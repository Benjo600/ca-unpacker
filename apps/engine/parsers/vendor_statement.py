"""Supplier / vendor statement parser.

Vendor statements are tabular documents (XLSX, CSV or PDF) with invoice or
reference numbers, dates, debit/credit values and often a running balance.  The
generic financial table reader already understands those headers, so this
module adapts its canonical SAP-style rows into the vendor-statement shape used
by the reconciliation workflow.
"""

from __future__ import annotations

from pathlib import Path

from apps.engine.parsers.sap.parser import parse_sap_file


def _first(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_vendor_statement_file(path: Path, filename: str | None = None) -> dict:
    path = Path(path)
    source = filename or path.name
    parsed = parse_sap_file(path, source)
    rows = []
    for row in parsed.get("rows") or []:
        if not isinstance(row, dict):
            continue
        invoice_date = _first(row, "document_date", "posting_date")
        amount = _first(row, "amount")
        debit = _first(row, "debit")
        credit = _first(row, "credit")
        if amount is None:
            try:
                amount = abs(float(debit or 0) - float(credit or 0))
            except (TypeError, ValueError):
                amount = None
        adapted = dict(row)
        adapted.update(
            {
                "register": "vendor_statement",
                "party_name": _first(row, "party_name", "account_name") or "",
                "supplier_name": _first(row, "party_name", "account_name") or "",
                "gstin": _first(row, "gstin") or "",
                "supplier_gstin": _first(row, "gstin") or "",
                "invoice_number": _first(row, "invoice_number", "reference") or "",
                "invoice_date": invoice_date,
                "date": invoice_date,
                "invoice_value": amount,
                "amount": amount,
                "debit": debit,
                "credit": credit,
                "balance": _first(row, "balance", "closing_balance"),
                "narration": _first(row, "description", "narration") or "",
                "document_type": _first(row, "document_type") or "Vendor statement",
                "source": row.get("source") or source,
            }
        )
        rows.append(adapted)
    return {
        "rows": rows,
        "error": parsed.get("error"),
        "reason": parsed.get("reason"),
        "warnings": parsed.get("warnings") or [],
        "report_type": "vendor_statement",
    }
