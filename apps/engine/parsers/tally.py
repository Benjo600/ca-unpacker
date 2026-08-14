from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def parse_tally_file(path: Path, filename: str | None = None) -> dict:
    name = filename or path.name
    if path.suffix.lower() == ".zip":
        rows: list[dict] = []
        with zipfile.ZipFile(path) as archive:
            for inner in archive.namelist():
                if not inner.lower().endswith((".xml", ".txt")):
                    continue
                with archive.open(inner) as handle:
                    rows.extend(_parse_xml(handle.read(), f"{name}:{Path(inner).name}"))
        return {"rows": rows}
    return {"rows": _parse_xml(path.read_bytes(), name)}


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
        rows.append(
            {
                "voucher_type": vtype,
                "voucher_number": _child(voucher, "VOUCHERNUMBER"),
                "date": _pretty_date(_child(voucher, "DATE")),
                "party_name": _child(voucher, "PARTYLEDGERNAME"),
                "gstin": _child(voucher, "PARTYGSTIN") or _child(voucher, "GSTIN"),
                "amount": _amount(_child(voucher, "AMOUNT")),
                "source": source,
                "flags": [],
            }
        )
    return rows


def _child(node: ET.Element, name: str) -> str | None:
    for child in node:
        if child.tag.split("}")[-1].upper() == name and child.text:
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
