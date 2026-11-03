"""Remembered reconciliation decisions: accept, reject or note a row.

Pure helpers live at the top; the small store helpers at the bottom keep the
saved decisions in the local database so a re-run of the month never loses them.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from apps.engine.recon import money, normalize_gstin, normalize_invoice_number

DECISION_ACCEPTED = "accepted"
DECISION_REJECTED = "rejected"
DECISION_NOTED = "noted"
DECISION_NONE = ""

DECISIONS = (DECISION_ACCEPTED, DECISION_REJECTED, DECISION_NOTED)
DECISION_LABELS = {
    DECISION_ACCEPTED: "Accepted",
    DECISION_REJECTED: "Rejected",
    DECISION_NOTED: "Noted",
}
DECISION_HELP = {
    DECISION_ACCEPTED: "Agreed as it stands; no further action on this row.",
    DECISION_REJECTED: "Not agreed; this row still needs fixing or chasing.",
    DECISION_NOTED: "Leave it for now with a reminder of why.",
}

REASONS = (
    ("rate_difference", "Rate difference"),
    ("credit_note_pending", "Credit note pending"),
    ("supplier_not_filed", "Supplier has not filed"),
    ("wrong_gstin", "Wrong GSTIN"),
    ("other", "Something else"),
)
REASON_LABELS = dict(REASONS)

NEEDS_DECISION = frozenset({"books_only", "portal_only", "amount_mismatch", "likely"})
_ROW_KEY_LIMIT = 320
_NOTE_LIMIT = 1000
_BY_LIMIT = 200


def decision_label(value) -> str:
    return DECISION_LABELS.get(str(value or ""), "Not decided")


def reason_label(code) -> str:
    return REASON_LABELS.get(str(code or ""), "")


def needs_decision(row: dict) -> bool:
    return str(row.get("status") or "") in NEEDS_DECISION


def _clean(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def base_key(row: dict) -> str:
    """A stable identity for a row that survives a re-run of the same month.

    Supplier plus invoice number is enough when both exist; otherwise fall back
    to the party, date and amount so a row without an invoice number still has
    a home for its decision.
    """
    gstin = normalize_gstin(row.get("gstin"))
    invoice = normalize_invoice_number(row.get("invoice_books")) or normalize_invoice_number(
        row.get("invoice_2b")
    )
    if gstin and invoice:
        return f"{gstin}|{invoice}"
    party = re.sub(r"[^A-Z0-9]+", "", str(row.get("party") or "").upper())[:24]
    when = str(row.get("date_books") or row.get("date_2b") or "")
    amount = row.get("amount_books")
    if amount is None:
        amount = row.get("amount_2b")
    value = money(amount)
    amount_text = f"{value:.2f}" if isinstance(value, Decimal) else ""
    return "|".join([gstin or "-", party or "-", when or "-", amount_text or "-"])


def row_keys(rows: list[dict]) -> list[str]:
    """One key per row; repeated invoices on one side get #1, #2 ... suffixes."""
    seen: dict[str, int] = {}
    keys: list[str] = []
    for row in rows:
        base = base_key(row)
        count = seen.get(base, 0)
        seen[base] = count + 1
        keys.append(base if count == 0 else f"{base}#{count}")
    return keys


def _record_dict(record) -> dict:
    decided_at = getattr(record, "decided_at", None)
    first_seen = getattr(record, "first_seen_at", None)
    return {
        "row_key": record.row_key,
        "decision": record.decision or "",
        "reason_code": record.reason_code or "",
        "reason_label": record.reason_label or "",
        "note": record.note or "",
        "decided_by": record.decided_by or "",
        "decided_at": decided_at.isoformat() if isinstance(decided_at, datetime) else "",
        "first_seen_at": first_seen.isoformat() if isinstance(first_seen, datetime) else "",
    }


def _attach(row: dict, record: dict) -> None:
    decision = str(record.get("decision") or "")
    row["row_key"] = row.get("row_key") or ""
    row["decision"] = decision
    row["decision_label"] = decision_label(decision)
    row["decision_reason_code"] = str(record.get("reason_code") or "")
    row["decision_reason"] = str(record.get("reason_label") or "")
    row["decision_note"] = str(record.get("note") or "")
    row["decision_by"] = str(record.get("decided_by") or "")
    row["decision_at"] = str(record.get("decided_at") or "")
    row["needs_decision"] = needs_decision(row)


def apply(rows: list[dict], saved: dict[str, dict], new_keys=None) -> dict:
    """Attach keys and decisions to rows in place, then summarise the result."""
    keys = row_keys(rows)
    fresh = set(new_keys or ())
    for row, key in zip(rows, keys):
        row["row_key"] = key
        _attach(row, saved.get(key) or {})
        row["is_new"] = key in fresh
    return summarize(rows)


