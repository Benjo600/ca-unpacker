from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.engine.validators.gstin import gstin_flags

_SUP_3B = {
    "osup_det": "Outward taxable (other than zero rated)",
    "osup_zero": "Outward zero rated",
    "osup_nil_exmp": "Nil / exempt",
    "isup_rev": "Inward reverse charge",
    "osup_nongst": "Non-GST outward",
}


def parse_gstr_file(path: Path, kind: str, filename: str | None = None) -> dict:
    path = Path(path)
    name = filename or path.name
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return {"kind": kind, "rows": [], "error": "not valid JSON"}
    if not isinstance(payload, dict):
        return {"kind": kind, "rows": [], "error": "not valid JSON"}
    if kind == "gstr_2b":
        rows = _parse_2b(payload, name)
    elif kind == "gstr_1":
        rows = _parse_1(payload, name)
    else:
        rows = _parse_3b(payload, name)
    return {
        "kind": kind,
        "gstin": payload.get("gstin"),
        "period": payload.get("rtnprd") or payload.get("fp") or payload.get("ret_period"),
        "rows": rows,
    }


def _parse_2b(payload: dict, filename: str) -> list[dict]:
    docdata = _docdata_2b(payload)
    rows: list[dict] = []
    for pi, party in enumerate(_list(docdata.get("b2b"))):
        for ii, inv in enumerate(_party_docs(party, ("inv",))):
            rows.append(
                _invoice_row(
                    party,
                    inv,
                    document_type="B2B",
                    source=f"{filename}#2b.b2b[{pi}].inv[{ii}]",
                )
            )
    for pi, party in enumerate(_list(docdata.get("cdnr"))):
        for ii, note in enumerate(_party_docs(party, ("nt", "inv"))):
            rows.append(
                _invoice_row(
                    party,
                    note,
                    document_type=_cdn_type(note),
                    source=f"{filename}#2b.cdnr[{pi}].nt[{ii}]",
                )
            )
    return rows


def _parse_1(payload: dict, filename: str) -> list[dict]:
    root = _gstr1_root(payload)
    rows: list[dict] = []
    for section, dtype in (("b2b", "B2B"), ("b2ba", "B2BA")):
        for pi, party in enumerate(_list(root.get(section))):
            for ii, inv in enumerate(_party_docs(party, ("inv",))):
                rows.append(
                    _invoice_row(
                        party,
                        inv,
                        document_type=dtype,
                        source=f"{filename}#1.{section}[{pi}].inv[{ii}]",
                    )
                )
    for section in ("cdnr", "cdnra"):
        for pi, party in enumerate(_list(root.get(section))):
            for ii, note in enumerate(_party_docs(party, ("nt", "inv"))):
                rows.append(
                    _invoice_row(
                        party,
                        note,
                        document_type=_cdn_type(note),
                        source=f"{filename}#1.{section}[{pi}].nt[{ii}]",
                    )
                )
    hsn_block = root.get("hsn") if isinstance(root.get("hsn"), dict) else {}
    for i, item in enumerate(_list((hsn_block or {}).get("data"))):
        code = item.get("hsn_sc")
        taxes = _doc_taxes(item)
        rows.append(
            _base_row(
                gstin=payload.get("gstin") or root.get("gstin"),
                trade_name="HSN summary",
                invoice_number=code,
                invoice_date=None,
                invoice_value=item.get("val"),
                taxable=taxes["taxable"],
                igst=taxes["igst"],
                cgst=taxes["cgst"],
                sgst=taxes["sgst"],
                cess=taxes["cess"],
                itc_availability=None,
                document_type="HSN",
                hsn=code,
                source=f"{filename}#1.hsn[{i}]",
                flags=[],
            )
        )
    return rows


def _parse_3b(payload: dict, filename: str) -> list[dict]:
    rows: list[dict] = []
    details = payload.get("sup_details") if isinstance(payload.get("sup_details"), dict) else {}
    for key, label in _SUP_3B.items():
        block = details.get(key)
        if not isinstance(block, dict):
            continue
        rows.append(
            _summary_row(
                label,
                block.get("txval"),
                block.get("iamt"),
                block.get("camt"),
                block.get("samt"),
                block.get("csamt"),
                f"{filename}#3b.sup_details.{key}",
            )
        )
    itc_elg = payload.get("itc_elg") if isinstance(payload.get("itc_elg"), dict) else {}
    for i, item in enumerate(_list((itc_elg or {}).get("itc_avl"))):
        ty = item.get("ty")
        section = f"ITC available: {ty}" if ty else "ITC available"
        rows.append(
            _summary_row(
                section,
                item.get("txval"),
                item.get("iamt"),
                item.get("camt"),
                item.get("samt"),
                item.get("csamt"),
                f"{filename}#3b.itc_elg.itc_avl[{i}]",
            )
        )
    inward = payload.get("inward_sup") if isinstance(payload.get("inward_sup"), dict) else {}
    for i, item in enumerate(_list((inward or {}).get("isup_details"))):
        ty = item.get("ty")
        section = f"Inward supplies: {ty}" if ty else "Inward supplies"
        rows.append(
            _summary_row(
                section,
                _add(item.get("inter"), item.get("intra")),
                None,
                None,
                None,
                None,
                f"{filename}#3b.inward_sup.isup_details[{i}]",
            )
        )
    if not rows:
        rows.append(
            _summary_row(
                "GSTR-3B (empty outward block)",
                None,
                None,
                None,
                None,
                None,
                filename,
            )
        )
    return rows


