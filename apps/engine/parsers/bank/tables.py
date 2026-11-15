from __future__ import annotations

import re
from decimal import Decimal

from apps.engine.parsers.bank.layout import _debit_credit
from apps.engine.parsers.bank.money import (
    DATE_RE,
    amounts_in,
    is_plausible_iso_date,
    normalize_date,
    parse_amount,
    parse_amount_with_evidence,
)
from apps.engine.parsers.bank.patterns import OPENING_RE, clean_text, is_boilerplate
from apps.engine.parsers.bank.profiles import BankProfile

HEADER = (
    ("date", ("txn date", "trans date", "transaction date", "value date", "tran date", "date")),
    ("narration", ("narration", "particulars", "description", "remarks", "details")),
    ("cheque", ("chq", "cheque", "ref no", "instrument", "chq / ref", "ref.")),
    ("debit", ("withdrawal", "withdrawals", "debit", "withdraw", "dr.")),
    ("credit", ("deposit", "deposits", "credit", "cr.")),
    ("balance", ("balance",)),
)

_SKIPPED_ROW_LIMIT = 200


def rows_from_cell_tables(
    tables: list[list[list[str | None]]],
    profile: BankProfile,
    filename: str,
    page: int = 1,
    bbox: str | None = None,
) -> list[dict]:
    """Convenience wrapper: parse tables that share one page."""
    session = TableSession(profile, filename)
    for table in tables:
        session.feed(table, page, bbox)
    return session.finish()[0]


class TableSession:
    """Parse cell tables page by page, threading transaction state across pages.

    A transaction whose narration wraps onto the next page used to be split at
    the table boundary and silently dropped (the fragment lacked a date or a
    balance).  The session keeps ``pending`` state across tables and records
    anything it cannot complete as an explicit skipped row instead of losing
    it.
    """

    def __init__(self, profile: BankProfile, filename: str) -> None:
        self.profile = profile
        self.filename = filename
        self.rows: list[dict] = []
        self.pending: dict | None = None
        self.skipped: list[dict] = []

    def feed(self, table: list[list[str | None]], page: int, bbox: str | None) -> None:
        header_at = None
        mapping: dict[int, str] = {}
        for i, raw in enumerate(table[:8]):
            mapped = _map_header(raw)
            if mapped:
                header_at = i
                mapping = mapped
                break
        body = table[header_at + 1 :] if header_at is not None else table
        for raw in body:
            cells = [clean_text(value or "") for value in raw]
            joined = clean_text(" ".join(cells))
            if not joined:
                continue
            if _looks_like_header_row(cells, mapping):
                self._skip(page, joined, "repeated_header")
                continue
            if OPENING_RE.search(joined) or is_boilerplate(joined):
                if self.pending and not DATE_RE.search(joined) and joined:
                    self._append_narration(joined)
                continue
            if _row_has_txn_date(cells, mapping, joined):
                if self.pending is not None:
                    self._settle_pending()
                self.pending = _cells_to_row(
                    cells, mapping, self.profile, self.filename, page, bbox
                )
                continue
            if self.pending is not None:
                debit = _mapped_amount(cells, mapping, "debit")
                credit = _mapped_amount(cells, mapping, "credit")
                balance = _mapped_amount(cells, mapping, "balance")
                if _row_complete(self.pending) and _looks_like_own_amounts(
                    debit, credit, balance, joined, self.profile
                ):
                    previous = self.pending
                    self._settle_pending()
                    self.pending = _cells_to_row(
                        cells,
                        mapping,
                        self.profile,
                        self.filename,
                        page,
                        bbox,
                        inherit_date=previous.get("date") if previous else None,
                    )
                    continue
                extra = _mapped_cell(cells, mapping, "narration") or joined
                if extra:
                    self._append_narration(extra)
                self._backfill_amounts(debit, credit, balance, joined)
            else:
                # No open transaction: an amount-only fragment with no date and
                # no narration owner cannot be attributed — record it.
                if joined and amounts_in(joined):
                    self._skip(page, joined, "orphan_amount_row")

    def _append_narration(self, extra: str) -> None:
        pending = self.pending
        if pending is None:
            return
        pending["description"] = f"{pending['description']} {extra}".strip()
        pending["raw_text"] = f"{pending['raw_text']} | {extra}"

    def _backfill_amounts(
        self,
        debit: Decimal | None,
        credit: Decimal | None,
        balance: Decimal | None,
        joined: str,
    ) -> None:
        pending = self.pending
        if pending is None:
            return
        if pending.get("debit") is None and debit is not None:
            pending["debit"] = float(debit)
        if pending.get("credit") is None and credit is not None:
            pending["credit"] = float(credit)
        if pending.get("balance") is None and balance is not None:
            pending["balance"] = float(balance)
        if pending.get("debit") is None and pending.get("credit") is None:
            amounts = amounts_in(joined)
            if len(amounts) >= 2:
                pending["balance"] = float(amounts[-1])
                debit_v, credit_v = _debit_credit(amounts, joined, self.profile)
                pending["debit"] = float(debit_v) if debit_v is not None else None
                pending["credit"] = float(credit_v) if credit_v is not None else None

    def _settle_pending(self) -> None:
        """Move ``pending`` into rows or skipped, then clear it."""
        pending = self.pending
        self.pending = None
        if pending is None:
            return
        if _row_ok(pending):
            self.rows.append(pending)
        else:
            self._skip(
                pending.get("source_page") or 1,
                pending.get("raw_text") or pending.get("description") or "",
                "incomplete_transaction_row",
            )

    def _skip(self, page: int, text: str, reason: str) -> None:
        if len(self.skipped) >= _SKIPPED_ROW_LIMIT:
            return
        self.skipped.append(
            {
                "source_page": page,
                "raw_text": (text or "")[:240],
                "reason": reason,
            }
        )

    def finish(self) -> tuple[list[dict], list[dict]]:
        self._settle_pending()
        return self.rows, self.skipped


