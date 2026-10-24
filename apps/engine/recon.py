from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT_TOLERANCE = Decimal("1.00")
COUNT_KEYS = ("matched", "books_only", "portal_only", "amount_mismatch", "likely")
GENERIC_STATUS_KEYS = (
    "matched",
    "amount_mismatch",
    "review_required",
    "left_only",
    "right_only",
    "duplicate",
)
_COUNT_KEYS = COUNT_KEYS
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


# ---------------------------------------------------------------------------
# Generic comparison engine
#
# The GST reconciliation above is deliberately narrow: GSTR-2B against books,
# with the statuses the existing pack writer already understands.  The helpers
# below compare any two extracted datasets (purchase invoices, purchase
# registers, bank statements) without changing the source rows.  Matching is
# one-to-one, keyed on identifiers first, and only falls back to a candidate
# that a human must review.  Amount similarity alone never produces a match.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ValueRecord:
    index: int
    row: dict
    gstin: str
    reference: str
    reference_display: str
    date: date | None
    date_display: str
    party: str
    amount: Decimal | None
    taxable: Decimal | None
    tax: Decimal | None
    source: str
    currency: str


@dataclass(frozen=True)
class _BankRecord:
    index: int
    row: dict
    date: date | None
    date_display: str
    text: str
    reference: str
    amount: Decimal | None
    direction: str
    source: str
    currency: str


def _tax_total(row: dict) -> Decimal | None:
    direct = _row_money(row, "tax", "tax_amount")
    if direct is not None:
        return direct
    parts = [
        _row_money(row, "igst"),
        _row_money(row, "cgst"),
        _row_money(row, "sgst"),
        _row_money(row, "cess"),
    ]
    present = [value for value in parts if value is not None]
    if not present:
        return None
    return sum(present, Decimal("0"))


def _first_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _value_record(row: dict, index: int) -> _ValueRecord:
    reference_display = _first_text(
        row, "invoice_number", "voucher_number", "reference", "bill_number"
    )
    date_raw = _first_text(
        row, "invoice_date", "voucher_date", "date", "posting_date", "document_date"
    )
    parsed_date = _row_date(
        row, "invoice_date", "voucher_date", "date", "posting_date", "document_date"
    )
    party = _first_text(
        row,
        "supplier_name",
        "party_name",
        "trade_name",
        "customer_name",
        "vendor_name",
    )
    return _ValueRecord(
        index=index,
        row=row,
        gstin=_gstin(row, "supplier_gstin", "gstin", "party_gstin"),
        reference=_invoice(
            row, "invoice_number", "voucher_number", "reference", "bill_number"
        ),
        reference_display=reference_display,
        date=parsed_date,
        date_display=parsed_date.isoformat() if parsed_date else date_raw,
        party=party,
        amount=_row_money(row, "invoice_value", "amount", "total"),
        taxable=_row_money(row, "taxable_value", "taxable"),
        tax=_tax_total(row),
        source=_first_text(row, "source"),
        currency=_first_text(row, "currency_code", "currency"),
    )


def _bank_record(row: dict, index: int) -> _BankRecord:
    debit = money(row.get("debit"))
    credit = money(row.get("credit"))
    if debit is not None and debit != 0:
        amount = debit.copy_abs()
        direction = "debit"
    elif credit is not None and credit != 0:
        amount = credit.copy_abs()
        direction = "credit"
    elif debit is not None:
        amount = debit.copy_abs()
        direction = "debit"
    elif credit is not None:
        amount = credit.copy_abs()
        direction = "credit"
    else:
        amount = None
        direction = ""
    text = _first_text(row, "description", "narration", "detail")
    parsed_date = _row_date(row, "date", "transaction_date", "value_date")
    date_raw = _first_text(row, "date", "transaction_date", "value_date")
    return _BankRecord(
        index=index,
        row=row,
        date=parsed_date,
        date_display=parsed_date.isoformat() if parsed_date else date_raw,
        text=text,
        reference=_first_text(row, "cheque_ref", "reference"),
        amount=amount,
        direction=direction,
        source=_first_text(row, "source"),
        currency=_first_text(row, "currency_code", "currency"),
    )


