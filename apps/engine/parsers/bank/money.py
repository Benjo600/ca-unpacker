from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

AMOUNT_RE = re.compile(
    r"(?:₹\s*)?(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+\.\d{2})(?!\.\d)"
)
DATE_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")


def parse_amount(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace("₹", "").replace(" ", "")
    cleaned = cleaned.replace(",", "")
    if not cleaned:
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
    parts = re.split(r"[/\-.]", raw.strip())
    if len(parts) != 3:
        return raw.strip()
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
