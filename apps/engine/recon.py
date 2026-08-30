from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT_TOLERANCE = Decimal("1.00")
_COUNT_KEYS = ("matched", "books_only", "portal_only", "amount_mismatch", "likely")
_DATE_FMTS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y%m%d",
    "%d-%m-%y",
    "%d/%m/%y",
)


def normalize_gstin(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip().upper()


def normalize_invoice_number(value) -> str:
    if value is None:
        return ""
    alnum = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()

    def _digits(match: re.Match[str]) -> str:
        stripped = match.group(0).lstrip("0")
        return stripped or "0"

    return re.sub(r"\d+", _digits, alnum)


def parse_recon_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parts = re.split(r"[/\-.]", text)
    if len(parts) == 3 and all(parts):
        try:
            a, b, c = (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
        if a > 31:
            year, month, day = a, b, c
        else:
            day, month, year = a, b, c
            if year < 100:
                year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = str(value).strip().replace("₹", "").replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def reconcile(
    books_rows: list[dict],
    gstr_2b_rows: list[dict],
    bank_rows: list[dict] | None = None,
) -> dict:
    books = list(books_rows or [])
    twob = [row for row in (gstr_2b_rows or []) if not _is_cdn(row)]
    bank = list(bank_rows or [])

    used_books: set[int] = set()
    used_2b: set[int] = set()
    pairs: list[tuple[str, int | None, int | None]] = []

    def _claim(status: str, bi: int, gi: int) -> None:
        used_books.add(bi)
        used_2b.add(gi)
        pairs.append((status, bi, gi))

    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _exact_key(book, portal) and _amounts_close(book, portal):
                _claim("matched", bi, gi)
                break

    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _exact_key(book, portal) and not _amounts_close(book, portal):
                _claim("amount_mismatch", bi, gi)
                break

    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _likely_pair(book, portal):
                _claim("likely", bi, gi)
                break

    for gi in range(len(twob)):
        if gi not in used_2b:
            pairs.append(("portal_only", None, gi))
    for bi in range(len(books)):
        if bi not in used_books:
            pairs.append(("books_only", bi, None))

    rows = []
    counts = {key: 0 for key in _COUNT_KEYS}
    for status, bi, gi in pairs:
        book = books[bi] if bi is not None else {}
        portal = twob[gi] if gi is not None else {}
        row = _recon_row(status, book, portal)
        row["bank_hint"] = _bank_hint(row, book, portal, bank)
        rows.append(row)
        counts[status] = counts.get(status, 0) + 1
    return {"rows": rows, "counts": counts}


def _is_cdn(row: dict) -> bool:
    return str(row.get("document_type") or "").strip().upper().startswith("CDN")


def _gstin(row: dict, *keys: str) -> str:
    for key in keys:
        if row.get(key):
            return normalize_gstin(row.get(key))
    return ""


def _invoice(row: dict, *keys: str) -> str:
    for key in keys:
        if row.get(key) not in (None, ""):
            return normalize_invoice_number(row.get(key))
    return ""


def _row_date(row: dict, *keys: str) -> date | None:
    for key in keys:
        parsed = parse_recon_date(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _row_money(row: dict, *keys: str) -> Decimal | None:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return money(row.get(key))
    return None


def _books_gstin(row: dict) -> str:
    return _gstin(row, "supplier_gstin", "gstin")


def _books_invoice(row: dict) -> str:
    return _invoice(row, "invoice_number")


def _books_date(row: dict) -> date | None:
    return _row_date(row, "invoice_date", "date")


def _books_amount(row: dict) -> Decimal | None:
    return _row_money(row, "invoice_value", "amount")


def _gstr_gstin(row: dict) -> str:
    return _gstin(row, "gstin", "supplier_gstin")


def _gstr_invoice(row: dict) -> str:
    return _invoice(row, "invoice_number")


def _gstr_date(row: dict) -> date | None:
    return _row_date(row, "invoice_date", "date")


def _gstr_amount(row: dict) -> Decimal | None:
    return _row_money(row, "invoice_value", "amount")


def _exact_key(book: dict, portal: dict) -> bool:
    gstin = _books_gstin(book)
    inv = _books_invoice(book)
    if not gstin or not inv:
        return False
    if gstin != _gstr_gstin(portal) or inv != _gstr_invoice(portal):
        return False
    return _dates_agree(book, portal)


def _dates_agree(book: dict, portal: dict) -> bool:
    left = _books_date(book)
    right = _gstr_date(portal)
    if left is None or right is None:
        return True
    return left == right


def _amounts_close(book: dict, portal: dict) -> bool:
    left = _books_amount(book)
    right = _gstr_amount(portal)
    if left is None or right is None:
        return False
    return (left - right).copy_abs() <= AMOUNT_TOLERANCE


def _likely_pair(book: dict, portal: dict) -> bool:
    gstin = _books_gstin(book)
    when = _books_date(book)
    if not gstin or when is None:
        return False
    if gstin != _gstr_gstin(portal) or when != _gstr_date(portal):
        return False
    if not _amounts_close(book, portal):
        return False
    left = _books_invoice(book)
    right = _gstr_invoice(portal)
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _fmt_amount(value: Decimal | None):
    if value is None:
        return None
    return float(value)


def _recon_row(status: str, book: dict, portal: dict) -> dict:
    amt_2b = _gstr_amount(portal) if portal else None
    amt_books = _books_amount(book) if book else None
    diff = None
    if amt_2b is not None and amt_books is not None:
        diff = amt_2b - amt_books
    party = ""
    if portal:
        party = str(portal.get("trade_name") or portal.get("supplier_name") or portal.get("party_name") or "")
    if not party and book:
        party = str(book.get("supplier_name") or book.get("party_name") or book.get("trade_name") or "")
    gstin = _gstr_gstin(portal) if portal else ""
    if not gstin and book:
        gstin = _books_gstin(book)
    return {
        "status": status,
        "gstin": gstin,
        "party": party,
        "invoice_2b": str(portal.get("invoice_number") or "") if portal else "",
        "invoice_books": str(book.get("invoice_number") or "") if book else "",
        "date_2b": _fmt_date(_gstr_date(portal) if portal else None),
        "date_books": _fmt_date(_books_date(book) if book else None),
        "amount_2b": _fmt_amount(amt_2b),
        "amount_books": _fmt_amount(amt_books),
        "amount_diff": _fmt_amount(diff),
        "bank_hint": "",
        "source_2b": str(portal.get("source") or "") if portal else "",
        "source_books": str(book.get("source") or "") if book else "",
    }


def _bank_hint(row: dict, book: dict, portal: dict, bank_rows: list[dict]) -> str:
    if not bank_rows:
        return ""
    amount = _books_amount(book) if book else None
    if amount is None and portal:
        amount = _gstr_amount(portal)
    when = _books_date(book) if book else None
    if when is None and portal:
        when = _gstr_date(portal)
    party = str(row.get("party") or "")
    best_score = 0
    best_line: dict | None = None
    for line in bank_rows:
        score = _bank_score(line, amount, when, party)
        if score > best_score:
            best_score = score
            best_line = line
    if best_score < 70 or best_line is None:
        return ""
    line_date = parse_recon_date(best_line.get("date"))
    debit = money(best_line.get("debit"))
    credit = money(best_line.get("credit"))
    shown = debit if debit else credit
    narr = str(best_line.get("narration") or best_line.get("description") or "").strip()
    snippet = re.sub(r"\s+", " ", narr)[:40]
    parts = []
    if line_date:
        parts.append(line_date.isoformat())
    if shown is not None:
        parts.append(f"{shown:.2f}")
    if snippet:
        parts.append(snippet)
    return " | ".join(parts)


def _bank_score(line: dict, amount: Decimal | None, when: date | None, party: str) -> int:
    score = 0
    debit = money(line.get("debit"))
    credit = money(line.get("credit"))
    line_amt = debit if debit not in (None, Decimal("0")) else credit
    if amount is not None and line_amt is not None and (amount - line_amt).copy_abs() <= AMOUNT_TOLERANCE:
        score += 50
    line_date = parse_recon_date(line.get("date"))
    if when is not None and line_date is not None and abs((when - line_date).days) <= 7:
        score += 20
    narr = str(line.get("narration") or line.get("description") or "")
    if _name_overlap(party, narr):
        score += 20
    if debit not in (None, Decimal("0")):
        score += 10
    return score


def _name_overlap(party: str, narration: str) -> bool:
    party_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (party or "").upper())}
    narr_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (narration or "").upper())}
    return bool(party_tokens & narr_tokens)
