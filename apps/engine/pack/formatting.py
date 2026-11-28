"""Shared Excel formatting for customer-facing packs.

Phase 12 quality bar: Indian currency formatting where the document is
Indian, red negatives everywhere, hard guards so a huge import raises a
clear error instead of silently overflowing Excel's row limit.

Two more things live here because every pack needs them and they must behave
the same in all of them:

* ``plural`` — so a cover never says "1 row(s)";
* ``parse_date_value`` — so a register shows a real date, DD-MM-YYYY, and
  never invents one from a value it cannot read.
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Excel's hard worksheet limit is 1,048,576 rows; leave the header row.
MAX_SHEET_ROWS = 1_048_575

# Indian lakh/crore grouping with ₹, mirroring the reconciliation report.
INR_MONEY_FORMAT = '[>=10000000]"₹"##\\,##\\,##\\,##0.00;[>=100000]"₹"##\\,##\\,##\\,##0.00;"₹"##,##0.00'
FOREIGN_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AED": "AED ", "AUD": "A$"}


def currency_of_rows(rows: list[dict]) -> str | None:
    """The single currency used across rows, when every row agrees."""
    codes: set[str] = set()
    for row in rows or []:
        for key in ("currency_code", "currency"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                codes.add(value.strip().upper())
        code = row.get("currency_code")
        if isinstance(code, str) and code.strip():
            codes.add(code.strip().upper())
    if not codes or codes - {"INR", ""} == set():
        return "INR" if codes else None
    if len(codes) == 1:
        return next(iter(codes))
    return None


def money_format(rows: list[dict]) -> str:
    """Number format string for a sheet's money columns.

    INR (or unmarked) data gets Indian lakh/crore grouping with the ₹ symbol;
    a consistent foreign currency gets its own symbol with standard grouping;
    mixed currencies stay neutral so nothing is mislabelled.
    """
    currency = currency_of_rows(rows)
    if currency in (None, "INR"):
        return INR_MONEY_FORMAT
    symbol = FOREIGN_SYMBOLS.get(currency)
    if not symbol:
        return "#,##0.00;[Red]-#,##0.00"
    return f'"{symbol}"#,##0.00;[Red]-"{symbol}"#,##0.00'


def guard_sheet_capacity(rows: list[dict], label: str) -> None:
    """Refuse to write more rows than Excel supports instead of truncating."""
    count = len(rows or [])
    if count > MAX_SHEET_ROWS:
        raise ValueError(
            f"{label} produced {count:,} rows. Excel supports at most "
            f"{MAX_SHEET_ROWS:,} data rows per sheet. Split the export into "
            "smaller periods and re-import."
        )


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """``7 rows`` / ``1 row`` — never ``1 row(s)``.

    The plural is regular unless a caller supplies one ("entry"/"entries").
    """
    number = int(count or 0)
    word = singular if number == 1 else (plural_form or f"{singular}s")
    return f"{number:,} {word}"


# --- dates -----------------------------------------------------------------
# A register column is treated as a date column by its key, so the writer never
# has to guess from the value.
DATE_KEYS = frozenset(
    {
        "date",
        "invoice_date",
        "voucher_date",
        "document_date",
        "bill_date",
        "posting_date",
        "payment_date",
        "entry_date",
        "due_date",
        "baseline_date",
        "clearing_date",
        "value_date",
        "period_from",
        "period_to",
    }
)

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
_DMY_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DMY_DASH = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")
_DMY_DASHED_MONTH = re.compile(
    r"^(\d{1,2})[-/ ]([A-Za-z]{3,9})[-/ ](\d{4})$",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_date_value(value) -> date | None:
    """A real date for a date-looking value, or ``None`` when it is not safe.

    Accepted:

    * a date or datetime object;
    * ISO ``YYYY-MM-DD`` (a time suffix is dropped);
    * ``DD/MM/YYYY`` — the Indian day-first convention, taken as written;
    * ``DD-MM-YYYY`` only when the day and month cannot be swapped;
    * ``12-Jul-2026`` / ``12 July 2026``.

    ``05-07-2026`` with dashes stays text: a wrong month on a GST invoice is
    worse than a string that still reads exactly as it was received.  Anything
    that matches no known shape is returned untouched by the caller.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    match = _ISO.match(text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    # DD/MM/YYYY: day first, the way Indian source documents write a date.
    match = _DMY_SLASH.match(text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        return _safe_date(year, month, day)

    # DD-MM-YYYY: only when the numbers force one reading.
    match = _DMY_DASH.match(text)
    if match:
        first, second, year = (int(part) for part in match.groups())
        day, month = _day_month(first, second)
        if day is None:
            return None
        return _safe_date(year, month, day)

    match = _DMY_DASHED_MONTH.match(text)
    if match:
        day = int(match.group(1))
        month = _MONTHS.get(match.group(2).lower()[:4]) or _MONTHS.get(
            match.group(2).lower()
        )
        if month is None:
            return None
        return _safe_date(int(match.group(3)), month, day)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _day_month(first: int, second: int) -> tuple[int, int] | tuple[None, None]:
    """Resolve a day/month pair only when the answer cannot be swapped."""
    if first > 12 and second <= 12:
        return first, second
    if second > 12 and first <= 12:
        return second, first
    if first == second:
        return first, second
    return None, None