def _looks_like_header_row(cells: list[str], mapping: dict[int, str]) -> bool:
    """A repeated header row: header-shaped labels, no transaction content."""
    if not cells:
        return False
    joined = clean_text(" ".join(cells)).lower()
    if not joined or DATE_RE.search(joined) or amounts_in(joined):
        return False
    mapped = _map_header(cells)
    if mapped:
        return True
    header_words = {"date", "narration", "particulars", "description", "debit", "credit",
                    "withdrawal", "deposit", "balance", "chq", "cheque", "ref"}
    hits = sum(1 for word in re.split(r"[\s/]+", joined) if word.strip(":.") in header_words)
    return hits >= 2


def rows_from_markdown(text: str, profile: BankProfile, filename: str, page: int = 1) -> list[dict]:
    session = TableSession(profile, filename)
    for table in _markdown_tables(text):
        session.feed(table, page, None)
    return session.finish()[0]


def _markdown_tables(text: str) -> list[list[list[str | None]]]:
    tables: list[list[list[str | None]]] = []
    current: list[list[str | None]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [part.strip() or None for part in line.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", (cell or "").replace(" ", "")) for cell in cells):
                continue
            current.append(cells)
            continue
        if current:
            if len(current) >= 2:
                tables.append(current)
            current = []
    if len(current) >= 2:
        tables.append(current)
    return tables


def _row_has_txn_date(cells: list[str], mapping: dict[int, str], joined: str) -> bool:
    if any(name == "date" for name in mapping.values()):
        return bool(DATE_RE.search(_mapped_cell(cells, mapping, "date")))
    return bool(DATE_RE.search(joined))


def _row_complete(row: dict | None) -> bool:
    if not row or not row.get("date") or row.get("balance") is None:
        return False
    return row.get("debit") is not None or row.get("credit") is not None


def _looks_like_own_amounts(
    debit: Decimal | None,
    credit: Decimal | None,
    balance: Decimal | None,
    joined: str,
    profile: BankProfile,
) -> bool:
    if balance is not None and (debit is not None or credit is not None):
        return True
    amounts = amounts_in(joined)
    if len(amounts) >= 2:
        guessed_debit, guessed_credit = _debit_credit(amounts, joined, profile)
        return guessed_debit is not None or guessed_credit is not None
    return False


def _row_ok(row: dict) -> bool:
    if not row.get("date"):
        return False
    if row.get("balance") is None:
        return False
    return row.get("debit") is not None or row.get("credit") is not None


def _map_header(raw: list[str | None]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for index, value in enumerate(raw):
        lowered = clean_text(value or "").lower().strip(":.") if value else ""
        if not lowered:
            continue
        for key, hints in HEADER:
            if key in used:
                continue
            if any(hint == lowered or hint in lowered for hint in hints):
                mapping[index] = key
                used.add(key)
                break
    keys = set(mapping.values())
    if "date" in keys and ("debit" in keys or "credit" in keys or "balance" in keys):
        return mapping
    return {}


def _mapped_cell(cells: list[str], mapping: dict[int, str], key: str) -> str:
    for index, name in mapping.items():
        if name == key and index < len(cells):
            return cells[index]
    return ""


def _mapped_amount(cells: list[str], mapping: dict[int, str], key: str) -> Decimal | None:
    text = _mapped_cell(cells, mapping, key)
    if not text:
        return None
    evidence = parse_amount_with_evidence(text)
    if evidence.value == 0:
        return None
    return evidence.value


def _cells_to_row(
    cells: list[str],
    mapping: dict[int, str],
    profile: BankProfile,
    filename: str,
    page: int,
    bbox: str | None,
    inherit_date: str | None = None,
) -> dict | None:
    joined = clean_text(" ".join(cells))
    date_text = _mapped_cell(cells, mapping, "date") or joined
    date_match = DATE_RE.search(date_text)
    if date_match:
        date = normalize_date(date_match.group(1))
        if not is_plausible_iso_date(date):
            date = inherit_date
    else:
        date = inherit_date
    if not date or not is_plausible_iso_date(date):
        return None
    debit = _mapped_amount(cells, mapping, "debit")
    credit = _mapped_amount(cells, mapping, "credit")
    balance = _mapped_amount(cells, mapping, "balance")
    if balance is None or (debit is None and credit is None):
        amounts = amounts_in(joined)
        if len(amounts) >= 2:
            balance = amounts[-1]
            guessed_debit, guessed_credit = _debit_credit(amounts, joined, profile)
            if debit is None:
                debit = guessed_debit
            if credit is None:
                credit = guessed_credit
    description = _mapped_cell(cells, mapping, "narration") or DATE_RE.sub("", joined, count=1)
    description = re.sub(r"\s{2,}", " ", description).strip(" -|")
    cheque = _mapped_cell(cells, mapping, "cheque") or None
    if cheque and not re.search(r"\d", cheque):
        cheque = None
    chq = re.search(r"\b(?:chq|cheque|ref)[^\d]{0,6}(\d{4,})\b", joined, re.I)
    if not cheque and chq:
        cheque = chq.group(1)
    return {
        "date": date,
        "description": description or joined,
        "cheque_ref": cheque or None,
        "debit": float(debit) if debit is not None else None,
        "credit": float(credit) if credit is not None else None,
        "balance": float(balance) if balance is not None else None,
        "source_page": page,
        "source_bbox": bbox,
        "source": f"{filename}#p{page}" + (f"@{bbox}" if bbox else ""),
        "raw_text": joined,
        "flags": [],
    }