def _row_meta(row: dict, key: str):
    return row.get(f"_ca_{key}")


def _public_record(record: _ValueRecord) -> dict:
    return {
        "row_id": _row_meta(record.row, "row_id"),
        "file_id": _row_meta(record.row, "file_id"),
        "file_name": _row_meta(record.row, "file_name"),
        "kind": _row_meta(record.row, "kind"),
        "reference": record.reference_display,
        "normalized_reference": record.reference,
        "date": record.date_display,
        "party": record.party,
        "gstin": record.gstin,
        "amount": _fmt_amount(record.amount),
        "taxable": _fmt_amount(record.taxable),
        "tax": _fmt_amount(record.tax),
        "currency": record.currency,
        "source": record.source,
        "source_page": _row_meta(record.row, "page") or record.row.get("source_page"),
        "source_bbox": _row_meta(record.row, "bbox") or record.row.get("source_bbox"),
    }


def _public_bank(record: _BankRecord) -> dict:
    return {
        "row_id": _row_meta(record.row, "row_id"),
        "file_id": _row_meta(record.row, "file_id"),
        "file_name": _row_meta(record.row, "file_name"),
        "kind": _row_meta(record.row, "kind") or "bank",
        "reference": record.reference,
        "normalized_reference": normalize_invoice_number(record.reference),
        "date": record.date_display,
        "description": record.text,
        "direction": record.direction,
        "amount": _fmt_amount(record.amount),
        "currency": record.currency,
        "source": record.source,
        "source_page": _row_meta(record.row, "page") or record.row.get("source_page"),
        "source_bbox": _row_meta(record.row, "bbox") or record.row.get("source_bbox"),
    }


def _abs_diff(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return (left - right).copy_abs()


def _date_diff(left: date | None, right: date | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left - right).days)


def _date_within(
    left: date | None, right: date | None, days: int, *, missing_ok: bool = True
) -> bool:
    difference = _date_diff(left, right)
    if difference is None:
        return missing_ok
    return difference <= days


def _currencies_match(left: str, right: str) -> bool:
    if not left or not right:
        return True
    return left.strip().upper() == right.strip().upper()


def _amount_close(
    left: Decimal | None,
    right: Decimal | None,
    tolerance: Decimal = AMOUNT_TOLERANCE,
) -> bool:
    difference = _abs_diff(left, right)
    return difference is not None and difference <= tolerance


def _name_overlap_count(left: str, right: str) -> int:
    left_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (left or "").upper())}
    right_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (right or "").upper())}
    return len(left_tokens & right_tokens)


def _reference_prefix(left: str, right: str) -> bool:
    if not left or not right or left == right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def _differences(
    left: _ValueRecord, right: _ValueRecord
) -> dict:
    return {
        "amount": _fmt_amount(_abs_diff(left.amount, right.amount)),
        "taxable": _fmt_amount(_abs_diff(left.taxable, right.taxable)),
        "tax": _fmt_amount(_abs_diff(left.tax, right.tax)),
        "date_days": _date_diff(left.date, right.date),
    }


def _pair_status(
    left: _ValueRecord,
    right: _ValueRecord,
    tolerance: Decimal,
    date_window_days: int,
) -> tuple[str, str]:
    if not _currencies_match(left.currency, right.currency):
        return "review_required", "currency_differs"
    amount_difference = _abs_diff(left.amount, right.amount)
    if amount_difference is None:
        return "review_required", "amount_missing"
    if amount_difference > tolerance:
        return "amount_mismatch", "total_differs"
    tax_difference = _abs_diff(left.tax, right.tax)
    if tax_difference is not None and tax_difference > tolerance:
        return "review_required", "tax_differs"
    taxable_difference = _abs_diff(left.taxable, right.taxable)
    if taxable_difference is not None and taxable_difference > tolerance:
        return "review_required", "taxable_differs"
    date_difference = _date_diff(left.date, right.date)
    if date_difference is not None and date_difference > date_window_days:
        return "review_required", "date_differs"
    return "matched", "values_agree"


