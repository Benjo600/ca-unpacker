from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func

from apps.engine.db import Client, ExtractedRow, Period, StoredFile, get_session
from apps.engine.recon import (
    compare_bank_ledger,
    compare_records,
    money,
)

WORKFLOWS: tuple[dict, ...] = (
    {
        "id": "gst_2b_invoices",
        "label": "GSTR-2B vs purchase invoices",
        "description": "Match portal invoices against bills extracted from client PDFs.",
        "left_label": "GSTR-2B",
        "right_label": "Purchase invoices",
        "left_key": "gstr_2b",
        "right_key": "invoices",
        "rules": (
            "GSTIN and invoice number must agree.",
            "Totals must agree within ₹1. Tax and taxable values are also checked.",
            "Different invoice numbers or a missing GSTIN only become review candidates.",
        ),
    },
    {
        "id": "gst_2b_purchase_register",
        "label": "GSTR-2B vs purchase register",
        "description": "Match portal invoices against the purchase register in a Tally or Zoho export.",
        "left_label": "GSTR-2B",
        "right_label": "Purchase register",
        "left_key": "gstr_2b",
        "right_key": "purchase_register",
        "rules": (
            "GSTIN and invoice number must agree.",
            "Totals must agree within ₹1. Tax and taxable values are also checked.",
            "Rows without a shared reference are left for review, never auto-matched.",
        ),
    },
    {
        "id": "invoices_purchase_register",
        "label": "Purchase invoices vs purchase register",
        "description": "Check that every extracted bill is present in the purchase register.",
        "left_label": "Purchase invoices",
        "right_label": "Purchase register",
        "left_key": "invoices",
        "right_key": "purchase_register",
        "rules": (
            "GSTIN and invoice number must agree.",
            "Totals must agree within ₹1. Tax and taxable values are also checked.",
            "Duplicate references are reported instead of being paired arbitrarily.",
        ),
    },
    {
        "id": "bank_accounting",
        "label": "Bank statement vs accounting ledger",
        "description": "Look for bank lines in Tally payment, receipt, contra or bank vouchers.",
        "left_label": "Bank statement",
        "right_label": "Accounting ledger",
        "left_key": "bank",
        "right_key": "bank_ledger",
        "rules": (
            "A voucher reference in the bank narration plus an agreeing amount is a match.",
            "Without a reference, matching amount, nearby date and party name only become review candidates.",
            "Amount similarity alone never produces a match.",
        ),
    },
)

_WORKFLOW_BY_ID = {item["id"]: item for item in WORKFLOWS}


