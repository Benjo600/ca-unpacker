from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from apps.engine.parsers.bank.money import AMOUNT_RE, DATE_RE, normalize_date, parse_amount
from apps.engine.pdf_extract import extract_pdf
from apps.engine.validators.gstin import find_gstins, gstin_flags, hsn_flags

INV_RE = re.compile(
    r"(?:invoice\s*(?:no|number|#)|inv\.?\s*no)\s*[:.\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,})",
    re.I,
)
HSN_RE = re.compile(r"\bHSN\b\s*[:.\-]?\s*(\d{4,8})", re.I)
TOTAL_RE = re.compile(r"(?:invoice\s+value|grand\s+total|total\s+amount|invoice\s+total)\s*[:.\-]?\s*", re.I)
TAXABLE_RE = re.compile(r"taxable(?:\s+value)?\s*[:.\-]?\s*", re.I)


def parse_invoice_file(path: Path, filename: str | None = None) -> dict:
    extracted = extract_pdf(path)
    text = "\n".join(page.text for page in extracted.pages)
    gstins = find_gstins(text)
    supplier = gstins[0] if gstins else None
    inv = INV_RE.search(text)
    date_match = DATE_RE.search(text)
    hsn_match = HSN_RE.search(text)
    taxable = _amount_after(TAXABLE_RE, text)
    total = _amount_after(TOTAL_RE, text)
    if total is None:
        amounts = [parse_amount(m.group(1)) for m in AMOUNT_RE.finditer(text)]
        amounts = [a for a in amounts if a is not None]
        total = amounts[-1] if amounts else None

    tax = None
    for label in ("CGST", "SGST", "IGST"):
        found = _amount_after(re.compile(rf"{label}\s*[:.\-]?\s*", re.I), text)
        if found is not None:
            tax = (tax or Decimal("0")) + found

    flags = gstin_flags(supplier) if supplier else ["gstin_missing"]
    flags.extend(hsn_flags(hsn_match.group(1) if hsn_match else None))
    if taxable is not None and tax is not None and total is not None:
        if abs((taxable + tax) - total) > Decimal("1.00"):
            flags.append("invoice_math")

    row = {
        "supplier_gstin": supplier,
        "invoice_number": inv.group(1) if inv else None,
        "invoice_date": normalize_date(date_match.group(1)) if date_match else None,
        "taxable_value": _f(taxable),
        "tax": _f(tax),
        "invoice_value": _f(total),
        "hsn": hsn_match.group(1) if hsn_match else None,
        "source": filename or path.name,
        "source_page": 1,
        "flags": flags,
        "raw_excerpt": " ".join(text.split())[:240],
    }
    return {"rows": [row], "engine": extracted.engine}


def _amount_after(pattern: re.Pattern, text: str) -> Decimal | None:
    match = pattern.search(text)
    if not match:
        return None
    tail = text[match.end() : match.end() + 40]
    found = AMOUNT_RE.search(tail)
    if not found:
        return None
    return parse_amount(found.group(1))


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