def _explain(
    status: str,
    reason: str,
    left: _ValueRecord | _BankRecord | None,
    right: _ValueRecord | _BankRecord | None,
) -> str:
    if status == "matched":
        if reason == "bank_reference":
            return "The reference found in the bank narration and the amount agree."
        return "GSTIN/reference, date and amount agree."
    if status == "amount_mismatch":
        difference = _abs_diff(
            getattr(left, "amount", None), getattr(right, "amount", None)
        )
        shown = _fmt_amount(difference)
        tail = f" Difference is {shown:.2f}." if shown is not None else ""
        return f"Same reference but the total does not agree.{tail}".strip()
    if status == "review_required":
        return {
            "tax_differs": "The totals agree but the tax value differs. Confirm before relying on this match.",
            "taxable_differs": "The totals agree but the taxable value differs. Confirm before relying on this match.",
            "date_differs": "The reference and amount agree but the dates are far apart. Confirm this match.",
            "currency_differs": "The reference agrees but the currencies differ. No conversion is performed.",
            "amount_missing": "The reference agrees but one side has no readable amount.",
            "same_reference": "The reference agrees but the GSTIN needs confirmation.",
            "reference_prefix": "The invoice numbers share a prefix and the amount agrees. Confirm this match.",
            "name_amount_date": "The party, amount and nearby date agree, but there is no shared reference. Confirm this match.",
            "bank_reference": "The bank narration mentions this voucher reference and the amount agrees.",
            "bank_fuzzy": "The amount, date and party overlap, but no reference is present. Confirm this match.",
            "multiple_candidates": "More than one record looks similar. Choose the correct match manually.",
        }.get(reason, "This record needs a human check before it can be relied on.")
    if status == "duplicate":
        return "This reference appears more than once. No automatic one-to-one pairing was made."
    if status == "left_only":
        return "No matching record was found in the comparison dataset."
    if status == "right_only":
        return "No matching record was found in the comparison dataset."
    return ""


def _pair_row(
    status: str,
    reason: str,
    left: _ValueRecord | _BankRecord | None = None,
    right: _ValueRecord | _BankRecord | None = None,
    explanation: str | None = None,
) -> dict:
    left_payload = None
    right_payload = None
    if isinstance(left, _ValueRecord):
        left_payload = _public_record(left)
    elif isinstance(left, _BankRecord):
        left_payload = _public_bank(left)
    if isinstance(right, _ValueRecord):
        right_payload = _public_record(right)
    elif isinstance(right, _BankRecord):
        right_payload = _public_bank(right)
    differences = {"amount": None, "taxable": None, "tax": None, "date_days": None}
    if isinstance(left, _ValueRecord) and isinstance(right, _ValueRecord):
        differences = _differences(left, right)
    elif isinstance(left, (_ValueRecord, _BankRecord)) and isinstance(
        right, (_ValueRecord, _BankRecord)
    ):
        differences["amount"] = _fmt_amount(
            _abs_diff(getattr(left, "amount", None), getattr(right, "amount", None))
        )
        differences["date_days"] = _date_diff(left.date, right.date)
    return {
        "status": status,
        "reason_code": reason,
        "explanation": explanation or _explain(status, reason, left, right),
        "left": left_payload,
        "right": right_payload,
        "differences": differences,
    }


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in GENERIC_STATUS_KEYS}


