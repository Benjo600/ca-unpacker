from __future__ import annotations

import re

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")
GSTIN_FIND = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b", re.I)
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def find_gstins(text: str) -> list[str]:
    return [match.group(0).upper() for match in GSTIN_FIND.finditer(text.upper())]


def gstin_checksum_ok(gstin: str) -> bool:
    value = (gstin or "").strip().upper()
    if not GSTIN_RE.match(value):
        return False
    factor = 1
    total = 0
    for char in value[:14]:
        code = CHARS.index(char)
        product = factor * code
        factor = 2 if factor == 1 else 1
        total += product // 36 + product % 36
    check = (36 - (total % 36)) % 36
    return CHARS[check] == value[14]


def gstin_flags(gstin: str | None) -> list[str]:
    if not gstin:
        return ["gstin_missing"]
    value = gstin.strip().upper()
    if not GSTIN_RE.match(value):
        return ["gstin_format"]
    if not gstin_checksum_ok(value):
        return ["gstin_checksum"]
    return []


def hsn_flags(hsn: str | None) -> list[str]:
    if not hsn:
        return []
    digits = re.sub(r"\D", "", hsn)
    if digits and len(digits) not in {4, 6, 8}:
        return ["hsn_length"]
    return []
