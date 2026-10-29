from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from apps.engine.validators.gstin import gstin_flags, pos_state_code

_PURCHASE = frozenset({"purchase", "purch", "debit note", "debitnote", "dn"})
_SALES = frozenset({"sales", "sale", "credit note", "creditnote", "cn"})

# Ledger name → GST tax head. Cess is checked first in _tax_head, then these in order.
_TAX_LEDGERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("igst", ("igst", "integrated tax")),
    ("cgst", ("cgst", "central tax")),
    ("sgst", ("sgst", "utgst", "state tax", "union territory tax")),
)
_LEDGER_TAGS = frozenset({"ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST"})
_RATE_IN_NAME = re.compile(r"@\s*(\d+(?:\.\d+)?)\s*%")


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
        split = _tax_split(voucher)
        place_of_supply = (
            _child(voucher, "PLACEOFSUPPLY")
            or _child(voucher, "PLACEOFSUPPLYNAME")
            or _child(voucher, "PLACEOFSUPPLYCODE")
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
                "igst": split["igst"],
                "cgst": split["cgst"],
                "sgst": split["sgst"],
                "cess": split["cess"],
                "tax_rate": split["tax_rate"],
                "place_of_supply": place_of_supply,
                "place_of_supply_state": pos_state_code(place_of_supply),
                "document_type": _document_type(vtype),
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


def _tax_split(voucher: ET.Element) -> dict:
    """Read the GST split off a voucher, from ledger entries or explicit voucher tags.

    Returns cgst/sgst/igst/cess (None when the voucher carries no such amount) and a
    tax_rate only when the export states one. Nothing is inferred here.
    """
    split: dict[str, float | None] = {"igst": None, "cgst": None, "sgst": None, "cess": None}
    ledger_rates: dict[str, float] = {}
    for entry in voucher.iter():
        if entry.tag.split("}")[-1].upper() not in _LEDGER_TAGS:
            continue
        name = _child(entry, "LEDGERNAME") or ""
        amount = _amount(_child(entry, "AMOUNT"))
        if amount is None:
            continue
        head = _tax_head(name)
        if head is None:
            continue
        split[head] = round((split[head] or 0.0) + amount, 2)
        rate = _rate_from_name(name)
        if rate is not None and head != "cess":
            ledger_rates[head] = max(ledger_rates.get(head, 0.0), rate)
    # A voucher-level tag (some exports write only these) overrides the ledger scan.
    for head, tags in (
        ("igst", ("IGSTAMOUNT", "IGST")),
        ("cgst", ("CGSTAMOUNT", "CGST")),
        ("sgst", ("SGSTAMOUNT", "SGST", "UTGSTAMOUNT", "UTGST")),
        ("cess", ("CESSAMOUNT", "CESS")),
    ):
        for tag in tags:
            value = _amount(_child(voucher, tag))
            if value is not None:
                split[head] = value
                break
    split["tax_rate"] = _voucher_rate(voucher, ledger_rates)
    return split


def _tax_head(name: str) -> str | None:
    lowered = " ".join((name or "").lower().split())
    if not lowered:
        return None
    if "cess" in lowered:
        return "cess"
    for head, needles in _TAX_LEDGERS:
        if any(needle in lowered for needle in needles):
            return head
    return None


def _rate_from_name(name: str) -> float | None:
    match = _RATE_IN_NAME.search(name or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _voucher_rate(voucher: ET.Element, ledger_rates: dict[str, float]) -> float | None:
    stated = _amount(_child(voucher, "RATE") or _child(voucher, "TAXRATE"))
    if stated is not None:
        return stated
    if "igst" in ledger_rates:
        return round(ledger_rates["igst"], 2)
    if "cgst" in ledger_rates or "sgst" in ledger_rates:
        # Tally prints the two halves separately ("Output CGST @ 9%" + "SGST @ 9%").
        return round(ledger_rates.get("cgst", 0.0) + ledger_rates.get("sgst", 0.0), 2)
    return None


def _document_type(vtype: str | None) -> str:
    text = " ".join((vtype or "").strip().lower().split())
    if "credit note" in text or text in {"cn", "cr"}:
        return "CR"
    if "debit note" in text or text in {"dn", "dr"}:
        return "DR"
    return "INV"


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
