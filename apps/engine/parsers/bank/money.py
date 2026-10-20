from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation

# A conservative amount token used by invoice parsing and word-level layout
# code.  It deliberately requires a decimal separator or a grouped number so
# plain account numbers and cheque numbers are not mistaken for money.
_NUMBER_BODY = (
    r"(?:"
    r"\d{1,3}(?:[,\u00a0\u202f ]\d{2,3})+(?:[.,]\d{1,4})?"
    r"|\d{1,3}(?:\.\d{3})+(?:,\d{1,4})?"
    r"|\d+[.,]\d{1,4}"
    r"|\d{1,3}(?:['\u2019]\d{3})+(?:[.,]\d{1,4})?"
    r")"
)
AMOUNT_RE = re.compile(
    r"(?<![\w.])(" + _NUMBER_BODY + r")(?![.,]\d)(?![\w])"
)

_CURRENCY_TOKEN = (
    r"(?:[A-Z]{3}|[\u20b9$\u20ac\u00a3\u00a5\u20a9\u20ba\u20bd\u20a6\u20b1"
    r"\u0e3f\u20ab\u20b4\u20aa\u20a1\u20b2\u20b5\u20b8\u20bc\u20be\u09f3"
    r"\u20a8\ufdfc])"
)

# Full money token including optional sign, currency code/symbol and Dr/Cr
# marker.  ``amount`` is the first and only capturing group.
MONEY_TOKEN_RE = re.compile(
    r"(?<![\w.])"
    r"(?:(?P<open>\()\s*)?"
    r"(?:(?P<drcr_prefix>[Dd][Rr]\.?|[Cc][Rr]\.?)\s*)?"
    r"(?P<sign>[+\-])?"
    r"(?P<prefix>" + _CURRENCY_TOKEN + r")?\s*"
    r"(?P<amount>" + _NUMBER_BODY + r")"
    r"(?![.,]\d)(?![\w])"
    r"\s*(?P<suffix>" + _CURRENCY_TOKEN + r")?"
    r"(?(open)\s*\))"
    r"\s*(?P<drcr>[Dd][Rr]\.?|[Cc][Rr]\.?)?\s*(?P<trailing_sign>-)?"
    r"(?![\w])"
)

DATE_RE = re.compile(
    r"\b("
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|"
    r"\d{1,2}\s*[A-Za-z]{3,9}\.?\s*\d{2,4}"
    r")\b"
)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_ACTIVE_DECIMAL: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "caunpacker_decimal_separator", default=None
)


@contextmanager
def decimal_convention(separator: str | None):
    """Temporarily tell amount parsing which separator is the decimal mark."""
    token = _ACTIVE_DECIMAL.set(separator if separator in {".", ","} else None)
    try:
        yield
    finally:
        _ACTIVE_DECIMAL.reset(token)


def detect_decimal_separator(text: str | None) -> str | None:
    """Find strong decimal-separator evidence in a block of statement text.

    ``1,234.56`` proves a dot decimal mark; ``1.234,56`` proves a comma one.
    A handful of unambiguous one/two digit decimals also counts.  Weak
    three-digit groups are ignored so we do not guess.
    """
    body = str(text or "")
    matches = [match.group("amount") for match in MONEY_TOKEN_RE.finditer(body)]
    for token in matches:
        if "." in token and "," in token:
            return "." if token.rfind(".") > token.rfind(",") else ","
    for token in matches:
        for separator in (".", ","):
            position = token.rfind(separator)
            if position <= 0:
                continue
            tail = token[position + 1 :]
            if tail and len(tail) in {1, 2} and tail.isdigit():
                return separator
    return None


