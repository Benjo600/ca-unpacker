from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

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

_DATE_BODY = (
    r"\d{4}-\d{1,2}-\d{1,2}"
    r"|"
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|"
    r"\d{1,2}[.\s]*[A-Za-z]{3,9}\.?\s*\d{2,4}"
)
DATE_RE = re.compile(r"\b(" + _DATE_BODY + r")\b")
# OCR can append exactly one stray digit to a date token ("07/07/20261 UPI
# ...").  DATE_RE needs a word boundary and misses that row, which is how two
# printed transactions get merged into one amount.  This weaker form accepts a
# single trailing digit followed by a break; a longer reference number
# ("...2026123") still cannot match.
DATE_GLUED_TAIL_RE = re.compile(r"\b(" + _DATE_BODY + r")(?=\d(?:\s|$))")
# A whole date token, including the optional glued digit, for token filtering.
DATE_TOKEN_RE = re.compile(r"(?:" + _DATE_BODY + r")\d?")


def date_match(text: str) -> re.Match | None:
    """Find a date token, tolerating one OCR-glued digit on its tail.

    A scanned row such as ``07/07/20261 UPI merchant ...`` is a real
    transaction whose date kept one stray OCR digit.  Plain ``DATE_RE`` needs
    a word boundary and misses it, so the row is never treated as a new
    transaction and its amounts are folded into the row above.  Callers that
    only need the dated value can read ``group(1)``: it is the clean date in
    both forms.
    """
    body = str(text or "")
    match = DATE_RE.search(body)
    if match is not None:
        return match
    return DATE_GLUED_TAIL_RE.search(body)


def remove_first_date(text: str) -> str:
    """Remove the first date token (and any digit glued to its tail)."""
    body = str(text or "")
    match = date_match(body)
    if match is None:
        return body
    end = match.end()
    if end < len(body) and body[end].isdigit():
        # The OCR-glued tail digit belongs to the date token, not the text.
        end += 1
    return body[: match.start()] + body[end:]


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

# OCR look-alike digit substitutions.  Applied only when a token otherwise
# fails to parse, only when the repaired text is fully numeric, and always
# reported back to the caller so the repair can be flagged for review.
# Mapping is deliberately limited to the strongest typographic confusions in
# financial documents (Phase 7): 0/O, 1/I/l, 5/S, 8/B, 2/Z.
_OCR_DIGIT_FIXES = {
    "O": "0", "o": "0", "D": "0", "Q": "0",
    "I": "1", "i": "1", "l": "1", "|": "1", "!": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "B": "8",
}

_DRCR_SUFFIX_RE = re.compile(r"(?i)(?:^|[\s(])([Dd][Rr]|[Cc][Rr])\.?(?=[\s)|]|$)")


class AmountEvidence(NamedTuple):
    """What an amount parse actually saw — original text, value, repairs."""

    raw: str
    value: Decimal | None
    repaired_from: str | None = None
    drcr: str | None = None

    @property
    def repaired(self) -> bool:
        return self.repaired_from is not None


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
    candidate, negative = _numeric_candidate(text)
    if not candidate or candidate in {".", ",", "-", "--", "'"}:
        return None
    if not re.fullmatch(r"[0-9.,']+", candidate):
        return None

    hint = decimal_separator if decimal_separator in {".", ","} else _ACTIVE_DECIMAL.get()
    try:
        value = _parse_number(candidate, hint)
    except (InvalidOperation, ValueError):
        return None
    if value is None:
        return None
    return -value if negative else value


def _numeric_candidate(raw: str) -> tuple[str, bool]:
    """Reduce an amount token to its numeric body plus a negative flag."""
    text = str(raw).strip()
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

    # Remove a leading/trailing currency code or symbol.  Symbols are
    # unambiguous; a three-letter alphabetic token is only stripped when it is
    # a *known* ISO currency code, so OCR'd digits like ``2OOO`` are never
    # eaten as a fake "OOO currency".
    text = _strip_currency_edges(text)

    text = (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace("\u2007", "")
        .replace(" ", "")
        .replace("\u2019", "'")
    )
    return text, negative


