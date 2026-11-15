"""Shared Excel formatting for customer-facing packs.

Phase 12 quality bar: Indian currency formatting where the document is
Indian, red negatives everywhere, hard guards so a huge import raises a
clear error instead of silently overflowing Excel's row limit.
"""

from __future__ import annotations

# Excel's hard worksheet limit is 1,048,576 rows; leave the header row.
MAX_SHEET_ROWS = 1_048_575

# Indian lakh/crore grouping with ₹, mirroring the reconciliation report.
INR_MONEY_FORMAT = '[>=10000000]"₹"##\\,##\\,##\\,##0.00;[>=100000]"₹"##\\,##\\,##0.00;"₹"##\\,##0.00'
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
