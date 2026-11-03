from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT_TOLERANCE = Decimal("1.00")
COUNT_KEYS = (
    "matched",
    "books_only",
    "portal_only",
    "amount_mismatch",
    "likely",
    "tax_mismatch",
    "duplicate",
    "split_merged",
    "credit_note",
)
_LEFTOVER_STATUSES = ("books_only", "portal_only")
_TAX_COMPONENTS = (
    ("taxable", ("taxable", "taxable_value"), "taxable value"),
    ("cgst", ("cgst",), "central tax"),
    ("sgst", ("sgst",), "state tax"),
    ("igst", ("igst",), "integrated tax"),
)
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
    *,
    date_tolerance_days: int = 0,
    amount_tolerance=None,
) -> dict:
    books = list(books_rows or [])
    portal_all = list(gstr_2b_rows or [])
    credit_notes = [row for row in portal_all if _is_cdn(row)]
    twob = [row for row in portal_all if not _is_cdn(row)]
    bank = list(bank_rows or [])
    tolerance = money(amount_tolerance)
    if tolerance is None:
        tolerance = AMOUNT_TOLERANCE
    days = max(0, int(date_tolerance_days or 0))

    used_books: set[int] = set()
    used_2b: set[int] = set()
    pairs: list[tuple[str, list[int], list[int], str, int]] = []

    def _claim(
        status: str,
        books_idx: list[int],
        portal_idx: list[int],
        side: str = "",
        size: int = 0,
    ) -> None:
        for bi in books_idx:
            used_books.add(bi)
        for gi in portal_idx:
            used_2b.add(gi)
        pairs.append((status, list(books_idx), list(portal_idx), side, size))

    # 1. Same supplier and invoice, date within the allowed days.
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _exact_key(book, portal, days) and _amounts_close(book, portal, tolerance):
                status = "tax_mismatch" if _tax_gaps(book, portal, tolerance) else "matched"
                _claim(status, [bi], [gi])
                break

    # 2. One invoice split across several portal lines, or several bills
    #    merged into one portal line. This runs before the amount check so a
    #    two-line split is not mistaken for a single line with a wrong total.
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        group = _split_portal_group(book, twob, used_2b, days, tolerance)
        if group:
            _claim("split_merged", [bi], group, "portal")
    for gi, portal in enumerate(twob):
        if gi in used_2b:
            continue
        group = _split_books_group(portal, books, used_books, days, tolerance)
        if group:
            _claim("split_merged", group, [gi], "books")

    # 3. Same key, but the invoice total differs. Skip this when the portal
    #    carries several lines for the same invoice; those are split or
    #    repeated lines, not a single wrong total.
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        if _unclaimed_portal_same_key(book, twob, used_2b) >= 2:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _exact_key(book, portal, days) and not _amounts_close(book, portal, tolerance):
                _claim("amount_mismatch", [bi], [gi])
                break

    # 4. Everything lines up except the invoice number itself.
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        for gi, portal in enumerate(twob):
            if gi in used_2b:
                continue
            if _likely_pair(book, portal, days, tolerance):
                _claim("likely", [bi], [gi])
                break

    # 5. The same invoice repeated on one side, with the same amount each time.
    for index, side, size in _duplicate_items(
        books, twob, used_books, used_2b, tolerance
    ):
        if side == "books":
            _claim("duplicate", [index], [], "books", size)
        else:
            _claim("duplicate", [], [index], "portal", size)

    # 6. Whatever is genuinely one-sided.
    for gi in range(len(twob)):
        if gi not in used_2b:
            _claim("portal_only", [], [gi])
    for bi in range(len(books)):
        if bi not in used_books:
            _claim("books_only", [bi], [])

    rows = []
    counts = {key: 0 for key in COUNT_KEYS}
    for status, bis, gis, side, size in pairs:
        book = books[bis[0]] if bis else {}
        portal = twob[gis[0]] if gis else {}
        extra = [twob[gi] for gi in gis[1:]]
        row = _recon_row(
            status,
            book,
            portal,
            extra_portal=extra,
            tolerance=tolerance,
            group_size=size or max(len(bis), len(gis)),
            side=side,
        )
        row["bank_hint"] = _bank_hint(row, book, portal, bank, tolerance)
        rows.append(row)
        counts[status] = counts.get(status, 0) + 1
    for note in credit_notes:
        row = _recon_row("credit_note", {}, note)
        row["bank_hint"] = ""
        rows.append(row)
        counts["credit_note"] += 1
    return {"rows": rows, "counts": counts, "totals": _totals(rows)}