def parse_amount(raw: str, *, decimal_separator: str | None = None) -> Decimal | None:
    """Parse a monetary string without guessing unsafe conventions.

    Supported forms include ``1,234.56``, ``1.234,56``, ``1 234,56``,
    ``-1,234.56``, ``(1,234.56)``, ``1,234.56 Dr`` and amounts with a currency
    code or symbol before/after the number.  A lone three-digit group such as
    ``1,234`` is treated as a thousands group (the long-standing behaviour);
    ``1.234`` is ambiguous and returns ``None`` unless a decimal separator or
    integer zero makes the meaning safe.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")") and len(text) > 2:
        negative = True
        text = text[1:-1].strip()

    text = re.sub(r"(?i)\b(?:dr|cr)\.?\s*$", "", text).strip()
    text = re.sub(r"(?i)^(?:dr|cr)\.?\s*", "", text).strip()

    if text.endswith("-"):
        negative = True
        text = text[:-1].strip()
    if text.startswith("-"):
        negative = True
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()

    # Remove a leading/trailing currency code or symbol.  Only uppercase
    # three-letter codes are stripped so ordinary words are not eaten.
    text = re.sub(rf"^(?:{_CURRENCY_TOKEN})\s*", "", text).strip()
    text = re.sub(rf"\s*(?:{_CURRENCY_TOKEN})$", "", text).strip()

    text = (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace("\u2007", "")
        .replace(" ", "")
        .replace("\u2019", "'")
    )
    if not text or text in {".", ",", "-", "--", "'"}:
        return None
    if not re.fullmatch(r"[0-9.,']+", text):
        return None

    hint = decimal_separator if decimal_separator in {".", ","} else _ACTIVE_DECIMAL.get()
    try:
        value = _parse_number(text, hint)
    except (InvalidOperation, ValueError):
        return None
    if value is None:
        return None
    return -value if negative else value


def _parse_number(text: str, hint: str | None) -> Decimal | None:
    # Apostrophes are always grouping marks.
    text = text.replace("'", "")

    comma_count = text.count(",")
    dot_count = text.count(".")
    if not comma_count and not dot_count:
        if text.isdigit():
            return Decimal(text)
        return None

    if comma_count and dot_count:
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        grouping = "," if decimal == "." else "."
        integer_part, _, fraction = text.rpartition(decimal)
        if not integer_part or not fraction or not fraction.isdigit():
            return None
        if len(fraction) > 4:
            return None
        if not _valid_grouping(integer_part, grouping):
            return None
        return Decimal(integer_part.replace(grouping, "") + "." + fraction)

    separator = "," if comma_count else "."
    count = comma_count or dot_count
    integer_part, _, fraction = text.rpartition(separator)
    if count > 1:
        # Multiple separators can only be grouping marks.
        if not integer_part or not fraction or not fraction.isdigit():
            return None
        if not _valid_grouping(integer_part, separator) or len(fraction) != 3:
            return None
        return Decimal(text.replace(separator, ""))

    if not integer_part or not fraction or not fraction.isdigit():
        return None

    if hint == separator:
        if len(fraction) > 4:
            return None
        return Decimal(integer_part + "." + fraction)

    if hint is not None:
        # The statement has already established the other separator as its
        # decimal mark, so this one can only be a grouping mark.
        if len(fraction) == 3 and _valid_grouping(integer_part, separator):
            return Decimal(text.replace(separator, ""))
        return None

    if len(fraction) in {1, 2}:
        return Decimal(integer_part + "." + fraction)
    if len(fraction) == 4 and integer_part.strip("0") == "":
        return Decimal(integer_part + "." + fraction)
    if len(fraction) == 3:
        if separator == ",":
            # ``1,234`` is overwhelmingly a thousands group in bank
            # statements.  ``1.234`` is genuinely ambiguous.
            return Decimal(integer_part + fraction)
        if integer_part.strip("0") == "":
            return Decimal(integer_part + "." + fraction)
        return None
    return None


def _valid_grouping(integer_part: str, separator: str) -> bool:
    if separator not in integer_part or not integer_part:
        return integer_part.isdigit()
    groups = integer_part.split(separator)
    if not groups or not groups[0].isdigit() or not 1 <= len(groups[0]) <= 3:
        return False
    rest = groups[1:]
    if not rest or any(not group.isdigit() for group in rest):
        return False
    if all(len(group) == 3 for group in rest):
        return True
    # Indian grouping: 12,34,567 or 1,23,456.
    if len(rest[-1]) == 3 and all(len(group) == 2 for group in rest[:-1]):
        return True
    return False


def amounts_in(text: str, *, decimal_separator: str | None = None) -> list[Decimal]:
    found: list[Decimal] = []
    body = str(text or "")
    hint = decimal_separator if decimal_separator in {".", ","} else detect_decimal_separator(body)
    for match in MONEY_TOKEN_RE.finditer(body):
        value = parse_amount(match.group(0), decimal_separator=hint)
        if value is None:
            value = parse_amount(match.group("amount"), decimal_separator=hint)
        if value is not None:
            found.append(value)
    return found


def strip_amount_tokens(text: str) -> str:
    """Remove money tokens from a description while keeping other text."""
    return MONEY_TOKEN_RE.sub(" ", str(text or ""))


def normalize_date(raw: str) -> str:
    text = (raw or "").strip()
    named = re.fullmatch(r"(\d{1,2})\s*([A-Za-z]{3,9})\.?\s*(\d{2,4})", text)
    if named:
        day, month_raw, year = named.groups()
        month = _MONTHS.get(month_raw.lower()[:3])
        if month:
            if len(year) == 2:
                year = f"20{year}"
            return f"{int(year):04d}-{month:02d}-{int(day):02d}"
        return text
    parts = re.split(r"[/\-.]", text)
    if len(parts) != 3:
        return text
    day, month, year = parts
    if not month.isdigit():
        return text
    if len(year) == 2:
        year = f"20{year}"
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def is_plausible_iso_date(value: str) -> bool:
    try:
        year_s, month_s, day_s = value.split("-")
        year, month, day = int(year_s), int(month_s), int(day_s)
    except (TypeError, ValueError):
        return False
    return 1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31
