from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from apps.engine.ocr import extract_image
from apps.engine.parsers.bank.money import AMOUNT_RE, DATE_RE, normalize_date, parse_amount
from apps.engine.pdf_extract import ExtractedPdf, LineBox, extract_pdf
from apps.engine.validators.gstin import find_gstins, gstin_flags, hsn_flags

INV_RE = re.compile(
    r"(?:invoice\s*(?:no|number|#)|inv\.?\s*no)\s*[:.\-]?\s*([A-Z0-9][A-Z0-9/\-]{2,})",
    re.I,
)
HSN_RE = re.compile(r"\b(?:HSN|SAC)\b\s*[:.\-]?\s*(\d{4,8})", re.I)
TOTAL_RE = re.compile(r"(?:invoice\s+value|grand\s+total|total\s+amount|invoice\s+total)\s*[:.\-]?\s*", re.I)
TAXABLE_RE = re.compile(r"taxable(?:\s+value)?\s*[:.\-]?\s*", re.I)
SUPPLIER_NAME_RE = re.compile(
    r"(?:supplier(?:\s+name)?|seller(?:\s+name)?|trade\s+name|from|m/s\.?)\s*[:.\-]?\s*"
    r"([A-Za-z][A-Za-z0-9 .,&'\-]{2,80})",
    re.I,
)
GSTIN_LOOSE_RE = re.compile(r"\b[0-9]{2}[A-Z0-9]{13}\b", re.I)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
_NAME_BLOCK = re.compile(r"^(gstin|hsn|sac|invoice|tax|total|cgst|sgst|igst)\b", re.I)


def parse_invoice_file(path: Path, filename: str | None = None) -> dict:
    path = Path(path)
    extracted = _extract(path)
    text = _joined_text(extracted)
    source = filename or path.name
    row = _build_row(text, extracted.lines, source)
    if row is None:
        return {"rows": [], "engine": extracted.engine, "unreadable": True}
    return {
        "rows": [row],
        "engine": extracted.engine,
        "unreadable": "unreadable" in row["flags"],
    }


def _extract(path: Path) -> ExtractedPdf:
    if path.suffix.lower() in _IMAGE_SUFFIXES:
        return extract_image(path)
    return extract_pdf(path)


def _joined_text(extracted: ExtractedPdf) -> str:
    pages = [page.text for page in extracted.pages if (page.text or "").strip()]
    if pages:
        return "\n".join(pages)
    return "\n".join(line.text for line in extracted.lines if (line.text or "").strip())


def _build_row(text: str, lines: list[LineBox], source: str) -> dict | None:
    gstin = _supplier_gstin(text)
    inv_match = INV_RE.search(text)
    invoice_number = inv_match.group(1).strip() if inv_match else None
    # Prefer zero rows over invented amounts when GSTIN and invoice number are both missing.
    if not gstin and not invoice_number:
        return None

    date_match = DATE_RE.search(text)
    hsn_match = HSN_RE.search(text)
    hsn = hsn_match.group(1) if hsn_match else None
    taxable = _amount_after(TAXABLE_RE, text)
    total = _amount_after(TOTAL_RE, text)
    if total is None:
        amounts = [parse_amount(match.group(1)) for match in AMOUNT_RE.finditer(text)]
        amounts = [amount for amount in amounts if amount is not None]
        total = amounts[-1] if amounts else None
    tax, cgst, sgst, igst = _tax_amounts(text)

    flags = list(gstin_flags(gstin))
    flags.extend(hsn_flags(hsn))
    if taxable is not None and tax is not None and total is not None:
        if abs((taxable + tax) - total) > Decimal("1.00"):
            flags.append("invoice_math")

    fields, field_lines = _locate_fields(
        lines,
        gstin=gstin,
        invoice_number=invoice_number,
        taxable=taxable,
        tax=tax,
        invoice_value=total,
    )
    source_line = field_lines.get("supplier_gstin") or field_lines.get("invoice_number")
    if source_line is None and lines:
        source_line = next((line for line in lines if (line.text or "").strip()), lines[0])
    source_bbox = _union_bbox(list(field_lines.values())) or (_bbox(source_line) if source_line else None)
    source_page = int(source_line.page) if source_line is not None else 1

    thin = gstin is None or invoice_number is None
    if thin and taxable is None and total is None:
        flags.append("unreadable")

    return {
        "supplier_name": _supplier_name(text),
        "supplier_gstin": gstin,
        "invoice_number": invoice_number,
        "invoice_date": normalize_date(date_match.group(1)) if date_match else None,
        "taxable_value": _f(taxable),
        "tax": _f(tax),
        "cgst": _f(cgst),
        "sgst": _f(sgst),
        "igst": _f(igst),
        "invoice_value": _f(total),
        "hsn": hsn,
        "source": source,
        "source_page": source_page,
        "source_bbox": source_bbox,
        "fields": fields,
        "flags": flags,
        "raw_excerpt": " ".join(text.split())[:240],
    }