def _row_money(row: dict) -> Decimal | None:
    amount = row.get("amount_2b")
    if amount is None:
        amount = row.get("amount_books")
    return money(amount)


def refresh_pack(pack: dict, saved: dict[str, dict]) -> dict:
    """Re-attach saved decisions to an already loaded pack without re-parsing.

    Used right after a decision is saved so the tray shows it immediately; the
    "new this run" badges are preserved from the pack that was produced.
    """
    recon = (pack or {}).get("recon") or {}
    rows = recon.get("rows") or []
    if rows:
        fresh = {row.get("row_key") for row in rows if row.get("is_new")}
        recon["decisions"] = apply(rows, saved, fresh)
    return pack


def summarize(rows: list[dict]) -> dict:
    """Counts and rupees per decision, over the rows that need a decision only."""
    counts = {
        DECISION_ACCEPTED: 0,
        DECISION_REJECTED: 0,
        DECISION_NOTED: 0,
        "undecided": 0,
        "new": 0,
        "exceptions": 0,
    }
    amounts = {
        DECISION_ACCEPTED: Decimal("0"),
        DECISION_REJECTED: Decimal("0"),
        DECISION_NOTED: Decimal("0"),
        "undecided": Decimal("0"),
        "at_stake": Decimal("0"),
    }
    by_reason: dict[str, int] = {}
    for row in rows:
        if not needs_decision(row):
            continue
        counts["exceptions"] += 1
        value = _row_money(row) or Decimal("0")
        amounts["at_stake"] += value
        decision = str(row.get("decision") or "")
        bucket = decision if decision in DECISIONS else "undecided"
        counts[bucket] += 1
        amounts[bucket] += value
        if row.get("is_new"):
            counts["new"] += 1
        code = str(row.get("decision_reason_code") or "")
        if code:
            by_reason[code] = by_reason.get(code, 0) + 1
    money_out = {key: float(value) for key, value in amounts.items()}
    return {"counts": counts, "money": money_out, "by_reason": by_reason}


def load(session, period_id: int) -> dict[str, dict]:
    from apps.engine.db import ReconDecision

    records = (
        session.query(ReconDecision)
        .filter(ReconDecision.period_id == int(period_id))
        .all()
    )
    return {record.row_key: _record_dict(record) for record in records}


def remember(session, period_id: int, keys: list[str], now: datetime | None = None) -> set[str]:
    """Record which rows exist this run and return the keys that are genuinely new."""
    from apps.engine.db import ReconDecision, utcnow

    when = now or utcnow()
    wanted = [str(key)[:_ROW_KEY_LIMIT] for key in keys if str(key or "").strip()]
    if not wanted:
        return set()
    existing = {
        record.row_key
        for record in session.query(ReconDecision.row_key)
        .filter(ReconDecision.period_id == int(period_id))
        .all()
    }
    fresh = {key for key in wanted if key not in existing}
    for key in fresh:
        session.add(
            ReconDecision(
                period_id=int(period_id),
                row_key=key,
                decision=DECISION_NONE,
                first_seen_at=when,
                updated_at=when,
            )
        )
    return fresh


def save(
    session,
    period_id: int,
    row_key: str,
    decision: str,
    reason_code: str = "",
    note: str = "",
    decided_by: str = "",
    now: datetime | None = None,
) -> dict:
    """Store one decision; an empty decision removes it. Raises ValueError on bad input."""
    from apps.engine.db import ReconDecision, utcnow

    key = _clean(row_key, _ROW_KEY_LIMIT)
    if not key:
        raise ValueError("This row has no identity, so it cannot be remembered.")
    value = str(decision or "").strip().lower()
    if value and value not in DECISIONS:
        raise ValueError("Choose accept, reject or note.")
    code = str(reason_code or "").strip().lower()
    if code and code not in REASON_LABELS:
        raise ValueError("That reason is not one of the ready-made choices.")
    when = now or utcnow()

    record = (
        session.query(ReconDecision)
        .filter(
            ReconDecision.period_id == int(period_id),
            ReconDecision.row_key == key,
        )
        .one_or_none()
    )
    if record is None:
        record = ReconDecision(
            period_id=int(period_id),
            row_key=key,
            first_seen_at=when,
        )
        session.add(record)

    if not value:
        record.decision = DECISION_NONE
        record.reason_code = None
        record.reason_label = None
        record.note = None
        record.decided_by = None
        record.decided_at = None
    else:
        record.decision = value
        record.reason_code = code or None
        record.reason_label = reason_label(code) or None
        record.note = _clean(note, _NOTE_LIMIT) or None
        record.decided_by = _clean(decided_by, _BY_LIMIT) or None
        record.decided_at = when
    record.updated_at = when
    session.flush()
    return _record_dict(record)
