"""GST state codes and the UTGST / SGST split.

For a supply where the supplier and the place of supply sit in the *same* Union
Territory **without a legislature**, the second tax is UTGST, not SGST. Delhi,
Puducherry and Jammu & Kashmir are Union Territories too, but each has its own
legislature, so intra-UT supplies there are charged SGST.

The GST portal folds UTGST into the SGST bucket of its JSON, so this module only
classifies a row; it never invents a separate money column.
"""

from __future__ import annotations

import re
from typing import Any

# Official GST state codes 01..38. 25 Daman and Diu is kept for pre-2020 data;
# it was merged into 26 Dadra and Nagar Haveli and Daman and Diu.
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
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (old)",
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
}

# Union Territories that have no legislature: only these charge UTGST.
# Delhi (07), Puducherry (34) and Jammu and Kashmir (01) have legislatures and
# therefore charge SGST, so they are deliberately absent.
UT_WITHOUT_LEGISLATURE: frozenset[str] = frozenset({"04", "26", "31", "35", "38"})

_CODE_IN_TEXT = re.compile(r"(?:^|[^0-9])(\d{1,2})(?=[^0-9]|$)")


def normalise_state_code(value: Any) -> str | None:
    """Return a two-digit state code for a code, int, or 'code - name' text."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) <= 2:
        return text.zfill(2)
    match = _CODE_IN_TEXT.search(text)
    if not match:
        return None
    return match.group(1).zfill(2)


def is_union_territory(code: Any) -> bool:
    """True only when *code* is a Union Territory **without** a legislature."""
    normalised = normalise_state_code(code)
    return normalised in UT_WITHOUT_LEGISLATURE


def state_code_from_gstin(gstin: str | None) -> str | None:
    """First two characters of a GSTIN, but only when they are a known code."""
    if not gstin:
        return None
    text = str(gstin).strip().upper()
    if len(text) < 2:
        return None
    code = text[:2]
    return code if code in STATE_NAMES else None


def state_name(code: Any) -> str | None:
    normalised = normalise_state_code(code)
    if normalised is None:
        return None
    return STATE_NAMES.get(normalised)


def is_intra_utgst(supplier_gstin: str | None, place_of_supply: Any) -> bool:
    """True when supplier state and place of supply are the same UT sans legislature."""
    supplier_code = state_code_from_gstin(supplier_gstin)
    if supplier_code is None or not is_union_territory(supplier_code):
        return False
    pos_code = normalise_state_code(place_of_supply)
    return pos_code == supplier_code
