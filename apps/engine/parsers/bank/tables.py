from __future__ import annotations

import re
from decimal import Decimal

from apps.engine.parsers.bank.layout import _debit_credit
from apps.engine.parsers.bank.money import DATE_RE, amounts_in, is_plausible_iso_date, normalize_date, parse_amount
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


def rows_from_cell_tables(
    tables: list[list[list[str | None]]],
    profile: BankProfile,
    filename: str,
    page: int = 1,
    bbox: str | None = None,
) -> list[dict]:
    rows: list[dict] = []
    for table in tables:
        rows.extend(_table_to_rows(table, profile, filename, page, bbox))
    return rows


def rows_from_markdown(text: str, profile: BankProfile, filename: str, page: int = 1) -> list[dict]:
    return rows_from_cell_tables(_markdown_tables(text), profile, filename, page)


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


def _table_to_rows(
    table: list[list[str | None]],
    profile: BankProfile,
    filename: str,
    page: int,
    bbox: str | None,
) -> list[dict]:
    header_at = None
    mapping: dict[int, str] = {}
    for i, raw in enumerate(table[:8]):
        mapped = _map_header(raw)
        if mapped:
            header_at = i
            mapping = mapped
            break
    body = table[header_at + 1 :] if header_at is not None else table
    rows: list[dict] = []
    pending: dict | None = None
    for raw in body:
        cells = [clean_text(value or "") for value in raw]
        joined = clean_text(" ".join(cells))
        if not joined or OPENING_RE.search(joined) or is_boilerplate(joined):
            if pending and not DATE_RE.search(joined) and joined:
                pending["description"] = f"{pending['description']} {joined}".strip()
                pending["raw_text"] = f"{pending['raw_text']} | {joined}"
            continue
        if _row_has_txn_date(cells, mapping, joined):
            if pending is not None:
                rows.append(pending)
            pending = _cells_to_row(cells, mapping, profile, filename, page, bbox)
        elif pending is not None:
            debit = _mapped_amount(cells, mapping, "debit")
            credit = _mapped_amount(cells, mapping, "credit")
            balance = _mapped_amount(cells, mapping, "balance")
            if _row_complete(pending) and _looks_like_own_amounts(
                debit, credit, balance, joined, profile
            ):
                rows.append(pending)
                pending = _cells_to_row(
                    cells,
                    mapping,
                    profile,
                    filename,
                    page,
                    bbox,
                    inherit_date=pending.get("date"),
                )
                continue
            extra = _mapped_cell(cells, mapping, "narration") or joined
            if extra:
                pending["description"] = f"{pending['description']} {extra}".strip()
                pending["raw_text"] = f"{pending['raw_text']} | {extra}"
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
                    debit_v, credit_v = _debit_credit(amounts, joined, profile)
                    pending["debit"] = float(debit_v) if debit_v is not None else None
                    pending["credit"] = float(credit_v) if credit_v is not None else None
    if pending is not None:
        rows.append(pending)
    return [row for row in rows if _row_ok(row)]


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
        lowered = clean_text(value or "").lower().strip(":.")
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
    found = amounts_in(text)
    if found:
        value = found[0]
    else:
        value = parse_amount(text)
    if value == 0:
        return None
    return value


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