def _money_of(row: dict, key: str) -> Decimal | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _totals(rows: list[dict]) -> dict:
    portal = Decimal("0")
    books = Decimal("0")
    risk = Decimal("0")
    unsupported = Decimal("0")
    credit_notes = Decimal("0")
    for row in rows:
        status = str(row.get("status") or "")
        amt_2b = _money_of(row, "amount_2b")
        amt_books = _money_of(row, "amount_books")
        if status == "credit_note":
            if amt_2b is not None:
                credit_notes += amt_2b.copy_abs()
            continue
        if amt_2b is not None:
            portal += amt_2b
        if amt_books is not None:
            books += amt_books
        if status == "portal_only" and amt_2b is not None:
            risk += amt_2b
        if status == "books_only" and amt_books is not None:
            unsupported += amt_books
    return {
        "portal_total": float(portal),
        "books_total": float(books),
        "gap": float(portal - books),
        "credit_at_risk": float(risk),
        "unsupported_credit": float(unsupported),
        "credit_note_total": float(credit_notes),
    }


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


def _exact_key(book: dict, portal: dict, days: int = 0) -> bool:
    gstin = _books_gstin(book)
    inv = _books_invoice(book)
    if not gstin or not inv:
        return False
    if gstin != _gstr_gstin(portal) or inv != _gstr_invoice(portal):
        return False
    return _dates_agree(book, portal, days)


def _dates_agree(book: dict, portal: dict, days: int = 0) -> bool:
    left = _books_date(book)
    right = _gstr_date(portal)
    if left is None or right is None:
        return True
    return abs((left - right).days) <= max(0, int(days or 0))


def _amounts_close(book: dict, portal: dict, tolerance: Decimal | None = None) -> bool:
    left = _books_amount(book)
    right = _gstr_amount(portal)
    if left is None or right is None:
        return False
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    return (left - right).copy_abs() <= limit


def _likely_pair(
    book: dict,
    portal: dict,
    days: int = 0,
    tolerance: Decimal | None = None,
) -> bool:
    gstin = _books_gstin(book)
    when = _books_date(book)
    if not gstin or when is None:
        return False
    if gstin != _gstr_gstin(portal) or not _dates_agree(book, portal, days):
        return False
    if not _amounts_close(book, portal, tolerance):
        return False
    left = _books_invoice(book)
    right = _gstr_invoice(portal)
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _tax_value(row: dict, keys: tuple[str, ...]) -> Decimal | None:
    for key in keys:
        if row.get(key) not in (None, ""):
            value = money(row.get(key))
            if value is not None:
                return value
    return None


def _tax_gaps(book: dict, portal: dict, tolerance: Decimal) -> list[tuple[str, Decimal]]:
    """Tax components that differ beyond the amount allowance."""
    gaps: list[tuple[str, Decimal]] = []
    for _slug, keys, label in _TAX_COMPONENTS:
        left = _tax_value(book, keys)
        right = _tax_value(portal, keys)
        if left is None or right is None:
            continue
        diff = right - left
        if diff.copy_abs() > tolerance:
            gaps.append((label, diff))
    return gaps