def _supplier_gstin(text: str) -> str | None:
    found = find_gstins(text)
    if found:
        labeled = re.search(r"supplier\s+gstin\s*[:.\-]?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9])", text, re.I)
        if labeled:
            value = labeled.group(1).upper()
            if value in found:
                return value
        return found[0]
    loose = GSTIN_LOOSE_RE.search(text.upper())
    if loose:
        return loose.group(0).upper()
    return None


def _supplier_name(text: str) -> str | None:
    for match in SUPPLIER_NAME_RE.finditer(text):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
        if not name or _NAME_BLOCK.match(name):
            continue
        if find_gstins(name) or GSTIN_LOOSE_RE.search(name):
            continue
        return name[:120]
    return None


def _tax_amounts(text: str) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    cgst = _amount_after(re.compile(r"\bCGST\b\s*[:.\-]?\s*", re.I), text)
    sgst = _amount_after(re.compile(r"\bSGST\b\s*[:.\-]?\s*", re.I), text)
    igst = _amount_after(re.compile(r"\bIGST\b\s*[:.\-]?\s*", re.I), text)
    parts = [value for value in (cgst, sgst, igst) if value is not None]
    tax = sum(parts, Decimal("0")) if parts else None
    if tax is None:
        tax = _standalone_tax(text)
    return tax, cgst, sgst, igst


def _standalone_tax(text: str) -> Decimal | None:
    for match in re.finditer(r"\b(?:total\s+)?tax(?:\s+amount)?\s*[:.\-]?\s*", text, re.I):
        start = match.start()
        prefix = text[max(0, start - 8) : start].lower()
        if "taxable" in prefix or "invoice" in prefix:
            continue
        tail = text[match.end() : match.end() + 40]
        found = AMOUNT_RE.search(tail)
        if found:
            return parse_amount(found.group(1))
    return None


def _locate_fields(
    lines: list[LineBox],
    *,
    gstin: str | None,
    invoice_number: str | None,
    taxable: Decimal | None,
    tax: Decimal | None,
    invoice_value: Decimal | None,
) -> tuple[dict[str, dict], dict[str, LineBox]]:
    fields: dict[str, dict] = {}
    located: dict[str, LineBox] = {}

    if gstin:
        line = _line_containing(lines, gstin)
        if line is not None:
            located["supplier_gstin"] = line
            fields["supplier_gstin"] = _field(line)

    if invoice_number:
        line = _line_containing(lines, invoice_number)
        if line is None:
            line = _first_matching_line(lines, INV_RE)
        if line is not None:
            located["invoice_number"] = line
            fields["invoice_number"] = _field(line)

    if taxable is not None:
        line = _line_with_amount(lines, taxable, TAXABLE_RE)
        if line is not None:
            located["taxable_value"] = line
            fields["taxable_value"] = _field(line)

    if tax is not None:
        tax_label = re.compile(r"\b(?:CGST|SGST|IGST|total\s+tax|(?<!taxable\s)tax)\b", re.I)
        line = _line_with_amount(lines, tax, tax_label)
        if line is not None:
            located["tax"] = line
            fields["tax"] = _field(line)

    if invoice_value is not None:
        line = _line_with_amount(lines, invoice_value, TOTAL_RE)
        if line is not None:
            located["invoice_value"] = line
            fields["invoice_value"] = _field(line)

    return fields, located


def _line_containing(lines: list[LineBox], needle: str) -> LineBox | None:
    target = needle.upper()
    for line in lines:
        if target in (line.text or "").upper():
            return line
    return None


def _first_matching_line(lines: list[LineBox], pattern: re.Pattern) -> LineBox | None:
    for line in lines:
        if pattern.search(line.text or ""):
            return line
    return None


def _line_with_amount(lines: list[LineBox], value: Decimal, label: re.Pattern) -> LineBox | None:
    labeled: LineBox | None = None
    numbered: LineBox | None = None
    for line in lines:
        text = line.text or ""
        has_amount = _line_has_amount(text, value)
        if label.search(text) and (has_amount or labeled is None):
            labeled = line
            if has_amount:
                return line
        if has_amount and numbered is None:
            numbered = line
    return labeled or numbered


def _line_has_amount(text: str, value: Decimal) -> bool:
    for match in AMOUNT_RE.finditer(text):
        parsed = parse_amount(match.group(1))
        if parsed is not None and parsed == value:
            return True
    return False


def _field(line: LineBox) -> dict:
    return {"page": int(line.page), "bbox": _bbox(line)}


def _bbox(line: LineBox) -> str:
    return f"{line.x:.1f},{line.y:.1f},{line.width:.1f},{line.height:.1f}"


def _union_bbox(lines: list[LineBox]) -> str | None:
    if not lines:
        return None
    x0 = min(line.x for line in lines)
    y0 = min(line.y for line in lines)
    x1 = max(line.x + line.width for line in lines)
    y1 = max(line.y + line.height for line in lines)
    return f"{x0:.1f},{y0:.1f},{x1 - x0:.1f},{y1 - y0:.1f}"


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