def _public_workflow(workflow: dict) -> dict:
    return {
        "id": workflow["id"],
        "label": workflow["label"],
        "description": workflow["description"],
        "left_label": workflow["left_label"],
        "right_label": workflow["right_label"],
        "rules": list(workflow["rules"]),
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
    return row


def _load_extracted(period_id: int, kinds: Iterable[str]) -> list[dict]:
    session = get_session()
    try:
        records = (
            session.query(ExtractedRow, StoredFile)
            .join(StoredFile, ExtractedRow.file_id == StoredFile.id)
            .filter(
                ExtractedRow.period_id == period_id,
                ExtractedRow.kind.in_(tuple(kinds)),
            )
            .order_by(ExtractedRow.id.asc())
            .all()
        )
        rows: list[dict] = []
        for extracted, stored in records:
            row = _row_payload(extracted, stored)
            if row is not None:
                rows.append(row)
        return rows
    finally:
        session.close()


def _is_purchase_register(row: dict) -> bool:
    register = str(row.get("register") or "").strip().lower()
    if register in {"purchase", "purchases", "bill", "bills"}:
        return True
    voucher = str(row.get("voucher_type") or "").strip().lower()
    if "purchase" in voucher or voucher in {"bill", "bills"}:
        return True
    return False


def _is_invoice_header(row: dict) -> bool:
    """Invoice extraction stores header and line-item rows under one kind.

    Reconciliation compares invoices, not their individual line items.  Line
    items carry a description; headers carry an invoice number, GSTIN, or
    invoice value.
    """
    if row.get("description"):
        return False
    return bool(
        row.get("invoice_number")
        or row.get("supplier_gstin")
        or row.get("customer_gstin")
        or row.get("invoice_value") is not None
        or (row.get("supplier_name") and row.get("customer_name"))
    )


def _is_bank_ledger(row: dict) -> bool:
    voucher = str(row.get("voucher_type") or "").strip().lower()
    if not voucher:
        return False
    return any(
        marker in voucher
        for marker in ("payment", "receipt", "contra", "bank")
    )


def _period_datasets(period_id: int) -> dict[str, list[dict]]:
    invoices = [
        row
        for row in _load_extracted(period_id, ("invoice",))
        if _is_invoice_header(row)
    ]
    gstr_2b = [
        row
        for row in _load_extracted(period_id, ("gstr_2b",))
        if not str(row.get("document_type") or "").upper().startswith("CDN")
    ]
    books = _load_extracted(period_id, ("tally", "zoho"))
    return {
        "gstr_2b": gstr_2b,
        "invoices": invoices,
        "purchase_register": [row for row in books if _is_purchase_register(row)],
        "bank": _load_extracted(period_id, ("bank",)),
        "bank_ledger": [row for row in books if _is_bank_ledger(row)],
    }


def _availability(workflow: dict, datasets: dict[str, list[dict]]) -> dict:
    left_count = len(datasets.get(workflow["left_key"]) or [])
    right_count = len(datasets.get(workflow["right_key"]) or [])
    missing = []
    if left_count == 0:
        missing.append(workflow["left_label"])
    if right_count == 0:
        missing.append(workflow["right_label"])
    return {
        "id": workflow["id"],
        "available": left_count > 0 and right_count > 0,
        "missing": missing,
        "left_count": left_count,
        "right_count": right_count,
    }


def _period_summary(period: Period, client: Client, file_count: int, datasets: dict) -> dict:
    availability = [
        _availability(workflow, datasets) for workflow in WORKFLOWS
    ]
    return {
        "id": period.id,
        "label": period.label,
        "client_id": client.id,
        "client_name": client.name,
        "file_count": file_count,
        "created_at": period.created_at.isoformat() if period.created_at else None,
        "datasets": {
            key: len(rows or []) for key, rows in datasets.items()
        },
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
        datasets = _period_datasets(period.id)
        periods.append(_period_summary(period, client, file_count, datasets))

    selected = next(
        (item["id"] for item in periods if item["has_comparison"]),
        periods[0]["id"] if periods else None,
    )
    return {
        "periods": periods,
        "workflows": [_public_workflow(workflow) for workflow in WORKFLOWS],
        "selected_period_id": selected,
    }


def _sum_amounts(rows: list[dict]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        value = money(row.get("invoice_value"))
        if value is None:
            value = money(row.get("amount"))
        if value is None:
            debit = money(row.get("debit"))
            credit = money(row.get("credit"))
            value = debit if debit not in (None, Decimal("0")) else credit
        if value is not None:
            total += value
    return total


def _dataset_sources(rows: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    for row in rows:
        file_id = row.get("_ca_file_id")
        if file_id is None or file_id in seen:
            continue
        seen[file_id] = {
            "file_id": file_id,
            "file_name": row.get("_ca_file_name") or row.get("source") or "",
            "kind": row.get("_ca_kind") or "",
            "rows": 0,
        }
    for row in rows:
        file_id = row.get("_ca_file_id")
        if file_id in seen:
            seen[file_id]["rows"] += 1
    return list(seen.values())


def _missing_message(workflow: dict, missing: list[str]) -> str:
    if len(missing) == 2:
        return (
            f"{workflow['label']} needs both {workflow['left_label']} and "
            f"{workflow['right_label']} data for this period. Nothing is calculated "
            "until both are present."
        )
    return (
        f"{workflow['label']} needs {missing[0]} data for this period. "
        "Nothing is calculated until it is available."
    )


def _result_totals(
    left_rows: list[dict], right_rows: list[dict], result_rows: list[dict]
) -> dict:
    left_total = _sum_amounts(left_rows)
    right_total = _sum_amounts(right_rows)
    matched_total = Decimal("0")
    matched_tax = Decimal("0")
    for row in result_rows:
        if row.get("status") != "matched":
            continue
        left = row.get("left") or {}
        amount = money(left.get("amount"))
        if amount is not None:
            matched_total += amount
        tax = money(left.get("tax"))
        if tax is not None:
            matched_tax += tax
    return {
        "left_amount": float(left_total),
        "right_amount": float(right_total),
        "matched_amount": float(matched_total),
        "matched_tax": float(matched_tax),
        "difference": float(left_total - right_total),
        "left_rows": len(left_rows),
        "right_rows": len(right_rows),
    }


def run_reconciliation(period_id: int, workflow_id: str) -> dict:
    workflow = _WORKFLOW_BY_ID.get(str(workflow_id or ""))
    if workflow is None:
        raise ValueError("That reconciliation workflow is not available.")

    session = get_session()
    try:
        period = session.get(Period, period_id)
        client = session.get(Client, period.client_id) if period else None
        if period is None or client is None:
            raise ValueError("Period was not found.")
        period_payload = {
            "id": period.id,
            "label": period.label,
            "client_id": client.id,
            "client_name": client.name,
        }
    finally:
        session.close()

    datasets = _period_datasets(period_id)
    availability = _availability(workflow, datasets)
    public_workflow = _public_workflow(workflow)
    if not availability["available"]:
        return {
            "available": False,
            "workflow": public_workflow,
            "period": period_payload,
            "datasets": {key: len(value) for key, value in datasets.items()},
            "missing": availability["missing"],
            "message": _missing_message(workflow, availability["missing"]),
        }

    left_rows = datasets[workflow["left_key"]]
    right_rows = datasets[workflow["right_key"]]
    if workflow["id"] == "bank_accounting":
        result = compare_bank_ledger(left_rows, right_rows)
    else:
        result = compare_records(left_rows, right_rows)
    rows = result.get("rows") or []
    return {
        "available": True,
        "workflow": public_workflow,
        "period": period_payload,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": {
            "left": {
                "label": workflow["left_label"],
                "count": len(left_rows),
                "sources": _dataset_sources(left_rows),
            },
            "right": {
                "label": workflow["right_label"],
                "count": len(right_rows),
                "sources": _dataset_sources(right_rows),
            },
        },
        "counts": result.get("counts") or {},
        "totals": _result_totals(left_rows, right_rows, rows),
        "rows": rows,
    }


def latest_reconciliation_summary(workspace: dict | None = None) -> dict:
    """Return the newest available comparison for the dashboard."""
    workspace = workspace or reconciliation_workspace()
    for period in workspace.get("periods") or []:
        available = {
            item["id"]: item for item in period.get("workflows") or []
        }
        for workflow in WORKFLOWS:
            status = available.get(workflow["id"]) or {}
            if not status.get("available"):
                continue
            result = run_reconciliation(period["id"], workflow["id"])
            if not result.get("available"):
                continue
            counts = result.get("counts") or {}
            return {
                "available": True,
                "period_id": period["id"],
                "period_label": period["label"],
                "client_name": period["client_name"],
                "workflow_id": workflow["id"],
                "workflow_label": workflow["label"],
                "left_label": workflow["left_label"],
                "right_label": workflow["right_label"],
                "counts": counts,
                "totals": result.get("totals") or {},
                "generated_at": result.get("generated_at"),
            }
    return {
        "available": False,
        "message": (
            "No period has two compatible processed datasets yet. Process the "
            "source documents first, then open Reconciliation."
        ),
    }