def _count_rows(rows: list[dict]) -> dict[str, int]:
    counts = _empty_counts()
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def compare_records(
    left_rows: list[dict],
    right_rows: list[dict],
    *,
    amount_tolerance: Decimal = AMOUNT_TOLERANCE,
    date_window_days: int = 30,
) -> dict:
    """Compare two invoice-like datasets one-to-one.

    Exact GSTIN + invoice-number groups are paired first.  Remaining rows may
    only become a review candidate when a reference, invoice-number prefix, or
    party name also supports the amount.  Similar amounts alone never match.
    """
    left = [_value_record(row, index) for index, row in enumerate(left_rows or [])]
    right = [_value_record(row, index) for index, row in enumerate(right_rows or [])]
    used_left: set[int] = set()
    used_right: set[int] = set()
    rows: list[dict] = []

    def claim(status: str, reason: str, li: int, ri: int) -> None:
        if li in used_left or ri in used_right:
            return
        used_left.add(li)
        used_right.add(ri)
        rows.append(_pair_row(status, reason, left[li], right[ri]))

    left_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    right_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record in left:
        if record.gstin and record.reference:
            left_groups[(record.gstin, record.reference)].append(record.index)
    for record in right:
        if record.gstin and record.reference:
            right_groups[(record.gstin, record.reference)].append(record.index)

    for key in sorted(set(left_groups) & set(right_groups)):
        pending_left = [i for i in left_groups[key] if i not in used_left]
        pending_right = [i for i in right_groups[key] if i not in used_right]
        if not pending_left or not pending_right:
            continue
        amount_pairs = [
            (li, ri)
            for li in pending_left
            for ri in pending_right
            if _amount_close(left[li].amount, right[ri].amount, amount_tolerance)
        ]
        left_candidates: dict[int, list[int]] = defaultdict(list)
        right_candidates: dict[int, list[int]] = defaultdict(list)
        for li, ri in amount_pairs:
            left_candidates[li].append(ri)
            right_candidates[ri].append(li)
        for li, ri in amount_pairs:
            if li in used_left or ri in used_right:
                continue
            if len(left_candidates[li]) != 1 or len(right_candidates[ri]) != 1:
                continue
            status, reason = _pair_status(
                left[li], right[ri], amount_tolerance, date_window_days
            )
            claim(status, reason, li, ri)

        pending_left = [i for i in left_groups[key] if i not in used_left]
        pending_right = [i for i in right_groups[key] if i not in used_right]
        if len(pending_left) == 1 and len(pending_right) == 1:
            status, reason = _pair_status(
                left[pending_left[0]],
                right[pending_right[0]],
                amount_tolerance,
                date_window_days,
            )
            # Reaching this branch means the amounts did not pair.  Preserve
            # that as an amount mismatch instead of calling it a likely match.
            if status == "matched":
                status, reason = "amount_mismatch", "total_differs"
            claim(status, reason, pending_left[0], pending_right[0])
            continue
        for li in pending_left:
            used_left.add(li)
            rows.append(_pair_row("duplicate", "duplicate_key", left[li], None))
        for ri in pending_right:
            used_right.add(ri)
            rows.append(_pair_row("duplicate", "duplicate_key", None, right[ri]))

    # Candidate pass: unique, supported, and explicitly left for review.
    for record in left:
        if record.index in used_left:
            continue
        candidates: list[tuple[int, str]] = []
        for other in right:
            if other.index in used_right:
                continue
            reason = _review_candidate(record, other, amount_tolerance)
            if reason:
                candidates.append((other.index, reason))
        if len(candidates) != 1:
            continue
        ri, reason = candidates[0]
        used_left.add(record.index)
        used_right.add(ri)
        rows.append(_pair_row("review_required", reason, record, right[ri]))

    for record in left:
        if record.index not in used_left:
            used_left.add(record.index)
            rows.append(_pair_row("left_only", "no_counterpart", record, None))
    for record in right:
        if record.index not in used_right:
            used_right.add(record.index)
            rows.append(_pair_row("right_only", "no_counterpart", None, record))

    return {"rows": rows, "counts": _count_rows(rows)}


def _review_candidate(
    left: _ValueRecord,
    right: _ValueRecord,
    amount_tolerance: Decimal,
) -> str | None:
    if not _currencies_match(left.currency, right.currency):
        return None
    if not _amount_close(left.amount, right.amount, amount_tolerance):
        return None
    same_reference = bool(
        left.reference and right.reference and left.reference == right.reference
    )
    if same_reference and _date_within(left.date, right.date, 30):
        if not left.gstin or not right.gstin or left.gstin != right.gstin:
            return "same_reference"
    if (
        left.gstin
        and right.gstin
        and left.gstin == right.gstin
        and _reference_prefix(left.reference, right.reference)
        and _date_within(left.date, right.date, 7)
    ):
        return "reference_prefix"
    overlap = _name_overlap_count(left.party, right.party)
    if overlap and _date_within(left.date, right.date, 3):
        if overlap >= 2 or any(
            len(token) >= 5
            for token in (
                set(re.findall(r"[A-Za-z]{3,}", left.party.upper()))
                & set(re.findall(r"[A-Za-z]{3,}", right.party.upper()))
            )
        ):
            return "name_amount_date"
    return None


