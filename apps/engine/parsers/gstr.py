from __future__ import annotations

import json
from pathlib import Path

from apps.engine.validators.gstin import gstin_flags


def parse_gstr_file(path: Path, kind: str, filename: str | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if kind == "gstr_2b":
        rows = _parse_2b(payload, filename or path.name)
    elif kind == "gstr_1":
        rows = _parse_1(payload, filename or path.name)
    else:
        rows = _parse_3b(payload, filename or path.name)
    return {
        "kind": kind,
        "gstin": payload.get("gstin"),
        "period": payload.get("rtnprd") or payload.get("fp") or payload.get("ret_period"),
        "rows": rows,
    }


def _parse_2b(payload: dict, filename: str) -> list[dict]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    docdata = data.get("docdata") if isinstance(data, dict) else {}
    rows: list[dict] = []
    for party in (docdata or {}).get("b2b") or []:
        for inv in party.get("inv") or []:
            gstin = party.get("ctin")
            flags = gstin_flags(gstin)
            rows.append(
                {
                    "gstin": gstin,
                    "trade_name": party.get("trdnm"),
                    "invoice_number": inv.get("inum"),
                    "invoice_date": inv.get("dt"),
                    "invoice_value": inv.get("val"),
                    "taxable": inv.get("txval"),
                    "igst": inv.get("iamt") or 0,
                    "cgst": inv.get("camt") or 0,
                    "sgst": inv.get("samt") or 0,
                    "cess": inv.get("csamt") or 0,
                    "itc_availability": inv.get("itcavl"),
                    "source": filename,
                    "flags": flags,
                }
            )
    return rows


def _parse_1(payload: dict, filename: str) -> list[dict]:
    rows: list[dict] = []
    for party in payload.get("b2b") or []:
        for inv in party.get("inv") or []:
            gstin = party.get("ctin")
            rows.append(
                {
                    "gstin": gstin,
                    "trade_name": party.get("trdnm") or party.get("cname"),
                    "invoice_number": inv.get("inum"),
                    "invoice_date": inv.get("idt") or inv.get("dt"),
                    "invoice_value": inv.get("val"),
                    "taxable": inv.get("txval"),
                    "igst": (inv.get("itms") or [{}])[0].get("itm_det", {}).get("iamt") if inv.get("itms") else inv.get("iamt"),
                    "cgst": inv.get("camt"),
                    "sgst": inv.get("samt"),
                    "hsn": None,
                    "source": filename,
                    "flags": gstin_flags(gstin),
                }
            )
    for item in (payload.get("hsn") or {}).get("data") or []:
        rows.append(
            {
                "gstin": payload.get("gstin"),
                "trade_name": "HSN summary",
                "invoice_number": item.get("hsn_sc"),
                "invoice_date": None,
                "invoice_value": None,
                "taxable": item.get("txval"),
                "igst": item.get("iamt"),
                "cgst": item.get("camt"),
                "sgst": item.get("samt"),
                "hsn": item.get("hsn_sc"),
                "source": f"{filename}#hsn",
                "flags": [],
            }
        )
    return rows


def _parse_3b(payload: dict, filename: str) -> list[dict]:
    details = payload.get("sup_details") or {}
    labels = {
        "osup_det": "Outward taxable (other than zero rated)",
        "osup_zero": "Outward zero rated",
        "osup_nil_exmp": "Nil / exempt",
        "isup_rev": "Inward reverse charge",
        "osup_nongst": "Non-GST outward",
    }
    rows = []
    for key, label in labels.items():
        block = details.get(key)
        if not isinstance(block, dict):
            continue
        rows.append(
            {
                "section": label,
                "taxable": block.get("txval"),
                "igst": block.get("iamt"),
                "cgst": block.get("camt"),
                "sgst": block.get("samt"),
                "cess": block.get("csamt"),
                "source": filename,
                "flags": [],
            }
        )
    if not rows:
        rows.append(
            {
                "section": "GSTR-3B (empty outward block)",
                "taxable": None,
                "igst": None,
                "cgst": None,
                "sgst": None,
                "cess": None,
                "source": filename,
                "flags": [],
            }
        )
    return rows