def _docdata_2b(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if isinstance((data or {}).get("docdata"), dict):
        return data["docdata"]
    if isinstance(payload.get("docdata"), dict):
        return payload["docdata"]
    if data and ("b2b" in data or "cdnr" in data):
        return data
    if "b2b" in payload or "cdnr" in payload:
        return payload
    return {}


def _gstr1_root(payload: dict) -> dict:
    if any(key in payload for key in ("b2b", "b2ba", "cdnr", "cdnra", "hsn")):
        return payload
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _invoice_row(party: dict, doc: dict, *, document_type: str, source: str) -> dict:
    gstin = party.get("ctin") or doc.get("ctin")
    taxes = _doc_taxes(doc)
    return _base_row(
        gstin=gstin,
        trade_name=party.get("trdnm") or party.get("cname") or doc.get("trdnm"),
        invoice_number=doc.get("inum") or doc.get("ntnum") or doc.get("nt_num"),
        invoice_date=doc.get("idt") or doc.get("dt") or doc.get("nt_dt"),
        invoice_value=doc.get("val"),
        taxable=taxes["taxable"],
        igst=taxes["igst"],
        cgst=taxes["cgst"],
        sgst=taxes["sgst"],
        cess=taxes["cess"],
        itc_availability=doc.get("itcavl"),
        document_type=document_type,
        hsn=doc.get("hsn") or doc.get("hsn_sc"),
        source=source,
        flags=gstin_flags(gstin),
    )


def _base_row(
    *,
    gstin: Any,
    trade_name: Any,
    invoice_number: Any,
    invoice_date: Any,
    invoice_value: Any,
    taxable: Any,
    igst: Any,
    cgst: Any,
    sgst: Any,
    cess: Any,
    itc_availability: Any,
    document_type: str,
    hsn: Any,
    source: str,
    flags: list[str],
) -> dict:
    return {
        "gstin": gstin,
        "trade_name": trade_name,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "invoice_value": invoice_value,
        "taxable": taxable,
        "igst": igst,
        "cgst": cgst,
        "sgst": sgst,
        "cess": cess,
        "itc_availability": itc_availability,
        "document_type": document_type,
        "hsn": hsn,
        "source": source,
        "flags": flags,
        "match_status": "",
        "books_ref": "",
    }


def _summary_row(section: str, taxable: Any, igst: Any, cgst: Any, sgst: Any, cess: Any, source: str) -> dict:
    return {
        "section": section,
        "taxable": taxable,
        "igst": igst,
        "cgst": cgst,
        "sgst": sgst,
        "cess": cess,
        "source": source,
        "flags": [],
    }


def _doc_taxes(doc: dict) -> dict[str, Any]:
    items = doc.get("itms") if doc.get("itms") else doc.get("items")
    summed = _sum_items(items) if items else {}
    if items:
        return {
            "taxable": _first(doc.get("txval"), summed.get("txval")),
            "igst": _first(summed.get("iamt"), doc.get("iamt")),
            "cgst": _first(summed.get("camt"), doc.get("camt")),
            "sgst": _first(summed.get("samt"), doc.get("samt")),
            "cess": _first(summed.get("csamt"), doc.get("csamt")),
        }
    return {
        "taxable": doc.get("txval"),
        "igst": doc.get("iamt"),
        "cgst": doc.get("camt"),
        "sgst": doc.get("samt"),
        "cess": doc.get("csamt"),
    }


def _sum_items(items: Any) -> dict[str, Any]:
    totals = {"txval": None, "iamt": None, "camt": None, "samt": None, "csamt": None}
    for item in _list(items):
        det = item.get("itm_det") if isinstance(item.get("itm_det"), dict) else item
        for key in totals:
            totals[key] = _add(totals[key], det.get(key))
    return totals


def _cdn_type(doc: dict) -> str:
    ntty = str(doc.get("ntty") or "").strip().upper()
    if ntty in {"D", "DN", "DEBIT", "DB"}:
        return "DN"
    if ntty:
        return "CDN"
    return "CDN"


def _party_docs(party: dict, keys: tuple[str, ...]) -> list[dict]:
    docs: list[dict] = []
    for key in keys:
        docs.extend(_list(party.get(key)))
    if docs:
        return docs
    if any(party.get(key) for key in ("inum", "ntnum", "nt_num")):
        return [party]
    return []


def _list(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _add(left: Any, right: Any) -> Any:
    a = _num(left)
    b = _num(right)
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def _num(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return None
    return None