def _split_portal_group(
    book: dict,
    twob: list[dict],
    used_2b: set[int],
    days: int,
    tolerance: Decimal,
) -> list[int]:
    """Portal lines that together add up to this one books invoice."""
    gstin = _books_gstin(book)
    inv = _books_invoice(book)
    amount = _books_amount(book)
    if not gstin or not inv or amount is None:
        return []
    group: list[int] = []
    for gi, portal in enumerate(twob):
        if gi in used_2b:
            continue
        if _gstr_gstin(portal) != gstin or _gstr_invoice(portal) != inv:
            continue
        if not _dates_agree(book, portal, days):
            continue
        group.append(gi)
    if len(group) < 2:
        return []
    total = Decimal("0")
    for gi in group:
        value = _gstr_amount(twob[gi])
        if value is None:
            return []
        total += value
    return group if (total - amount).copy_abs() <= tolerance else []


def _split_books_group(
    portal: dict,
    books: list[dict],
    used_books: set[int],
    days: int,
    tolerance: Decimal,
) -> list[int]:
    """Several books bills that add up to this one portal line."""
    from itertools import combinations

    gstin = _gstr_gstin(portal)
    amount = _gstr_amount(portal)
    if not gstin or amount is None:
        return []
    candidates: list[int] = []
    for bi, book in enumerate(books):
        if bi in used_books:
            continue
        if _books_gstin(book) != gstin:
            continue
        if _books_amount(book) is None:
            continue
        if not _dates_agree(book, portal, days):
            continue
        candidates.append(bi)
    for size in (2, 3):
        if len(candidates) < size:
            continue
        for combo in combinations(candidates, size):
            total = Decimal("0")
            for bi in combo:
                value = _books_amount(books[bi])
                if value is None:
                    total = Decimal("0")
                    break
                total += value
            if (total - amount).copy_abs() <= tolerance:
                return list(combo)
    return []


def _unclaimed_portal_same_key(
    book: dict, twob: list[dict], used_2b: set[int]
) -> int:
    gstin = _books_gstin(book)
    inv = _books_invoice(book)
    if not gstin or not inv:
        return 0
    count = 0
    for gi, portal in enumerate(twob):
        if gi in used_2b:
            continue
        if _gstr_gstin(portal) == gstin and _gstr_invoice(portal) == inv:
            count += 1
    return count


def _duplicate_items(
    books: list[dict],
    twob: list[dict],
    used_books: set[int],
    used_2b: set[int],
    tolerance: Decimal,
) -> list[tuple[int, str, int]]:
    """Unmatched rows that are extra copies of the same invoice on one side.

    A real duplicate carries the same invoice number and the same amount. When
    the amounts differ the rows are partial lines (a split that does not add
    up), so they are left to the ordinary one-sided groups instead.
    """
    found: list[tuple[int, str, int]] = []
    for side, rows, used in (("books", books, used_books), ("portal", twob, used_2b)):
        groups: dict[tuple[str, str], list[int]] = {}
        for index, row in enumerate(rows):
            gstin = _books_gstin(row) if side == "books" else _gstr_gstin(row)
            inv = _books_invoice(row) if side == "books" else _gstr_invoice(row)
            if not gstin or not inv:
                continue
            groups.setdefault((gstin, inv), []).append(index)
        for indices in groups.values():
            if len(indices) < 2:
                continue
            amounts = [
                _books_amount(rows[i]) if side == "books" else _gstr_amount(rows[i])
                for i in indices
            ]
            if any(value is None for value in amounts):
                continue
            first = amounts[0]
            if any((value - first).copy_abs() > tolerance for value in amounts[1:]):
                continue
            for index in indices:
                if index in used:
                    continue
                found.append((index, side, len(indices)))
    return found


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _fmt_amount(value: Decimal | None):
    if value is None:
        return None
    return float(value)


