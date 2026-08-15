from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from apps.engine.validators.gstin import gstin_flags

_PURCHASE = frozenset({"purchase", "purch", "debit note", "debitnote", "dn"})
_SALES = frozenset({"sales", "sale", "credit note", "creditnote", "cn"})


def parse_tally_file(path: Path, filename: str | None = None) -> dict:
    """Parse a Tally XML / TXT / ZIP export. Never talks to TallyPrime or ODBC."""
    name = filename or Path(path).name
    try:
        path = Path(path)
        if path.suffix.lower() == ".zip":
            return _parse_zip(path, name)
        raw = path.read_bytes()
    except Exception as exc:
        return {"rows": [], "error": str(exc)}
    return _rows_from_bytes(raw, name)


def _parse_zip(path: Path, name: str) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            rows: list[dict] = []
            for inner in archive.namelist():
                if not inner.lower().endswith((".xml", ".txt")):
                    continue
                try:
                    raw = archive.read(inner)
                except Exception:
                    continue
                source = f"{name}:{Path(inner).name}"
                parsed = _rows_from_bytes(raw, source)
                rows.extend(parsed.get("rows") or [])
            return {"rows": rows}
    except Exception as exc:
        return {"rows": [], "error": str(exc)}


def _rows_from_bytes(raw: bytes, source: str) -> dict:
    if not raw or not raw.strip():
        return {"rows": [], "error": "empty"}
    try:
        return {"rows": _parse_xml(raw, source)}
    except Exception as exc:
        return {"rows": [], "error": str(exc)}


def _parse_xml(raw: bytes, source: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    rows = []
    for voucher in root.iter():
        tag = voucher.tag.split("}")[-1].upper()
        if tag != "VOUCHER":
            continue
        vtype = voucher.attrib.get("VCHTYPE") or _child(voucher, "VOUCHERTYPENAME")
        voucher_number = _child(voucher, "VOUCHERNUMBER")
        invoice_number = (
            _child(voucher, "REFERENCE")
            or _child(voucher, "BASICINVOICENUMBER")
            or voucher_number
        )
        party_name = _child(voucher, "PARTYLEDGERNAME") or _child(voucher, "PARTYNAME")
        gstin = _child(voucher, "PARTYGSTIN") or _child(voucher, "GSTIN")
        date = _pretty_date(_child(voucher, "DATE"))
        amount = _amount(_child(voucher, "AMOUNT") or _deep(voucher, "AMOUNT"))
        hsn = _child(voucher, "HSNCODE") or _child(voucher, "HSN") or _deep(voucher, "HSNCODE")
        taxable = _amount(
            _child(voucher, "TAXABLEVALUE")
            or _child(voucher, "ASSESSABLEVALUE")
            or _deep(voucher, "TAXABLEVALUE")
        )
        tax = _amount(
            _child(voucher, "TAXAMOUNT")
            or _child(voucher, "VCHTAXAMOUNT")
            or _deep(voucher, "TAXAMOUNT")
        )
        rows.append(
            {
                "register": _register(vtype),
                "supplier_name": party_name,
                "party_name": party_name,
                "supplier_gstin": gstin,
                "gstin": gstin,
                "invoice_number": invoice_number,
                "invoice_date": date,
                "taxable_value": taxable,
                "tax": tax,
                "invoice_value": amount,
                "hsn": hsn,
                "flags": gstin_flags(gstin) if gstin else [],
                "source": source,
                "voucher_type": vtype,
                "voucher_number": voucher_number,
                "date": date,
                "amount": amount,
            }
        )
    return rows


def _register(vtype: str | None) -> str:
    text = " ".join((vtype or "").strip().lower().split())
    compact = text.replace(" ", "")
    first = text.split(" ", 1)[0] if text else ""
    if text in _PURCHASE or compact in _PURCHASE or first in {"purchase", "purch"}:
        return "purchase"
    if text in _SALES or compact in _SALES or first in {"sales", "sale"}:
        return "sales"
    return "other"


def _child(node: ET.Element, name: str) -> str | None:
    want = name.upper()
    for child in node:
        if child.tag.split("}")[-1].upper() == want and child.text:
            return child.text.strip()
    return None


def _deep(node: ET.Element, name: str) -> str | None:
    want = name.upper()
    for child in node.iter():
        if child is node:
            continue
        if child.tag.split("}")[-1].upper() == want and child.text and child.text.strip():
            return child.text.strip()
    return None


def _pretty_date(raw: str | None) -> str | None:
    if not raw:
        return None
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _amount(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return abs(float(raw.replace(",", "")))
    except ValueError:
        return None
