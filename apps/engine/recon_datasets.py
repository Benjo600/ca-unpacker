"""Workflow catalogue and dataset loading for reconciliation runs.

This module maps the documents already stored for a client period onto the
datasets each reconciliation workflow needs.  It never fabricates a dataset:
if a source type is absent the workflow is reported as unavailable with the
missing source named.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Iterable, Mapping

from sqlalchemy import func

from apps.engine.db import Client, ExtractedRow, Period, StoredFile, get_session

WORKFLOWS: tuple[dict, ...] = (
    {
        "id": "gst_2b_purchase_register",
        "label": "GSTR-2B vs Purchase Register",
        "short_label": "2B vs Register",
        "description": "Match inward supplies reported in GSTR-2B against the purchase register in Tally, Zoho or SAP exports.",
        "left_key": "gstr_2b",
        "right_key": "purchase_register",
        "left_label": "GSTR-2B",
        "right_label": "Purchase register",
        "mode": "invoice",
        "partial": False,
        "group": "GST",
        "rules": (
            "GSTIN and normalised invoice number are the primary key.",
            "Taxable value, IGST, CGST, SGST and cess are compared within the configured amount tolerance.",
            "Rows without a shared reference may only become probable review candidates; similar amounts alone never match.",
            "ITC eligibility is never decided by the system. Ineligible or review-required items are shown as review flags only.",
        ),
    },
    {
        "id": "gst_2b_invoices",
        "label": "GSTR-2B vs Purchase Invoices",
        "short_label": "2B vs Invoices",
        "description": "Match portal invoices against invoice data extracted from supplier PDFs.",
        "left_key": "gstr_2b",
        "right_key": "invoices",
        "left_label": "GSTR-2B",
        "right_label": "Purchase invoices",
        "mode": "invoice",
        "partial": False,
        "group": "GST",
        "rules": (
            "GSTIN, invoice number, invoice date and the tax breakdown are compared.",
            "Every result keeps the source PDF page and coordinates where the parser stored them.",
            "A certificate or manual note is never treated as proof of ITC eligibility.",
        ),
    },
    {
        "id": "invoices_purchase_register",
        "label": "Purchase Invoices vs Purchase Register",
        "short_label": "Invoices vs Register",
        "description": "Check that every extracted supplier invoice is present in the books and that amounts and tax treatment agree.",
        "left_key": "invoices",
        "right_key": "purchase_register",
        "left_label": "Purchase invoices",
        "right_label": "Purchase register",
        "mode": "invoice",
        "partial": False,
        "group": "Purchase",
        "rules": (
            "GSTIN and invoice number must agree before a match can be confirmed.",
            "Duplicate postings are reported rather than paired arbitrarily.",
            "Register entries without a source invoice and source invoices without a posting both remain visible.",
        ),
    },
    {
        "id": "gstr_1_sales_register",
        "label": "GSTR-1 vs Sales Register",
        "short_label": "GSTR-1 vs Sales",
        "description": "Compare outward supplies reported in GSTR-1 with the sales register.",
        "left_key": "gstr_1",
        "right_key": "sales_register",
        "left_label": "GSTR-1",
        "right_label": "Sales register",
        "mode": "invoice",
        "partial": False,
        "group": "GST",
        "rules": (
            "Customer GSTIN, invoice number, invoice date, taxable value and tax components are compared.",
            "Document type is preserved exactly; the system does not reclassify a sales document.",
            "Duplicate reporting is surfaced as a duplicate exception.",
        ),
    },
    {
        "id": "bank_accounting",
        "label": "Bank Statement vs Accounting Ledger",
        "short_label": "Bank vs Ledger",
        "description": "Match bank lines against Tally payment, receipt, contra and bank vouchers plus imported bank statements.",
        "left_key": "bank",
        "right_key": "bank_ledger",
        "left_label": "Bank statement",
        "right_label": "Accounting ledger",
        "mode": "bank",
        "partial": True,
        "group": "Banking",
        "rules": (
            "UTR, cheque, invoice and narration references are extracted and matched with the voucher reference.",
            "A reference plus an agreeing amount can be a strong match. Amount similarity alone never matches.",
            "Partial payments and one-to-many splits are proposals only and must be reviewed.",
            "Closing balance checks only pass when both sides actually carry a closing balance.",
        ),
    },
    {
        "id": "vendor_statement_purchase_ledger",
        "label": "Vendor Statement vs Purchase Ledger",
        "short_label": "Vendor Statement",
        "description": "Reconcile supplier statements with purchase ledger entries, credit notes and payments.",
        "left_key": "vendor_statement",
        "right_key": "purchase_ledger",
        "left_label": "Vendor statement",
        "right_label": "Purchase ledger",
        "mode": "vendor",
        "partial": True,
        "group": "Vendor",
        "rules": (
            "Invoice numbers, dates, debit/credit values and reference numbers are compared.",
            "Missing invoices, missing credit notes, duplicate postings and outstanding balances remain visible.",
            "A supplier statement must be imported as a vendor statement file; the app does not invent one.",
        ),
    },
    {
        "id": "gl_subledger",
        "label": "General Ledger vs Sub-ledger",
        "short_label": "GL vs Sub-ledger",
        "description": "Compare control-account balances with sub-ledger balances using opening, movement and closing balances.",
        "left_key": "control_accounts",
        "right_key": "subledger_accounts",
        "left_label": "Control accounts",
        "right_label": "Sub-ledger",
        "mode": "balance",
        "partial": False,
        "group": "GL",
        "rules": (
            "Balances are grouped by account code/name and compared using opening, period movement and closing values.",
            "A reconciliation conclusion is claimed only when both sides carry a closing balance.",
            "Rows without an explicit control/sub-ledger marker are not silently forced into either side.",
        ),
    },
)

WORKFLOW_BY_ID = {workflow["id"]: workflow for workflow in WORKFLOWS}

_PURCHASE_MARKERS = ("purchase", "purch", "bill", "debit note", "debitnote")
_SALES_MARKERS = ("sales", "sale", "credit note", "creditnote")
_BANK_VOUCHER_MARKERS = ("payment", "receipt", "contra", "bank")


def _json_load(text: str | None, fallback):
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return value


def financial_year(label: str | None) -> str:
    """Return the Indian financial year (April-March) for a period label."""

    text = str(label or "")
    match = re.search(r"(20\d{2})\s*[-/]\s*(\d{2,4})", text)
    if match:
        start = int(match.group(1))
        return f"{start}-{(start + 1) % 100:02d}"
    match = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,/-]+(20\d{2})",
        text,
        re.I,
    )
    if match:
        month_text, year_text = match.group(1).lower()[:3], int(match.group(2))
        month = {
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
        }.get(month_text, 1)
        start = year_text if month >= 4 else year_text - 1
        return f"{start}-{(start + 1) % 100:02d}"
    match = re.search(r"(20\d{2})", text)
    if match:
        start = int(match.group(1))
        return f"{start}-{(start + 1) % 100:02d}"
    today = date.today()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def period_meta(period: Period, client: Client) -> dict:
    return {
        "period_id": period.id,
        "period_label": period.label,
        "client_id": client.id,
        "client_name": client.name,
        "financial_year": financial_year(period.label),
    }


def _row_payload(extracted: ExtractedRow, stored: StoredFile) -> dict | None:
    try:
        payload = json.loads(extracted.payload_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    row = dict(payload)
    row["_ca_row_id"] = extracted.id
    row["_ca_file_id"] = stored.id
    row["_ca_file_name"] = stored.original_name
    row["_ca_kind"] = extracted.kind
    row["_ca_page"] = extracted.source_page
    row["_ca_bbox"] = extracted.source_bbox
    row["_ca_detected_kind"] = stored.detected_kind
    row["_ca_override_kind"] = stored.override_kind
    row["_ca_currency"] = stored.currency_override or stored.currency_code
    return row


def _all_extracted(period_id: int) -> list[dict]:
    session = get_session()
    try:
        records = (
            session.query(ExtractedRow, StoredFile)
            .join(StoredFile, ExtractedRow.file_id == StoredFile.id)
            .filter(ExtractedRow.period_id == period_id)
            .order_by(ExtractedRow.id.asc())
            .all()
        )
        rows = []
        for extracted, stored in records:
            row = _row_payload(extracted, stored)
            if row is not None:
                rows.append(row)
        return rows
    finally:
        session.close()


def _register(row: Mapping) -> str:
    return str(row.get("register") or "").strip().lower()


def _voucher_type(row: Mapping) -> str:
    return str(row.get("voucher_type") or row.get("document_type") or "").strip().lower()


def _is_purchase(row: Mapping) -> bool:
    register = _register(row)
    voucher = _voucher_type(row)
    if register in {"purchase", "purchases", "bill", "bills"}:
        return True
    if any(marker in register for marker in _PURCHASE_MARKERS):
        return True
    return any(marker in voucher for marker in _PURCHASE_MARKERS) and "credit note" not in voucher


def _is_sales(row: Mapping) -> bool:
    register = _register(row)
    voucher = _voucher_type(row)
    if register in {"sales", "sale"}:
        return True
    if any(marker in register for marker in _SALES_MARKERS):
        return True
    return any(marker in voucher for marker in _SALES_MARKERS)


def _is_bank_ledger(row: Mapping) -> bool:
    voucher = _voucher_type(row)
    return bool(voucher) and any(marker in voucher for marker in _BANK_VOUCHER_MARKERS)


def _is_invoice_header(row: Mapping) -> bool:
    if row.get("description"):
        return False
    return bool(
        row.get("invoice_number")
        or row.get("supplier_gstin")
        or row.get("customer_gstin")
        or row.get("gstin")
        or row.get("invoice_value") is not None
        or (row.get("supplier_name") and row.get("customer_name"))
    )


def _ledger_type(row: Mapping) -> str:
    raw = str(
        row.get("ledger_type")
        or row.get("account_type")
        or row.get("account_category")
        or ""
    ).strip().lower()
    return raw


def _is_control_account(row: Mapping) -> bool:
    ledger = _ledger_type(row)
    if ledger:
        return "control" in ledger or ledger in {"gl", "general_ledger"}
    if row.get("control_account"):
        return True
    # SAP rows with a G/L account but no vendor/customer code are the closest
    # reliable signal for a control account.  This is a heuristic, and the UI
    # labels the source so a professional can verify it.
    return bool(row.get("gl_account")) and not any(
        row.get(key)
        for key in ("vendor_number", "customer_number", "party_code", "vendor_code")
    )


def _is_subledger(row: Mapping) -> bool:
    ledger = _ledger_type(row)
    if ledger:
        return "sub" in ledger or "party" in ledger or ledger in {"vendor", "customer", "debtor", "creditor"}
    return bool(row.get("gl_account")) and any(
        row.get(key)
        for key in ("vendor_number", "customer_number", "party_code", "vendor_code")
    )


def _is_vendor_statement(row: Mapping) -> bool:
    kind = str(row.get("_ca_kind") or "").lower()
    detected = str(row.get("_ca_detected_kind") or "").lower()
    override = str(row.get("_ca_override_kind") or "").lower()
    return "vendor_statement" in {kind, detected, override}


def datasets_for_period(period_id: int) -> dict[str, list[dict]]:
    rows = _all_extracted(period_id)
    invoice_headers = [
        row for row in rows if row.get("_ca_kind") == "invoice" and _is_invoice_header(row)
    ]
    gstr_2b = [row for row in rows if row.get("_ca_kind") == "gstr_2b"]
    gstr_1 = [row for row in rows if row.get("_ca_kind") == "gstr_1"]
    books = [row for row in rows if row.get("_ca_kind") in {"tally", "zoho", "sap"}]
    bank = [row for row in rows if row.get("_ca_kind") == "bank"]
    vendor_statement = [row for row in rows if _is_vendor_statement(row)]
    purchase_register = [row for row in books if _is_purchase(row)]
    sales_register = [row for row in books if _is_sales(row)]
    bank_ledger = [row for row in books if _is_bank_ledger(row)]
    purchase_ledger = [
        row for row in books if _is_purchase(row) or any(
            marker in _voucher_type(row) for marker in ("payment", "credit note", "debit note")
        )
    ]
    control_accounts = [row for row in books if _is_control_account(row)]
    subledger_accounts = [row for row in books if _is_subledger(row)]
    return {
        "invoices": invoice_headers,
        "gstr_2b": gstr_2b,
        "gstr_1": gstr_1,
        "purchase_register": purchase_register,
        "sales_register": sales_register,
        "bank": bank,
        "bank_ledger": bank_ledger,
        "vendor_statement": vendor_statement,
        "purchase_ledger": purchase_ledger,
        "control_accounts": control_accounts,
        "subledger_accounts": subledger_accounts,
        "all_books": books,
    }


def dataset_sources(rows: Iterable[Mapping]) -> list[dict]:
    seen: dict[int, dict] = {}
    order: list[int] = []
    for row in rows:
        file_id = row.get("_ca_file_id")
        if file_id is None:
            continue
        if file_id not in seen:
            seen[file_id] = {
                "file_id": file_id,
                "file_name": row.get("_ca_file_name") or row.get("source") or "",
                "kind": row.get("_ca_kind") or "",
                "rows": 0,
            }
            order.append(file_id)
        seen[file_id]["rows"] += 1
    return [seen[file_id] for file_id in order]


def _availability(workflow: Mapping, datasets: Mapping[str, list[dict]]) -> dict:
    left = datasets.get(workflow["left_key"]) or []
    right = datasets.get(workflow["right_key"]) or []
    missing = []
    if not left:
        missing.append(workflow["left_label"])
    if not right:
        missing.append(workflow["right_label"])
    return {
        "id": workflow["id"],
        "available": bool(left) and bool(right),
        "missing": missing,
        "left_count": len(left),
        "right_count": len(right),
        "left_sources": dataset_sources(left),
        "right_sources": dataset_sources(right),
    }


def _period_summary(period: Period, client: Client, file_count: int, datasets: Mapping[str, list[dict]]) -> dict:
    availability = [_availability(workflow, datasets) for workflow in WORKFLOWS]
    meta = period_meta(period, client)
    return {
        **meta,
        "id": period.id,
        "label": period.label,
        "file_count": file_count,
        "created_at": period.created_at.isoformat() if period.created_at else None,
        "datasets": {key: len(value or []) for key, value in datasets.items() if key != "all_books"},
        "workflows": availability,
        "has_comparison": any(item["available"] for item in availability),
    }


def reconciliation_workspace() -> dict:
    session = get_session()
    try:
        records = (
            session.query(Period, Client)
            .join(Client, Period.client_id == Client.id)
            .order_by(Period.created_at.desc(), Period.id.desc())
            .all()
        )
        file_counts = dict(
            session.query(StoredFile.period_id, func.count(StoredFile.id))
            .group_by(StoredFile.period_id)
            .all()
        )
        period_rows = [
            (period, client, int(file_counts.get(period.id) or 0))
            for period, client in records
        ]
    finally:
        session.close()
    periods = []
    for period, client, file_count in period_rows:
        periods.append(
            _period_summary(period, client, file_count, datasets_for_period(period.id))
        )
    selected = next(
        (item["id"] for item in periods if item["has_comparison"]),
        periods[0]["id"] if periods else None,
    )
    return {
        "periods": periods,
        "workflows": [_public_workflow(workflow) for workflow in WORKFLOWS],
        "selected_period_id": selected,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _public_workflow(workflow: Mapping) -> dict:
    return {
        "id": workflow["id"],
        "label": workflow["label"],
        "short_label": workflow.get("short_label") or workflow["label"],
        "description": workflow["description"],
        "left_label": workflow["left_label"],
        "right_label": workflow["right_label"],
        "mode": workflow["mode"],
        "partial": workflow.get("partial", False),
        "group": workflow.get("group", ""),
        "rules": list(workflow["rules"]),
    }


def workflow_definition(workflow_id: str) -> dict | None:
    return WORKFLOW_BY_ID.get(str(workflow_id or ""))


def dataset_payload(workflow: Mapping, datasets: Mapping[str, list[dict]]) -> dict:
    left_rows = datasets.get(workflow["left_key"]) or []
    right_rows = datasets.get(workflow["right_key"]) or []
    return {
        "left": {
            "key": workflow["left_key"],
            "label": workflow["left_label"],
            "count": len(left_rows),
            "sources": dataset_sources(left_rows),
        },
        "right": {
            "key": workflow["right_key"],
            "label": workflow["right_label"],
            "count": len(right_rows),
            "sources": dataset_sources(right_rows),
        },
    }
