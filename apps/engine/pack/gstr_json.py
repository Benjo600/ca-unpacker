"""GSTR-1 and GSTR-3B upload files, in the shape the GST portal's offline tool accepts.

Why this file is strict
-----------------------
This is a statutory return, so nothing here is guessed:

* A tax split (IGST / CGST / SGST / CESS) is only used when the source row carries
  it explicitly.
* When only an aggregate tax amount exists, the split is derived from the supply
  being intra-state or inter-state. That needs **both** the supplier's state (the
  client GSTIN) and the place of supply (a place-of-supply value or the party's
  GSTIN). Every row written this way is reported as a "derived split".
* The rate on an item is only written when the source states it, or when an
  explicit tax split divides into one of the standard GST slabs. No rate is
  invented from a total.
* Anything that cannot be established is excluded from the JSON and returned by
  :func:`build_gstr_report` so the pack can list it, with a reason, instead of
  dropping it silently.

Root fields are the first thing the portal validates: a GSTR-1 file without
``gt`` / ``cur_gt`` / ``version`` / ``hash`` (or a GSTR-3B without
``ret_period`` / ``version`` / ``hash``) is rejected before a single row is read.
``gstin`` and the return period are required too - :func:`build_gstr1_json` and
:func:`build_gstr3b_json` raise :class:`ValueError` rather than emit a file that
cannot be uploaded.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from apps.engine.validators.gstin import GSTIN_RE, gstin_checksum_ok, gstin_state, pos_state_code

# Schema version strings published with the portal's offline utilities. Bump these
# in one place when the portal moves on.
GSTR1_VERSION = "GST3.2.0"
GSTR3B_VERSION = "GST3.0.2"
# The portal's own sample files carry this literal; the validator only wants it present.
ROOT_HASH = "hash"

# B2CL starts above this invoice value (inter-state, unregistered buyer).
B2CL_THRESHOLD = 250000.0
STANDARD_RATES = (0.0, 0.1, 0.25, 1.0, 1.5, 3.0, 5.0, 12.0, 18.0, 28.0)
CENT = Decimal("0.01")

SPLIT_EXPLICIT = "explicit"
SPLIT_DERIVED = "derived"

REASON_NO_TAXABLE = "taxable value is missing or zero"
REASON_NO_INVOICE_NUMBER = "invoice number is missing"
REASON_NO_DATE = "invoice date is missing or not a date"
REASON_BAD_GSTIN = "counterparty GSTIN is not a valid 15-character GSTIN"
REASON_BAD_CHECKSUM = "counterparty GSTIN fails the GSTIN checksum"
REASON_NO_SPLIT = "no tax split and no total tax amount on the row"
REASON_NO_SUPPLIER_STATE = "client GSTIN is not set, so the supplier state is unknown"
REASON_NO_POS = "place of supply could not be established, so the split cannot be derived"
REASON_NO_RATE = "tax rate is not stated on the row and cannot be read off the tax amounts"
REASON_DUPLICATE = "identical row already taken from another file"

NOTES = (
    "Only outward supply rows (the sales register) feed these files.",
    "A tax split is used only when the row carries it; an aggregate tax is split "
    "intra-state/inter-state only when both the client GSTIN and the place of supply are known.",
    "A derived split treats the total tax as GST only: a cess hidden inside one lump "
    "tax sum cannot be separated, so those rows are listed under derived.",
    "A tax rate is written only when the source states it or an explicit split reads "
    "as a standard GST slab (0/0.1/0.25/1/1.5/3/5/12/18/28).",
    "HSN quantities are not in the books, so the HSN table uses UQC 'OTH' with quantity 0.",
    "doc_issue is not written: the pack cannot prove an invoice series is complete.",
    "GSTR-3B carries section 3.1(a) outward taxable supplies net of credit notes only; "
    "ITC (section 4) is left to the CA because purchase data does not prove ITC eligibility.",
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DMY_DATE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_LABEL = re.compile(r"^([a-z]{3,9})[\s,/-]*(\d{4})$")


def build_gstr1_json(rows: list[dict], meta: dict | None = None) -> dict:
    """Build the GSTR-1 upload payload. Raises ValueError when it cannot be filed."""
    root = _root_fields(meta)
    included = _included(_classify_all(rows, meta))
    if not included:
        raise ValueError("No outward supply row could be included in GSTR-1.")

    payload: dict[str, Any] = {
        "gstin": root["gstin"],
        "fp": root["fp"],
        "gt": 0.0,
        "cur_gt": 0.0,
        "version": GSTR1_VERSION,
        "hash": ROOT_HASH,
    }
    for key, table in (
        ("b2b", _b2b_table(included)),
        ("b2cs", _b2cs_table(included, root["supplier_state"])),
        ("b2cl", _b2cl_table(included)),
        ("cdnr", _cdnr_table(included)),
        ("cdnur", _cdnur_table(included)),
        ("hsn", _hsn_table(included)),
    ):
        if table:
            payload[key] = table
    turnover = _money(sum(item["value"] or 0.0 for item in included))
    payload["gt"] = turnover
    payload["cur_gt"] = turnover
    return payload


def build_gstr3b_json(rows: list[dict], meta: dict | None = None) -> dict:
    """Build the GSTR-3B summary payload. Raises ValueError when it cannot be filed."""
    root = _root_fields(meta)
    included = _included(_classify_all(rows, meta))
    if not included:
        raise ValueError("No outward supply row could be included in GSTR-3B.")

    totals = {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0}
    for item in included:
        sign = _note_sign(item)
        totals["txval"] += sign * (item["taxable"] or 0.0)
        totals["iamt"] += sign * (item["igst"] or 0.0)
        totals["camt"] += sign * (item["cgst"] or 0.0)
        totals["samt"] += sign * (item["sgst"] or 0.0)
        totals["csamt"] += sign * (item["cess"] or 0.0)

    return {
        "gstin": root["gstin"],
        "ret_period": root["fp"],
        "version": GSTR3B_VERSION,
        "hash": ROOT_HASH,
        "sup_details": {
            "osup_det": {
                "txval": _money(totals["txval"]),
                "iamt": _money(totals["iamt"]),
                "camt": _money(totals["camt"]),
                "samt": _money(totals["samt"]),
                "csamt": _money(totals["csamt"]),
            }
        },
    }


def build_gstr_report(rows: list[dict], meta: dict | None = None) -> dict:
    """Companion structure: what went in, what was derived, what had to be left out."""
    decisions = _classify_all(rows, meta)
    included = [item for item in decisions if item["status"] != "exclude"]
    derived_split = [item for item in included if item["split"] == SPLIT_DERIVED]
    derived_rate = [item for item in included if item["rate_source"] == "derived"]
    excluded = [item for item in decisions if item["status"] == "exclude"]
    meta = meta or {}
    return {
        "gstin": _text(meta.get("gstin")),
        "fp": _safe_fp(meta),
        "counts": {
            "considered": len(decisions),
            "included": len(included),
            "derived_split": len(derived_split),
            "derived_rate": len(derived_rate),
            "excluded": len(excluded),
        },
        "included": [_entry(item) for item in included],
        "derived": [_entry(item) for item in derived_split + derived_rate],
        "excluded": [_entry(item) for item in excluded],
        "notes": list(NOTES),
    }


def _classify_all(rows: list[dict], meta: dict | None) -> list[dict]:
    meta = meta or {}
    supplier_state = gstin_state(meta.get("gstin"))
    seen: set[tuple] = set()
    return [_classify(row, index, supplier_state, seen) for index, row in enumerate(rows or [])]


def _classify(row: dict, index: int, supplier_state: str | None, seen: set[tuple]) -> dict:
    decision = {
        "index": index,
        "source": _text(row.get("source")),
        "party": _text(_first(row, "party_name", "supplier_name", "trade_name")),
        "gstin": None,
        "invoice_number": _text(_first(row, "invoice_number", "invoice_no", "voucher_number", "nt_num", "ntnum")),
        "date": _gstr_date(_first(row, "invoice_date", "date", "idt", "nt_dt")),
        "taxable": _money(_first(row, "taxable_value", "taxable", "txval")),
        "value": _money(_first(row, "invoice_value", "value", "amount", "val")),
        "hsn": _text(_first(row, "hsn", "hsn_code", "hsn_sc")),
        "igst": None,
        "cgst": None,
        "sgst": None,
        "cess": None,
        "rate": None,
        "place_of_supply": None,
        "bucket": None,
        "note_type": None,
        "split": None,
        "rate_source": None,
        "status": "include",
        "reason": None,
    }

    gstin = _text(_first(row, "gstin", "supplier_gstin", "party_gstin", "ctin"))
    if gstin:
        gstin = gstin.upper()
    decision["gstin"] = gstin

    if not decision["taxable"]:
        return _exclude(decision, REASON_NO_TAXABLE)

    note_type = _note_type(row)
    decision["note_type"] = note_type
    if note_type is None and (decision["taxable"] or 0) < 0:
        # A negative sales row with no note marker is a return/credit note.
        note_type = "C"
        decision["note_type"] = "C"
        decision["reason"] = "negative amount read as a credit note"

    pos = pos_state_code(_first(row, "place_of_supply", "place_of_supply_state", "pos", "pos_state"))
    if pos is None and gstin:
        pos = gstin_state(gstin)
    decision["place_of_supply"] = pos

    registered = False
    if gstin:
        if not GSTIN_RE.match(gstin):
            return _exclude(decision, REASON_BAD_GSTIN)
        if not gstin_checksum_ok(gstin):
            return _exclude(decision, REASON_BAD_CHECKSUM)
        registered = True

    split = _tax_split(row, supplier_state, pos)
    if isinstance(split, str):
        return _exclude(decision, split)
    decision.update(split)

    rate, rate_source = _rate(decision, row)
    if rate is None:
        return _exclude(decision, REASON_NO_RATE)
    decision["rate"] = rate
    decision["rate_source"] = rate_source

    if decision["value"] is None:
        taxed = sum(decision[key] or 0.0 for key in ("igst", "cgst", "sgst", "cess"))
        decision["value"] = _money((decision["taxable"] or 0.0) + taxed)

    if note_type is None:
        if not decision["invoice_number"]:
            return _exclude(decision, REASON_NO_INVOICE_NUMBER)
        if decision["date"] is None:
            return _exclude(decision, REASON_NO_DATE)

    if registered:
        decision["bucket"] = "cdnr" if note_type else "b2b"
    elif note_type:
        decision["bucket"] = "cdnur"
    elif decision["place_of_supply"] != supplier_state and (decision["value"] or 0.0) > B2CL_THRESHOLD:
        decision["bucket"] = "b2cl"
    else:
        decision["bucket"] = "b2cs"

    if decision["bucket"] in {"b2cs", "b2cl", "cdnur"} and decision["place_of_supply"] is None:
        # These tables carry the place of supply on the row itself.
        return _exclude(decision, REASON_NO_POS)

    if note_type:
        for key in ("taxable", "value", "igst", "cgst", "sgst", "cess"):
            if decision[key] is not None:
                decision[key] = abs(decision[key])

    signature = (
        decision["bucket"],
        decision["gstin"],
        decision["invoice_number"],
        decision["date"],
        decision["taxable"],
        decision["value"],
        decision["igst"],
        decision["cgst"],
        decision["sgst"],
        decision["cess"],
    )
    if registered or decision["invoice_number"]:
        if signature in seen:
            return _exclude(decision, REASON_DUPLICATE)
        seen.add(signature)

    if decision["split"] == SPLIT_DERIVED:
        decision["status"] = "derived"
    return decision


def _exclude(decision: dict, reason: str) -> dict:
    decision["status"] = "exclude"
    if not decision.get("reason"):
        decision["reason"] = reason
    elif reason not in decision["reason"]:
        decision["reason"] = f"{decision['reason']}; {reason}"
    return decision


def _tax_split(row: dict, supplier_state: str | None, pos: str | None) -> dict | str:
    """Explicit split when the row has one, derived split otherwise, or a reason string."""
    heads = {}
    explicit = False
    for key in ("igst", "cgst", "sgst", "cess"):
        value = row.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            heads[key] = None
            continue
        heads[key] = _money(value) or 0.0
        explicit = True
    if explicit:
        return {**heads, "split": SPLIT_EXPLICIT}

    tax = _money(_first(row, "tax", "tax_amount", "taxamt", "total_tax"))
    if tax is None:
        return REASON_NO_SPLIT
    if supplier_state is None:
        return REASON_NO_SUPPLIER_STATE
    if pos is None:
        # A registered party's GSTIN gives us the state, so this only happens with no GSTIN.
        return REASON_NO_POS
    tax = abs(tax)
    if pos == supplier_state:
        cgst = _money(tax / 2.0)
        sgst = _money(tax - cgst)
        return {"igst": 0.0, "cgst": cgst, "sgst": sgst, "cess": 0.0, "split": SPLIT_DERIVED}
    return {"igst": tax, "cgst": 0.0, "sgst": 0.0, "cess": 0.0, "split": SPLIT_DERIVED}


def _rate(decision: dict, row: dict) -> tuple[float | None, str | None]:
    stated = _first(row, "tax_rate", "tax_percent", "gst_rate")
    if stated is not None:
        value = _money(stated)
        if value is not None:
            return value, "source"
    if decision["split"] != SPLIT_EXPLICIT:
        return None, None
    taxable = decision["taxable"]
    if not taxable:
        return None, None
    total = sum(decision[key] or 0.0 for key in ("igst", "cgst", "sgst", "cess"))
    percent = abs(total) / abs(taxable) * 100.0
    for slab in STANDARD_RATES:
        if abs(percent - slab) <= 0.01:
            return float(slab), "derived"
    return None, None


def _note_type(row: dict) -> str | None:
    for raw in (row.get("document_type"), row.get("voucher_type")):
        text = " ".join(str(raw or "").lower().split())
        if not text:
            continue
        if "credit note" in text or "creditnote" in text:
            return "C"
        if "debit note" in text or "debitnote" in text:
            return "D"
        code = text.replace(" ", "").upper()
        if code in {"CR", "CN", "CDNR"}:
            return "C"
        if code in {"DR", "DN", "CDNA"}:
            return "D"
    return None


def _note_sign(item: dict) -> float:
    if item["note_type"] == "C":
        return -1.0
    return 1.0


# --------------------------------------------------------------------------- #
# GSTR-1 tables
# --------------------------------------------------------------------------- #


def _b2b_table(included: list[dict]) -> list[dict]:
    parties: dict[str, dict] = {}
    for item in included:
        if item["bucket"] != "b2b":
            continue
        party = parties.setdefault(item["gstin"], {"ctin": item["gstin"], "invoices": [], "_by": {}})
        key = (item["invoice_number"], item["date"])
        invoice = party["_by"].get(key)
        if invoice is None:
            invoice = {
                "inum": item["invoice_number"],
                "idt": item["date"],
                "pos": item["place_of_supply"],
                "rchrg": "N",
                "inv_typ": "R",
                "lines": [],
            }
            party["_by"][key] = invoice
            party["invoices"].append(invoice)
        invoice["lines"].append(item)

    table = []
    for party in parties.values():
        invoices = []
        for invoice in party["invoices"]:
            entry = {
                "inum": invoice["inum"],
                "idt": invoice["idt"],
                "val": _document_value(invoice["lines"]),
                "rchrg": invoice["rchrg"],
                "inv_typ": invoice["inv_typ"],
                "itms": _item_list(invoice["lines"]),
            }
            if invoice["pos"]:
                entry["pos"] = invoice["pos"]
            invoices.append(entry)
        table.append({"ctin": party["ctin"], "inv": invoices})
    return table


def _b2cs_table(included: list[dict], supplier_state: str | None) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for item in included:
        if item["bucket"] != "b2cs":
            continue
        sply_ty = "INTRA" if item["place_of_supply"] == supplier_state else "INTER"
        key = (sply_ty, item["place_of_supply"], item["rate"])
        row = buckets.setdefault(
            key,
            {
                "sply_ty": sply_ty,
                "pos": item["place_of_supply"],
                "rt": item["rate"],
                "typ": "OE",
                "txval": 0.0,
                "iamt": 0.0,
                "camt": 0.0,
                "samt": 0.0,
                "csamt": 0.0,
            },
        )
        _add_taxes(row, item, 1.0)
    return list(buckets.values())


def _b2cl_table(included: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for item in included:
        if item["bucket"] != "b2cl":
            continue
        group = groups.setdefault(item["place_of_supply"], {"pos": item["place_of_supply"], "inv": [], "_by": {}})
        key = (item["invoice_number"], item["date"])
        invoice = group["_by"].get(key)
        if invoice is None:
            invoice = {"inum": item["invoice_number"], "idt": item["date"], "lines": []}
            group["_by"][key] = invoice
            group["inv"].append(invoice)
        invoice["lines"].append(item)
    table = []
    for group in groups.values():
        invoices = [
            {
                "inum": invoice["inum"],
                "idt": invoice["idt"],
                "val": _document_value(invoice["lines"]),
                "itms": _item_list(invoice["lines"]),
            }
            for invoice in group["inv"]
        ]
        table.append({"pos": group["pos"], "inv": invoices})
    return table


def _cdnr_table(included: list[dict]) -> list[dict]:
    parties: dict[str, dict] = {}
    for item in included:
        if item["bucket"] != "cdnr":
            continue
        party = parties.setdefault(item["gstin"], {"ctin": item["gstin"], "notes": [], "_by": {}})
        key = (item["note_type"], item["invoice_number"], item["date"])
        note = party["_by"].get(key)
        if note is None:
            note = {
                "ntty": item["note_type"] or "C",
                "nt_num": item["invoice_number"],
                "nt_dt": item["date"],
                "pos": item["place_of_supply"],
                "rchrg": "N",
                "inv_typ": "R",
                "lines": [],
            }
            party["_by"][key] = note
            party["notes"].append(note)
        note["lines"].append(item)
    table = []
    for party in parties.values():
        notes = []
        for note in party["notes"]:
            entry = {
                "ntty": note["ntty"],
                "nt_num": note["nt_num"],
                "nt_dt": note["nt_dt"],
                "val": _document_value(note["lines"]),
                "rchrg": note["rchrg"],
                "inv_typ": note["inv_typ"],
                "itms": _item_list(note["lines"]),
            }
            if note["pos"]:
                entry["pos"] = note["pos"]
            notes.append(entry)
        table.append({"ctin": party["ctin"], "nt": notes})
    return table


def _cdnur_table(included: list[dict]) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for item in included:
        if item["bucket"] != "cdnur":
            continue
        key = (item["place_of_supply"], item["rate"])
        row = buckets.setdefault(
            key,
            {
                "typ": "B2CS",
                "pos": item["place_of_supply"],
                "rt": item["rate"],
                "txval": 0.0,
                "iamt": 0.0,
                "camt": 0.0,
                "samt": 0.0,
                "csamt": 0.0,
            },
        )
        sign = -1.0 if item["note_type"] == "C" else 1.0
        _add_taxes(row, item, sign)
    return list(buckets.values())


def _hsn_table(included: list[dict]) -> dict | None:
    buckets: dict[tuple, dict] = {}
    for item in included:
        hsn = _text(item.get("hsn"))
        if not hsn:
            continue
        key = (hsn, item["rate"])
        row = buckets.setdefault(
            key,
            {
                "num": len(buckets) + 1,
                "hsn_sc": hsn,
                "uqc": "OTH",
                "qty": 0.0,
                "rt": item["rate"],
                "txval": 0.0,
                "iamt": 0.0,
                "camt": 0.0,
                "samt": 0.0,
                "csamt": 0.0,
            },
        )
        _add_taxes(row, item, _note_sign(item))
    if not buckets:
        return None
    return {"data": list(buckets.values())}


def _item_list(lines: list[dict]) -> list[dict]:
    """Line detail inside one document, merged per (HSN, rate)."""
    merged: dict[tuple, dict] = {}
    for line in lines:
        hsn = _text(line.get("hsn"))
        key = (hsn, line["rate"])
        entry = merged.setdefault(
            key,
            {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
        )
        _add_taxes(entry, line, 1.0)
    return [
        {
            "num": position,
            "itm_det": {
                "txval": entry["txval"],
                "rt": key[1],
                "iamt": entry["iamt"],
                "camt": entry["camt"],
                "samt": entry["samt"],
                "csamt": entry["csamt"],
            },
        }
        for position, (key, entry) in enumerate(merged.items(), start=1)
    ]


def _add_taxes(target: dict, item: dict, sign: float) -> None:
    target["txval"] = _money(target["txval"] + sign * (item["taxable"] or 0.0))
    target["iamt"] = _money(target["iamt"] + sign * (item["igst"] or 0.0))
    target["camt"] = _money(target["camt"] + sign * (item["cgst"] or 0.0))
    target["samt"] = _money(target["samt"] + sign * (item["sgst"] or 0.0))
    target["csamt"] = _money(target["csamt"] + sign * (item["cess"] or 0.0))


def _document_value(lines: list[dict]) -> float:
    if len(lines) == 1 and lines[0].get("value") is not None:
        return _money(lines[0]["value"])
    taxable = sum(line["taxable"] or 0.0 for line in lines)
    tax = sum(
        (line["igst"] or 0.0) + (line["cgst"] or 0.0) + (line["sgst"] or 0.0) + (line["cess"] or 0.0)
        for line in lines
    )
    return _money(taxable + tax)


# --------------------------------------------------------------------------- #
# Root fields and small helpers
# --------------------------------------------------------------------------- #


def _root_fields(meta: dict | None) -> dict:
    meta = meta or {}
    gstin = _text(meta.get("gstin"))
    if not gstin:
        raise ValueError("The client GSTIN is not set, so no GST upload file can be written.")
    gstin = gstin.upper()
    if not GSTIN_RE.match(gstin):
        raise ValueError("The client GSTIN is not a valid 15-character GSTIN.")
    if not gstin_checksum_ok(gstin):
        raise ValueError("The client GSTIN fails the GSTIN checksum, so no GST upload file can be written.")
    fp = _safe_fp(meta)
    if fp is None:
        raise ValueError(
            "The return period is not known, so no GST upload file can be written."
        )
    return {"gstin": gstin, "fp": fp, "supplier_state": gstin_state(gstin)}


def _safe_fp(meta: dict | None) -> str | None:
    meta = meta or {}
    for key in ("fp", "period_code", "rtnprd", "ret_period", "period"):
        value = meta.get(key)
        if value is None or str(value).strip() == "":
            continue
        formatted = format_fp(str(value))
        if formatted:
            return formatted
    return None


def format_fp(value: str) -> str | None:
    """Return the portal's MMYYYY return period, or None when it cannot be read."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return None
    if text.isdigit() and len(text) == 6:
        month, year = int(text[:2]), int(text[2:])
        return f"{month:02d}{year:04d}" if 1 <= month <= 12 else None
    match = re.match(r"^(\d{1,2})[-/.](\d{4})$", text)
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        return f"{month:02d}{year:04d}" if 1 <= month <= 12 else None
    match = re.match(r"^(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?$", text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        return f"{month:02d}{year:04d}" if 1 <= month <= 12 else None
    match = _MONTH_LABEL.match(text.lower())
    if match:
        month = _MONTH_NAMES.get(match.group(1)[:3])
        if month:
            return f"{month:02d}{int(match.group(2)):04d}"
    return None


def _gstr_date(value: Any) -> str | None:
    """Portal dates are DD-MM-YYYY."""
    text = str(value or "").strip()
    if not text:
        return None
    iso = _ISO_DATE.match(text)
    if iso:
        day, month, year = int(iso.group(3)), int(iso.group(2)), int(iso.group(1))
        return _date(day, month, year)
    dmy = _DMY_DATE.match(text)
    if dmy:
        return _date(int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3)))
    return None


def _date(day: int, month: int, year: int) -> str | None:
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2999):
        return None
    return f"{day:02d}-{month:02d}-{year:04d}"


def _money(value: Any) -> float | None:
    """Round to paise the way a return does: half up, two decimals."""
    number = _decimal(value)
    if number is None:
        return None
    return float(number)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, float)):
        number = Decimal(str(value))
    else:
        text = str(value).replace(",", "").replace("\u20b9", "").strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        if not text:
            return None
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    try:
        return number.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _included(decisions: list[dict]) -> list[dict]:
    return [item for item in decisions if item["status"] != "exclude"]


def _entry(item: dict) -> dict:
    keys = (
        "invoice_number",
        "date",
        "party",
        "gstin",
        "taxable",
        "value",
        "igst",
        "cgst",
        "sgst",
        "cess",
        "rate",
        "place_of_supply",
        "bucket",
        "note_type",
        "split",
        "rate_source",
        "status",
        "reason",
        "source",
    )
    return {key: item.get(key) for key in keys}


def _first(row: dict, *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