def _bank_mentions_reference(text: str, reference: str) -> bool:
    normalised_reference = normalize_invoice_number(reference)
    if len(normalised_reference) < 4:
        return False
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9/\-]*", text or "")
    if any(normalize_invoice_number(token) == normalised_reference for token in tokens):
        return True
    if len(normalised_reference) < 6:
        return False
    return normalised_reference in normalize_invoice_number(text)


def _bank_pair_status(
    bank: _BankRecord,
    ledger: _ValueRecord,
    amount_tolerance: Decimal,
    reference_window_days: int,
) -> tuple[str, str]:
    if not _currencies_match(bank.currency, ledger.currency):
        return "review_required", "currency_differs"
    difference = _abs_diff(bank.amount, ledger.amount)
    if difference is None:
        return "review_required", "amount_missing"
    if difference > amount_tolerance:
        return "amount_mismatch", "total_differs"
    if not _date_within(bank.date, ledger.date, reference_window_days):
        return "review_required", "date_differs"
    return "matched", "bank_reference"


def compare_bank_ledger(
    bank_rows: list[dict],
    ledger_rows: list[dict],
    *,
    amount_tolerance: Decimal = AMOUNT_TOLERANCE,
    reference_window_days: int = 45,
    fuzzy_window_days: int = 3,
) -> dict:
    """Compare bank statement lines with accounting vouchers.

    A reference found in the narration plus an agreeing amount is a match.
    Amount + nearby date + party overlap without a reference is only ever a
    review candidate.  Amount similarity alone is not enough.
    """
    bank = [_bank_record(row, index) for index, row in enumerate(bank_rows or [])]
    ledger = [_value_record(row, index) for index, row in enumerate(ledger_rows or [])]
    used_bank: set[int] = set()
    used_ledger: set[int] = set()
    rows: list[dict] = []

    for line in bank:
        candidates = [
            other
            for other in ledger
            if other.index not in used_ledger
            and other.reference
            and _bank_mentions_reference(line.text, other.reference)
        ]
        if len(candidates) > 1:
            amount_candidates = [
                item
                for item in candidates
                if _amount_close(line.amount, item.amount, amount_tolerance)
            ]
            if len(amount_candidates) == 1:
                candidates = amount_candidates
        if len(candidates) > 1:
            used_bank.add(line.index)
            rows.append(
                _pair_row(
                    "review_required",
                    "multiple_candidates",
                    line,
                    None,
                    explanation="More than one accounting entry mentions a matching reference. Choose the correct match manually.",
                )
            )
            continue
        if len(candidates) == 1:
            other = candidates[0]
            status, reason = _bank_pair_status(
                line, other, amount_tolerance, reference_window_days
            )
            used_bank.add(line.index)
            used_ledger.add(other.index)
            rows.append(_pair_row(status, reason, line, other))
            continue

        fuzzy = [
            other
            for other in ledger
            if other.index not in used_ledger
            and _currencies_match(line.currency, other.currency)
            and _amount_close(line.amount, other.amount, amount_tolerance)
            and _date_within(line.date, other.date, fuzzy_window_days)
            and _name_overlap(line.text, other.party)
        ]
        if len(fuzzy) == 1:
            other = fuzzy[0]
            used_bank.add(line.index)
            used_ledger.add(other.index)
            rows.append(_pair_row("review_required", "bank_fuzzy", line, other))
        elif len(fuzzy) > 1:
            used_bank.add(line.index)
            rows.append(
                _pair_row(
                    "review_required",
                    "multiple_candidates",
                    line,
                    None,
                    explanation="Several accounting entries have this amount and a nearby date. Choose the correct match manually.",
                )
            )

    for line in bank:
        if line.index not in used_bank:
            used_bank.add(line.index)
            rows.append(_pair_row("left_only", "no_counterpart", line, None))
    for other in ledger:
        if other.index not in used_ledger:
            used_ledger.add(other.index)
            rows.append(_pair_row("right_only", "no_counterpart", None, other))

    return {"rows": rows, "counts": _count_rows(rows)}
