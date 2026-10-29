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


def gstin_state(gstin: str | None) -> str | None:
    """Return the two-digit state code of a GSTIN, or None if it is not shaped like one."""
    value = (gstin or "").strip().upper()
    if not GSTIN_RE.match(value):
        return None
    return value[:2]


# GST state codes (as printed on the portal's place-of-supply dropdown).
STATE_NAMES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
}

_STATE_BY_NAME: dict[str, str] = {
    " ".join(name.lower().split()): code for code, name in STATE_NAMES.items()
}
_STATE_ALIASES: dict[str, str] = {
    "orissa": "21",
    "uttaranchal": "05",
    "pondicherry": "34",
    "dadra and nagar haveli": "26",
    "daman and diu": "26",
    "andaman and nicobar": "35",
    "jammu & kashmir": "01",
    "other territory": "97",
}
_STATE_PREFIX = re.compile(r"^(\d{2})(?:\D|$)")


def pos_state_code(value: str | None) -> str | None:
    """Normalise a place-of-supply to its two-digit state code ("27-Maharashtra", "Maharashtra", "27")."""
    text = str(value or "").strip()
    if not text:
        return None
    head = _STATE_PREFIX.match(text)
    if head and head.group(1) in STATE_NAMES:
        return head.group(1)
    key = " ".join(text.lower().replace("&", "and").split())
    if key in _STATE_BY_NAME:
        return _STATE_BY_NAME[key]
    return _STATE_ALIASES.get(key)


def hsn_flags(hsn: str | None) -> list[str]:
    if not hsn:
        return []
    digits = re.sub(r"\D", "", hsn)
    if digits and len(digits) not in {4, 6, 8}:
        return ["hsn_length"]
    return []