def _strip_currency_edges(text: str) -> str:
    match = re.match(rf"^({_CURRENCY_TOKEN})\s*", text)
    if match and _currency_token_ok(match.group(1)):
        text = text[match.end():]
    match = re.search(rf"\s*({_CURRENCY_TOKEN})$", text)
    if match and _currency_token_ok(match.group(1)):
        text = text[: match.start()].strip()
    return text


def _currency_token_ok(token: str) -> bool:
    """Symbols pass; three-letter codes must be real ISO currencies."""
    if not token.isalpha():
        return True
    from apps.engine.currency import is_known

    return is_known(token.upper())


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
        # Multiple separators can only be grouping marks: the whole token is a
        # grouped integer (the trailing group is the last group of the number,
        # not a decimal fraction).  Validate the full grouping so Indian
        # ``12,34,567`` and ``1,00,000`` parse; ``4821,355`` (4-digit head)
        # still fails.
        if not _valid_grouping(text, separator):
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


def normalize_date(raw: str, default_year: int | str | None = None) -> str:
    text = (raw or "").strip()
    named = re.fullmatch(r"(\d{1,2})[.\s]*([A-Za-z]{3,9})\.?\s*(\d{2,4})?", text)
    if named:
        day, month_raw, year = named.groups()
        month = _MONTHS.get(month_raw.lower()[:3])
        if month:
            if not year and default_year:
                year = str(default_year)
            if year:
                if len(year) == 2:
                    year = f"20{year}"
                return f"{int(year):04d}-{month:02d}-{int(day):02d}"
        return text
    if is_plausible_iso_date(text):
        return text
    parts = re.split(r"[/\-.]", text)
    if len(parts) != 3:
        return text
    if len(parts[0]) == 4 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
        year, month, day = parts
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    day, month, year = parts
    if not month.isdigit() or not day.isdigit() or not year.isdigit():
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


def repair_ocr_digits(text: str) -> str | None:
    """Repair OCR digit confusions (0/O, 1/I/l, 5/S, 8/B, …) conservatively.

    Returns the repaired string only when the result fully parses as an amount
    (signs, parentheses, grouping and decimals all included — :func:`parse_amount`
    is the validator, so the repair never invents a format); otherwise ``None``.
    A token like ``1O5,OOO.OO`` becomes ``105,000.00``; a word like ``TOTAL``
    is never touched (no digits to repair around, and the parse check fails).
    """
    if not text or not any(ch.isdigit() for ch in text):
        # Pure words, or words with a single stray letter: not an amount.
        return None
    candidate = "".join(_OCR_DIGIT_FIXES.get(ch, ch) for ch in text)
    candidate = candidate.replace(" ", "")
    if not re.fullmatch(r"[0-9.,'()\-\u00a0]+", candidate):
        return None
    if "." not in candidate and "," not in candidate:
        # A repaired plain integer (``12AB3`` → ``12483``) is far more likely
        # a cheque or reference number than an amount: refuse to guess.
        return None
    try:
        if parse_amount(candidate) is None:
            return None
    except (InvalidOperation, ValueError):
        return None
    return candidate


def parse_amount_with_evidence(
    raw: str,
    *,
    decimal_separator: str | None = None,
    allow_ocr_repair: bool = True,
) -> AmountEvidence:
    """Parse an amount and report what happened, including OCR repairs.

    ``value is None`` means unparseable.  ``repaired_from`` is set when an OCR
    digit confusion had to be fixed (0/O, 1/I, 5/S, 8/B …) — callers must flag
    such rows for review rather than silently trusting the repair.
    """
    text = str(raw or "").strip()
    if not text:
        return AmountEvidence(raw=text, value=None)
    value = parse_amount(text, decimal_separator=decimal_separator)
    if value is not None:
        return AmountEvidence(raw=text, value=value, drcr=_drcr_of(text))
    if not allow_ocr_repair:
        return AmountEvidence(raw=text, value=None, drcr=_drcr_of(text))
    candidate, negative = _numeric_candidate(text)
    repaired = repair_ocr_digits(candidate)
    if repaired is None:
        return AmountEvidence(raw=text, value=None, drcr=_drcr_of(text))
    if negative and not (repaired.startswith("-") or repaired.startswith("(")):
        # The parentheses/sign markers were consumed by the candidate strip;
        # put them back so the repaired value keeps its direction.
        repaired = f"({repaired})"
    value = parse_amount(repaired, decimal_separator=decimal_separator)
    if value is None:
        return AmountEvidence(raw=text, value=None, drcr=_drcr_of(text))
    return AmountEvidence(raw=text, value=value, repaired_from=text, drcr=_drcr_of(text))


