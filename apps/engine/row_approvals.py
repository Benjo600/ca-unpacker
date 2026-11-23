"""Explicit approval for rows a parser had to infer.

An inferred bank row is not printed in the statement: it exists because the
running balance jumped by an amount nothing else explains. A CA has to look at
it and say yes or no. The decision is stored against a fingerprint of the row
(file, date, amounts, narration) so it survives the pack being rebuilt, which
deletes and re-inserts every extracted row.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from apps.engine.db import ExtractedRow, RowApproval, get_session

APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"


def _money_text(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def row_key(file_id: int | None, kind: str, row: dict) -> str:
    """A fingerprint stable across rebuilds, but specific enough to be one row."""
    parts = [
        str(file_id if file_id is not None else ""),
        str(kind or ""),
        str(row.get("date") or "")[:20],
        _money_text(row.get("debit")),
        _money_text(row.get("credit")),
        _money_text(row.get("balance")),
        " ".join(str(row.get("description") or "").split())[:120],
    ]
    return "|".join(parts)[:320]


def decisions_for(period_id: int) -> dict[str, str]:
    session = get_session()
    try:
        rows = session.query(RowApproval).filter(RowApproval.period_id == period_id).all()
        return {row.row_key: row.decision for row in rows}
    finally:
        session.close()


def set_decision(
    period_id: int,
    key: str,
    decision: str,
    note: str | None = None,
) -> str:
    """Record (or replace) the decision for one row fingerprint."""
    decision = (decision or APPROVED).strip().lower()
    if decision not in {APPROVED, REJECTED, PENDING}:
        raise ValueError(f"Unknown approval decision: {decision!r}")
    session = get_session()
    try:
        record = (
            session.query(RowApproval)
            .filter(RowApproval.period_id == period_id, RowApproval.row_key == key)
            .one_or_none()
        )
        now = datetime.now(timezone.utc)
        if record is None:
            record = RowApproval(period_id=period_id, row_key=key)
            session.add(record)
        record.decision = decision
        record.note = (note or "")[:1000] or None
        record.decided_at = now
        record.updated_at = now
        session.commit()
        return decision
    finally:
        session.close()


def apply_decisions(period_id: int, files: list[dict]) -> int:
    """Stamp each row in ``files`` with the decision already made for it.

    Mutates the row dicts in place and returns how many approved rows were
    found, so the pack writer knows what may leave the approval sheet.
    """
    decisions = decisions_for(period_id)
    if not decisions:
        return 0
    approved = 0
    for item in files or []:
        file_id = item.get("file_id")
        for row in item.get("rows") or []:
            key = row_key(file_id, item.get("kind") or "bank", row)
            decision = decisions.get(key)
            if not decision:
                continue
            row["approval"] = decision
            if decision == APPROVED:
                approved += 1
    return approved


def decide_row(row_id: int, decision: str = APPROVED, note: str | None = None) -> dict:
    """Approve or reject one stored extracted row by its database id."""
    session = get_session()
    try:
        extracted = session.get(ExtractedRow, int(row_id))
        if extracted is None:
            return {"ok": False, "error": "That row is no longer in the library."}
        try:
            payload = json.loads(extracted.payload_json)
        except (TypeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        key = row_key(extracted.file_id, extracted.kind, payload)
        period_id = extracted.period_id
    finally:
        session.close()
    recorded = set_decision(period_id, key, decision, note)
    return {"ok": True, "decision": recorded, "row_id": int(row_id), "row_key": key}


def pending_rows(period_id: int, files: list[dict]) -> list[dict]:
    """Rows that are inferred and still waiting for a decision."""
    decisions = decisions_for(period_id)
    waiting: list[dict] = []
    for item in files or []:
        file_id = item.get("file_id")
        for row in item.get("rows") or []:
            if not _is_inferred(row):
                continue
            decision = decisions.get(row_key(file_id, item.get("kind") or "bank", row))
            if decision == APPROVED:
                continue
            waiting.append(row)
    return waiting


def _is_inferred(row: dict) -> bool:
    if row.get("needs_approval"):
        return True
    flags = row.get("flags") if row.get("flags") is not None else row.get("validation_flags")
    if isinstance(flags, str):
        return "inferred_from_balance" in flags
    return "inferred_from_balance" in (flags or [])
