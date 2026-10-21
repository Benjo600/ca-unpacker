from __future__ import annotations

from pathlib import Path

from apps.engine.parsers.sap.reports import (
    normalize_table,
    stated_totals,
    validate_rows,
)
from apps.engine.parsers.sap.signatures import (
    detect_report_type,
    report_label,
)
from apps.engine.parsers.sap.tables import read_tables


def parse_sap_file(path: Path, filename: str | None = None) -> dict:
    """Parse one SAP financial export into canonical transaction rows.

    The file has already been classified (or manually assigned) as SAP.  This
    function still validates the table structure and returns a readable reason
    for unsupported layouts rather than raising into the dump worker.
    """
    path = Path(path)
    source = filename or path.name
    try:
        loaded = read_tables(path, source)
    except Exception as exc:
        return {
            "rows": [],
            "error": str(exc) or "Could not read this SAP report.",
            "warnings": [],
        }

    tables = loaded.get("tables") or []
    warnings: list[str] = []
    if loaded.get("error"):
        return {
            "rows": [],
            "error": loaded["error"],
            "pdf_type": loaded.get("pdf_type"),
            "warnings": warnings,
        }
    if not tables:
        reason = (
            loaded.get("reason")
            or "No supported SAP financial table header was found in this file."
        )
        return {
            "rows": [],
            "reason": reason,
            "pdf_type": loaded.get("pdf_type"),
            "warnings": [reason] if reason else [],
            "engine": loaded.get("engine"),
        }

    rows: list[dict] = []
    report_types: list[str] = []
    validation: dict[str, dict] = {}
    for table in tables:
        fields = set(table.field_headers)
        context = f"{table.sheet or ''} {table.context}".strip()
        report_type, report_reason = detect_report_type(
            fields,
            context=context,
            filename=source,
        )
        table_label = report_label(report_type)
        table_name = table.sheet or "report"
        if report_type == "other":
            warning = (
                f"SAP report type was not identified for {table_name}; "
                "rows were kept under the generic SAP ledger profile."
            )
            if warning not in warnings:
                warnings.append(warning)
        table_rows = normalize_table(table, report_type, source=source)
        if not table_rows:
            warning = (
                f"SAP {table_label} table in {table_name} had no usable transaction rows."
            )
            if warning not in warnings:
                warnings.append(warning)
            continue
        totals = stated_totals(table.records)
        validation_warnings = validate_rows(
            table_rows,
            report_type=report_type,
            totals=totals,
        )
        for warning in validation_warnings:
            if warning not in warnings:
                warnings.append(warning)
        validation[table_name] = {
            "report_type": report_type,
            "reason": report_reason,
            "totals": totals,
            "warnings": validation_warnings,
            "row_count": len(table_rows),
        }
        rows.extend(table_rows)
        if report_type not in report_types:
            report_types.append(report_type)

    if not rows:
        reason = (
            "SAP report structure was recognised, but no supported transaction rows "
            "could be read from this layout."
        )
        if warnings:
            reason = warnings[-1]
        return {
            "rows": [],
            "reason": reason,
            "warnings": warnings,
            "report_types": report_types,
            "pdf_type": loaded.get("pdf_type"),
            "engine": loaded.get("engine"),
            "validation": validation,
        }

    return {
        "rows": rows,
        "report_type": report_types[0] if report_types else None,
        "report_types": report_types,
        "warnings": warnings,
        "validation": validation,
        "pdf_type": loaded.get("pdf_type"),
        "engine": loaded.get("engine"),
    }