def _drcr_of(text: str) -> str | None:
    """Detect a Dr/Cr marker on an amount token ('25,000 Dr', 'Cr 500.00')."""
    if not text:
        return None
    matches = _DRCR_SUFFIX_RE.findall(text)
    if not matches:
        return None
    directions = {match.lower() for match in matches}
    if len(directions) == 1:
        return "dr" if "d" in next(iter(directions)) else "cr"
    return None


def drcr_amounts_in(text: str) -> list[tuple[int, Decimal, str]]:
    """Annotated amounts in a line: [(token_index, value, 'dr'|'cr'), …].

    Used as directional evidence: ``NEFT 25,000 Dr 975,000`` says the 25,000
    is a debit.  Only tokens that actually carry a Dr/Cr marker are returned.
    """
    found: list[tuple[int, Decimal, str]] = []
    body = str(text or "")
    hint = detect_decimal_separator(body)
    for index, match in enumerate(MONEY_TOKEN_RE.finditer(body)):
        direction = _drcr_of(match.group("drcr_prefix") or "") or _drcr_of(match.group("drcr") or "")
        if not direction:
            continue
        value = parse_amount(match.group(0), decimal_separator=hint)
        if value is None:
            value = parse_amount(match.group("amount"), decimal_separator=hint)
        if value is not None:
            found.append((index, value, direction))
    return found


_DRCR_GLUED_RE = re.compile(r"(?P<marker>[Dd][Rr]|[Cc][Rr])\.?(?=\s|$|[),;])")


def annotated_directions(text: str) -> list[tuple[Decimal, str, int]]:
    """All Dr/Cr-annotated amounts in a line: [(value, 'dr'|'cr', start)].

    Handles both spaced (``25,000 Dr``) and glued (``5,000.00Dr``) markers.
    A marker only counts when the text immediately before it ends in a real
    *money* token (grouped or decimal — a bare reference number like
    ``REF 12345 DR`` never counts), so titles like ``Dr. Smith`` or the word
    ``CREDIT`` never match either.
    """
    out: list[tuple[Decimal, str, int]] = []
    body = str(text or "")
    hint = detect_decimal_separator(body)
    for match in _DRCR_GLUED_RE.finditer(body):
        prefix = body[: match.start()].rstrip()
        number = re.search(r"(\d[\d,.\u00a0\u202f ']*)$", prefix)
        if not number:
            continue
        token = number.group(1).strip()
        if not re.fullmatch(_NUMBER_BODY, token):
            # A bare integer before Dr/Cr is most likely a reference number
            # (``REF 12345 DR``); using it as the transaction amount would
            # override the real positional evidence.
            continue
        value = parse_amount(f"{token} {match.group('marker')}.", decimal_separator=hint)
        if value is not None:
            out.append((value.copy_abs(), match.group("marker").lower(), match.start()))
    return out


def annotated_txn_direction(text: str) -> tuple[str, Decimal] | None:
    """(direction, value) when a line's printed Dr/Cr marker identifies its
    transaction amount, else ``None``.

    A marker that follows the *last* money token most likely annotates the
    balance column (``975,000 Dr`` for a debit balance), so it is ignored for
    transaction direction.  Conflicting markers on the same line are treated
    as no evidence.
    """
    annotations = annotated_directions(text)
    if not annotations:
        return None
    directions = {direction for _value, direction, _start in annotations}
    if len(directions) != 1:
        # Conflicting printed evidence (``25,000 Dr 25,000 Cr``) is not a
        # guess: refuse and let the positional heuristics decide.
        return None
    token_starts = [match.start() for match in MONEY_TOKEN_RE.finditer(str(text or ""))]
    last_token_start = token_starts[-1] if token_starts else None
    txn = [
        (value, direction, start)
        for value, direction, start in annotations
        if last_token_start is None or start < last_token_start or len(token_starts) == 1
    ]
    if not txn:
        return None
    direction = next(iter(directions))
    value = txn[-1][0]
    return direction, value
