from __future__ import annotations

import csv
from pathlib import Path

from apps.engine.validators.gstin import gstin_flags


def parse_zoho_file(path: Path, filename: str | None = None) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for line in reader:
            gstin = (
                line.get("GST Identification Number (GSTIN)")
                or line.get("GSTIN")
                or line.get("gstin")
            )
            rows.append(
                {
                    "invoice_number": line.get("Invoice Number") or line.get("invoice_number"),
                    "invoice_date": line.get("Invoice Date") or line.get("invoice_date"),
                    "gst_treatment": line.get("GST Treatment"),
                    "supplier_gstin": gstin,
                    "tax_percent": line.get("Item Tax %"),
                    "invoice_value": _num(line.get("Total") or line.get("invoice_value")),
                    "source": filename or path.name,
                    "flags": gstin_flags(gstin) if gstin else [],
                }
            )
    return {"rows": rows}


def _num(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None
