from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

AMOUNT_RE = re.compile(
    r"(?:₹\s*)?(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{2})(?!\.\d)"
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


def parse_amount(raw: str) -> Decimal | None:
    cleaned = (raw or "").strip().replace("₹", "").replace(" ", "")
    cleaned = re.sub(r"(?i)[()]*\b(?:dr|cr)\.?\s*$", "", cleaned)
    cleaned = cleaned.replace(",", "")
    if not cleaned or cleaned in {".", "-", "--"}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def amounts_in(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    for match in AMOUNT_RE.finditer(text.replace("₹", "")):
        value = parse_amount(match.group(1))
        if value is not None:
            found.append(value)
    return found


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