def _recon_row(
    status: str,
    book: dict,
    portal: dict,
    *,
    extra_portal: list[dict] | None = None,
    tolerance: Decimal | None = None,
    group_size: int = 1,
    side: str = "",
) -> dict:
    extra = list(extra_portal or [])
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    amt_2b = _gstr_amount(portal) if portal else None
    if extra:
        total = amt_2b if amt_2b is not None else Decimal("0")
        for line in extra:
            value = _gstr_amount(line)
            if value is not None:
                total += value
        amt_2b = total
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
    gaps = _tax_gaps(book, portal, limit) if status == "tax_mismatch" else []
    row = {
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
        "reason": _reason(
            status,
            book,
            portal,
            diff,
            str(book.get("invoice_number") or "") if book else "",
            str(portal.get("invoice_number") or "") if portal else "",
            gaps=gaps,
            group_size=group_size,
            side=side,
        ),
        "bank_hint": "",
        "source_2b": str(portal.get("source") or "") if portal else "",
        "source_books": str(book.get("source") or "") if book else "",
    }
    if status != "credit_note" and not extra:
        for slug, keys, _label in _TAX_COMPONENTS:
            row[f"tax_{slug}_2b"] = _fmt_amount(_tax_value(portal, keys) if portal else None)
            row[f"tax_{slug}_books"] = _fmt_amount(_tax_value(book, keys) if book else None)
    return row


def _reason(
    status: str,
    book: dict,
    portal: dict,
    diff: Decimal | None,
    invoice_books: str,
    invoice_2b: str,
    *,
    gaps: list[tuple[str, Decimal]] | None = None,
    group_size: int = 1,
    side: str = "",
) -> str:
    if status == "matched":
        return "Supplier, invoice number, date and amount all agree."
    if status == "amount_mismatch":
        size = diff.copy_abs() if diff is not None else Decimal("0")
        return f"Invoice number, date and supplier agree, but the amounts differ by {size:.2f}."
    if status == "tax_mismatch":
        parts = [
            f"{label} differs by {value.copy_abs():.2f}" for label, value in (gaps or [])
        ]
        detail = " and ".join(parts) if parts else "a tax component differs"
        return f"Supplier, invoice, date and total agree, but {detail}."
    if status == "likely":
        return (
            "Date and amount agree, but the invoice numbers differ "
            f"(books '{invoice_books}' vs portal '{invoice_2b}') — confirm this is the same invoice."
        )
    if status == "books_only":
        return "This invoice appears only in the books; the GST portal download shows nothing like it."
    if status == "portal_only":
        return "This invoice appears only in the GST portal download; the books have no entry for it."
    if status == "credit_note":
        invoice = str(portal.get("invoice_number") or "").strip()
        where = f"Credit note {invoice}" if invoice else "A credit note"
        party = str(portal.get("trade_name") or portal.get("supplier_name") or "").strip()
        if party:
            where = f"{where} from {party}"
        return f"{where}: kept on its own so the credit is not lost; it is not matched to a purchase."
    if status == "duplicate":
        invoice = invoice_books or invoice_2b
        where = "books" if side == "books" else "2B download"
        times = "twice" if side == "books" and group_size == 2 else f"{group_size} times"
        return (
            f"Invoice {invoice} appears {times} in the {where}; "
            "only one entry is expected, so each copy is shown separately."
        )
    if status == "split_merged":
        if side == "books":
            return (
                f"These {group_size} bills add up to a single line in the 2B download; "
                "they are shown together so the money is not counted twice."
            )
        return (
            f"This invoice is split across {group_size} lines in the 2B download; "
            "together they add up to the books amount."
        )
    return ""


def _bank_hint(
    row: dict,
    book: dict,
    portal: dict,
    bank_rows: list[dict],
    tolerance: Decimal | None = None,
) -> str:
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
        score = _bank_score(line, amount, when, party, tolerance)
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


def _bank_score(
    line: dict,
    amount: Decimal | None,
    when: date | None,
    party: str,
    tolerance: Decimal | None = None,
) -> int:
    score = 0
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    debit = money(line.get("debit"))
    credit = money(line.get("credit"))
    line_amt = debit if debit not in (None, Decimal("0")) else credit
    if amount is not None and line_amt is not None and (amount - line_amt).copy_abs() <= limit:
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
