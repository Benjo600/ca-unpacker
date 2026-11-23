"""Shared money and date parsing for the reconciliation engines.

Both :mod:`apps.engine.recon` (GST portal vs books) and
:mod:`apps.engine.recon_engine` (bank vs ledger) used to carry their own copy
of the money and date helpers.  The copies drifted: the same string could be
read as two different amounts or dates depending on which engine saw it.  This
module is the single source of truth; the engine modules keep their public
names as thin wrappers so existing imports and call sites are unchanged.

Guiding rule: read only what is unambiguous.  Where the old copies disagreed,
the stricter reading wins -- when a value is not clearly a number or a date the
helpers return ``None`` instead of guessing at one.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

#: Accepted date layouts, tried in order.  Unambiguous, explicit formats only.
#: ``dd-mm-yyyy`` style values are day-first (Indian accounting convention).
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y%m%d",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d/%b/%Y",
    "%d %B %Y",
    "%b %d, %Y",
)

# Decorations that carry no numeric meaning: currency markers and the
# accounting Dr/Cr suffixes.  Removed only as whole tokens, so stray text like
# "abc123" is still rejected rather than mined for digits.
_CURRENCY_TOKENS = re.compile(
    r"(?<![A-Za-z])(?:rs|inr|usd|dr|cr)\.?(?![A-Za-z])",
    re.IGNORECASE,
)
_NOISE_CHARS = str.maketrans("", "", "₹$, \t\r\n\u00a0")
_DATE_SPLIT = re.compile(r"[/\-.]")

__all__ = [
    "DATE_FORMATS",
    "parse_date_value",
    "parse_money_value",
]


def parse_money_value(value: Any) -> Decimal | None:
    """Return ``value`` as a :class:`~decimal.Decimal`, or ``None``.

    Accepts ``Decimal``/``int``/``float`` and rupee-style strings such as
    ``"₹1,177.74"``, ``"1177.74 Dr"`` or ``"(500)"``.  ``None`` is returned for
    blanks, booleans, non-finite numbers and anything the parser cannot read
    without guessing (for example ``"abc123"``).
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value)) if math.isfinite(value) else None

    text = str(value).strip()
    if not text:
        return None

    # Accounting negatives: "(1,177.74)" means -1177.74.
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    text = _CURRENCY_TOKENS.sub("", text)
    text = text.translate(_NOISE_CHARS)
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    if negative and number > 0:
        number = -number
    return number


def parse_date_value(value: Any) -> date | None:
    """Return ``value`` as a :class:`~datetime.date`, or ``None``.

    Accepts ``date``/``datetime`` objects, ISO and day-first numeric strings
    (``"2026-07-12"``, ``"12-07-2026"``, ``"12/07/2026"``), month-name layouts
    and ISO timestamps.  Ambiguous or unreadable values return ``None``; a bare
    number is not treated as a date.
    """
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
    if " " in text and re.match(r"^\d{4}-\d{2}-\d{2} ", text):
        text = text.split(" ", 1)[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parts = _DATE_SPLIT.split(text)
    if len(parts) == 3 and all(parts):
        try:
            first, second, third = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if first > 31:
            year, month, day = first, second, third
        else:
            day, month, year = first, second, third
            if year < 100:
                year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None
