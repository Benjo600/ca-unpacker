"""Excel and PDF exports for persisted reconciliation runs.

The workbook is a complete evidence pack: executive summary, matched records,
unmatched records on both sides, exceptions, duplicates, partial matches,
manual decisions, audit history and source references.  Every figure is read
from the persisted run snapshot, never recalculated from a live dataset.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.engine.db import (
    ReconAuditEvent,
    ReconException,
    ReconMatch,
    ReconRun,
    get_session,
)
from apps.engine.recon_engine import EXCEPTION_LABELS
from apps.engine.settings import period_output_dir


def _json_load(text: str | None, fallback):
    try:
        value = json.loads(text or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return value

HEADER_FILL = PatternFill("solid", fgColor="0F2B46")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=16, color="0F2B46")
SECTION_FONT = Font(bold=True, size=12, color="0F2B46")
TOTAL_FILL = PatternFill("solid", fgColor="E8EEF5")
WARNING_FILL = PatternFill("solid", fgColor="FFF4E5")
DANGER_FILL = PatternFill("solid", fgColor="FDE8E8")
GOOD_FILL = PatternFill("solid", fgColor="E7F4EC")
THIN = Side(style="thin", color="D5DDE5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY_FORMAT = '[>=10000000]"₹"##\\,##\\,##\\,##0.00;[>=100000]"₹"##\\,##\\,##0.00;"₹"##\\,##0.00'
DATE_FORMAT = "DD-MMM-YYYY HH:MM"

STATUS_TONES = {
    "matched": GOOD_FILL,
    "accepted": GOOD_FILL,
    "manual": GOOD_FILL,
    "timing_difference": GOOD_FILL,
    "approved_adjustment": GOOD_FILL,
    "proposed": WARNING_FILL,
    "unmatched": DANGER_FILL,
    "duplicate": DANGER_FILL,
    "reversal_candidate": DANGER_FILL,
    "rejected": DANGER_FILL,
}


def _money(value: Any):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _status_label(status: str) -> str:
    return str(status or "").replace("_", " ").title()


def _write_title(sheet, title: str, subtitle: str = "") -> int:
    sheet["A1"] = title
    sheet["A1"].font = TITLE_FONT
    if subtitle:
        sheet["A2"] = subtitle
        sheet["A2"].font = Font(italic=True, color="5B6B7C")
        return 4
    return 3


def _write_header(sheet, row: int, headers: Sequence[str]) -> int:
    for column, value in enumerate(headers, start=1):
        cell = sheet.cell(row, column, value)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDER
    sheet.row_dimensions[row].height = 28
    return row + 1


def _finish_table(sheet, header_row: int, last_row: int, last_column: int) -> None:
    if last_row >= header_row:
        sheet.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(last_column)}{last_row}"
        )
        sheet.freeze_panes = f"A{header_row + 1}"
    for column in range(1, last_column + 1):
        width = 18
        for row in range(header_row, min(last_row, header_row + 80) + 1):
            value = sheet.cell(row, column).value
            if value is not None:
                width = max(width, min(52, len(str(value)) + 3))
        sheet.column_dimensions[get_column_letter(column)].width = width


def _write_kv(sheet, row: int, key: str, value: Any) -> int:
    sheet.cell(row, 1, key).font = Font(bold=True)
    sheet.cell(row, 2, value)
    return row + 1


def _exception_label(category: str) -> str:
    return EXCEPTION_LABELS.get(category, str(category).replace("_", " ").title())


def _record_label(record: Mapping) -> str:
    reference = str(record.get("reference") or "")
    party = str(record.get("party") or "")
    if reference and party:
        return f"{reference} · {party}"
    return reference or party or str(record.get("source") or "record")


def _record_amount(record: Mapping) -> Any:
    return _money(record.get("amount"))


def _match_amount(match: ReconMatch) -> float | None:
    values = [value for value in (match.left_amount, match.right_amount) if value is not None]
    return _money(max(values)) if values else None


def _source_rows(records: Iterable[Mapping]) -> list[list[Any]]:
    rows = []
    for record in records:
        rows.append(
            [
                record.get("row_id"),
                record.get("file_id"),
                record.get("file_name") or record.get("source") or "",
                record.get("kind") or "",
                record.get("source_page") or "",
                record.get("source_bbox") or "",
                record.get("reference") or "",
                record.get("party") or "",
                record.get("gstin") or "",
                record.get("date") or "",
                _money(record.get("amount")),
                record.get("currency") or "",
            ]
        )
    return rows


def export_reconciliation(run_id: int) -> dict:
    session = get_session()
    try:
        run = session.get(ReconRun, int(run_id))
        if run is None:
            raise ValueError("That reconciliation run was not found.")
        matches = (
            session.query(ReconMatch)
            .filter(ReconMatch.run_id == run.id, ReconMatch.is_superseded == 0)
            .order_by(ReconMatch.ordinal.asc(), ReconMatch.id.asc())
            .all()
        )
        exceptions = (
            session.query(ReconException)
            .filter(ReconException.run_id == run.id)
            .order_by(ReconException.id.asc())
            .all()
        )
        audit = (
            session.query(ReconAuditEvent)
            .filter(ReconAuditEvent.run_id == run.id)
            .order_by(ReconAuditEvent.id.asc())
            .all()
        )
        counts = _json_load(run.counts_json, {})
        totals = _json_load(run.totals_json, {})
        checks = _json_load(run.checks_json, [])
        rules = _json_load(run.rules_snapshot_json, {})
        source_files = _json_load(run.source_files_json, [])
        folder = period_output_dir(run.client_name, run.period_label) / "Reconciliation"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"Reconciliation_{run.workflow_id}_{run.run_uuid[:8]}_{stamp}"
        xlsx_path = folder / f"{stem}.xlsx"
        pdf_path = folder / f"{stem}_summary.pdf"
        generated = datetime.now()
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Executive Summary"
        _write_summary(
            summary, run, counts, totals, checks, rules, source_files, generated
        )
        _write_match_sheet(
            workbook,
            "Matched",
            [match for match in matches if match.status in {"matched", "accepted", "manual", "timing_difference", "approved_adjustment"}],
            run,
        )
        _write_match_sheet(
            workbook,
            "Unmatched Source",
            [match for match in matches if match.status in {"unmatched", "rejected"} and _json_load(match.left_records_json, [])],
            run,
        )
        _write_match_sheet(
            workbook,
            "Unmatched Destination",
            [match for match in matches if match.status in {"unmatched", "rejected"} and _json_load(match.right_records_json, [])],
            run,
        )
        _write_exceptions_sheet(
            workbook,
            "Exceptions & Variances",
            exceptions,
            matches,
            run,
        )
        _write_match_sheet(
            workbook,
            "Duplicates",
            [match for match in matches if match.status == "duplicate"],
            run,
        )
        _write_match_sheet(
            workbook,
            "Partial Matches",
            [match for match in matches if match.classification == "partial" or match.match_type in {"partial", "one_to_many", "many_to_one", "manual_allocation"}],
            run,
        )
        _write_adjustments_sheet(workbook, matches, audit, run)
        _write_audit_sheet(workbook, audit, run)
        _write_sources_sheet(workbook, matches, run)
        workbook.save(xlsx_path)
        _write_pdf_summary(
            pdf_path, run, counts, totals, checks, exceptions, generated
        )
        return {
            "run_id": run.id,
            "run_uuid": run.run_uuid,
            "folder": str(folder),
            "xlsx": str(xlsx_path),
            "pdf": str(pdf_path),
            "generated_at": generated.isoformat(),
        }
    finally:
        session.close()


def _write_summary(
    sheet,
    run: ReconRun,
    counts: Mapping,
    totals: Mapping,
    checks: Sequence[Mapping],
    rules: Mapping,
    source_files: Sequence[Mapping],
    generated: datetime,
) -> None:
    row = _write_title(
        sheet,
        "Reconciliation Executive Summary",
        f"{run.client_name} · {run.period_label} · {run.workflow_label}",
    )
    details = [
        ("Client", run.client_name),
        ("Financial year", run.financial_year),
        ("Period", run.period_label),
        ("Reconciliation type", run.workflow_label),
        ("Run ID", run.run_uuid),
        ("Run timestamp", run.created_at.strftime("%d-%b-%Y %H:%M") if run.created_at else ""),
        ("Generated", generated.strftime("%d-%b-%Y %H:%M")),
        ("Rules version", f"{rules.get('ruleset', {}).get('name', 'Default')} v{rules.get('ruleset', {}).get('version', 1)}"),
        ("Engine", rules.get("engine_version") or ""),
        ("Completion status", _status_label(run.completion_status)),
        ("Actor", run.actor or "local user"),
    ]
    for key, value in details:
        row = _write_kv(sheet, row, key, value)
    row += 1
    sheet.cell(row, 1, "Run metrics").font = SECTION_FONT
    row += 1
    row = _write_header(
        sheet,
        row,
        ["Metric", "Value"],
    )
    metrics = [
        ("Total records processed", int(totals.get("records_processed") or 0)),
        ("Matched records", int(totals.get("matched_records") or 0)),
        ("Unmatched records", int(totals.get("unmatched_records") or 0)),
        ("Requiring investigation", int(totals.get("proposed_records") or 0) + int(totals.get("duplicate_records") or 0)),
        ("Duplicate records", int(totals.get("duplicate_records") or 0)),
        ("Amount discrepancies", int(totals.get("amount_discrepancies") or 0)),
        ("Open exceptions", int(totals.get("open_exceptions") or 0)),
        ("Total exceptions", int(totals.get("total_exceptions") or 0)),
        ("Match rate %", float(totals.get("match_rate") or 0)),
        ("Total debit value", _money(totals.get("debit_total"))),
        ("Total credit value", _money(totals.get("credit_total"))),
        ("Unresolved exception value", _money(totals.get("unresolved_amount"))),
    ]
    for label, value in metrics:
        sheet.cell(row, 1, label).border = BORDER
        cell = sheet.cell(row, 2, value)
        cell.border = BORDER
        if "value" in label.lower() or "amount" in label.lower():
            cell.number_format = MONEY_FORMAT
        row += 1
    row += 1
    sheet.cell(row, 1, "Source totals").font = SECTION_FONT
    row += 1
    row = _write_header(sheet, row, ["Side", "Rows", "Amount", "Debit", "Credit"])
    for side_key, label in (("left", "Source A"), ("right", "Source B")):
        amount = _money(totals.get(f"{side_key}_amount"))
        values = [
            label,
            int(totals.get(f"{side_key}_rows") or 0),
            amount,
            None,
            None,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.border = BORDER
            if column == 3:
                cell.number_format = MONEY_FORMAT
        row += 1
    row += 1
    sheet.cell(row, 1, "Balance and source checks").font = SECTION_FONT
    row += 1
    if checks:
        row = _write_header(sheet, row, ["Check", "Status", "Difference", "Explanation"])
        for check in checks:
            sheet.cell(row, 1, check.get("name") or "").border = BORDER
            sheet.cell(row, 2, _status_label(str(check.get("status") or ""))).border = BORDER
            cell = sheet.cell(row, 3, _money(check.get("difference")))
            cell.border = BORDER
            cell.number_format = MONEY_FORMAT
            sheet.cell(row, 4, check.get("explanation") or "").border = BORDER
            row += 1
    else:
        sheet.cell(row, 1, "No balance check was applicable to this workflow.")
        row += 1
    row += 1
    sheet.cell(row, 1, "Rules snapshot").font = SECTION_FONT
    row += 1
    for note in rules.get("summary") or []:
        sheet.cell(row, 1, note)
        row += 1
    row += 1
    sheet.cell(row, 1, "Source documents").font = SECTION_FONT
    row += 1
    if source_files:
        row = _write_header(sheet, row, ["File ID", "File name", "Type", "Rows"])
        for source in source_files:
            sheet.cell(row, 1, source.get("file_id")).border = BORDER
            sheet.cell(row, 2, source.get("file_name")).border = BORDER
            sheet.cell(row, 3, source.get("kind")).border = BORDER
            sheet.cell(row, 4, source.get("rows")).border = BORDER
            row += 1
    else:
        sheet.cell(row, 1, "No source file metadata was recorded.")
    sheet.column_dimensions["A"].width = 38
    sheet.column_dimensions["B"].width = 34
    sheet.column_dimensions["C"].width = 22
    sheet.column_dimensions["D"].width = 70
    sheet.freeze_panes = "A4"


MATCH_HEADERS = [
    "Status",
    "Classification",
    "Confidence",
    "Match type",
    "Reference (Source A)",
    "Reference (Source B)",
    "Party / counterparty",
    "Date A",
    "Date B",
    "Amount A",
    "Amount B",
    "Difference",
    "Currency",
    "Reason",
    "Explanation",
    "Source A file",
    "Page A",
    "Source B file",
    "Page B",
    "Allocation",
    "Decided by",
    "Decision reason",
]


def _write_match_sheet(workbook: Workbook, title: str, matches: Sequence[ReconMatch], run: ReconRun) -> None:
    sheet = workbook.create_sheet(title[:31])
    row = _write_title(
        sheet,
        title,
        f"{run.client_name} · {run.period_label} · run {run.run_uuid[:8]}",
    )
    row = _write_header(sheet, row, MATCH_HEADERS)
    header_row = row - 1
    for match in matches:
        left = _json_load(match.left_records_json, [])
        right = _json_load(match.right_records_json, [])
        left_first = left[0] if left else {}
        right_first = right[0] if right else {}
        allocations = _json_load(match.allocations_json, [])
        values = [
            _status_label(match.status),
            match.classification.replace("_", " ").title(),
            match.confidence,
            match.match_type.replace("_", " ").title(),
            str(left_first.get("reference") or ""),
            str(right_first.get("reference") or ""),
            str(left_first.get("party") or right_first.get("party") or ""),
            str(left_first.get("date") or ""),
            str(right_first.get("date") or ""),
            _money(match.left_amount),
            _money(match.right_amount),
            _money(match.difference_amount),
            match.currency or "",
            match.reason_code,
            match.explanation,
            str(left_first.get("file_name") or left_first.get("source") or ""),
            left_first.get("source_page") or "",
            str(right_first.get("file_name") or right_first.get("source") or ""),
            right_first.get("source_page") or "",
            "; ".join(
                f"{item.get('left_id')}→{item.get('right_id')}: {item.get('amount')}"
                for item in allocations
            ),
            match.decided_by or "",
            match.decision_reason or "",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=column in {15, 21, 22})
            if column in {10, 11, 12}:
                cell.number_format = MONEY_FORMAT
        fill = STATUS_TONES.get(match.status)
        if fill is not None:
            sheet.cell(row, 1).fill = fill
        row += 1
    if matches:
        sheet.cell(row, 1, "TOTAL").font = Font(bold=True)
        sheet.cell(row, 10, _money(sum(float(match.left_amount or 0) for match in matches))).number_format = MONEY_FORMAT
        sheet.cell(row, 11, _money(sum(float(match.right_amount or 0) for match in matches))).number_format = MONEY_FORMAT
        sheet.cell(row, 12, _money(sum(float(match.difference_amount or 0) for match in matches))).number_format = MONEY_FORMAT
        for column in range(1, len(MATCH_HEADERS) + 1):
            sheet.cell(row, column).fill = TOTAL_FILL
            sheet.cell(row, column).font = Font(bold=True)
            sheet.cell(row, column).border = BORDER
        row += 1
    else:
        sheet.cell(row, 1, "No rows in this section.")
    _finish_table(sheet, header_row, max(header_row, row - 1), len(MATCH_HEADERS))


def _write_exceptions_sheet(
    workbook: Workbook,
    title: str,
    exceptions: Sequence[ReconException],
    matches: Sequence[ReconMatch],
    run: ReconRun,
) -> None:
    sheet = workbook.create_sheet(title[:31])
    row = _write_title(
        sheet,
        title,
        f"{run.client_name} · {run.period_label} · run {run.run_uuid[:8]}",
    )
    headers = [
        "Exception ID",
        "Category",
        "Status",
        "Severity",
        "Title",
        "Amount",
        "Currency",
        "Assigned to",
        "Resolution reason",
        "Source references",
        "Created",
        "Resolved",
    ]
    row = _write_header(sheet, row, headers)
    header_row = row - 1
    for exception in exceptions:
        source_refs = _json_load(exception.source_refs_json, [])
        values = [
            exception.id,
            _exception_label(exception.category),
            _status_label(exception.status),
            exception.severity.title(),
            exception.title,
            _money(exception.amount),
            exception.currency or "",
            exception.assigned_to or "",
            exception.resolution_reason or "",
            "; ".join(
                f"{item.get('file_name') or 'source'}"
                + (f" p.{item.get('page')}" if item.get("page") else "")
                for item in source_refs
            ),
            exception.created_at.strftime("%d-%b-%Y %H:%M") if exception.created_at else "",
            exception.resolved_at.strftime("%d-%b-%Y %H:%M") if exception.resolved_at else "",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.border = BORDER
            if column == 6:
                cell.number_format = MONEY_FORMAT
        status_fill = {
            "open": DANGER_FILL,
            "investigating": WARNING_FILL,
            "assigned": WARNING_FILL,
            "resolved": GOOD_FILL,
            "approved": GOOD_FILL,
            "timing_difference": GOOD_FILL,
            "approved_adjustment": GOOD_FILL,
            "reopened": WARNING_FILL,
        }.get(exception.status)
        if status_fill is not None:
            sheet.cell(row, 3).fill = status_fill
        row += 1
    if exceptions:
        sheet.cell(row, 1, "TOTAL").font = Font(bold=True)
        total_cell = sheet.cell(row, 6, _money(sum(float(exception.amount or 0) for exception in exceptions)))
        total_cell.number_format = MONEY_FORMAT
        for column in range(1, len(headers) + 1):
            sheet.cell(row, column).fill = TOTAL_FILL
            sheet.cell(row, column).font = Font(bold=True)
            sheet.cell(row, column).border = BORDER
        row += 1
    else:
        sheet.cell(row, 1, "No exceptions in this run.")
    _finish_table(sheet, header_row, max(header_row, row - 1), len(headers))


def _write_adjustments_sheet(
    workbook: Workbook,
    matches: Sequence[ReconMatch],
    audit: Sequence[ReconAuditEvent],
    run: ReconRun,
) -> None:
    sheet = workbook.create_sheet("Manual Adjustments")
    row = _write_title(
        sheet,
        "Manual Adjustments and Decisions",
        f"{run.client_name} · {run.period_label} · run {run.run_uuid[:8]}",
    )
    headers = [
        "Match ID",
        "Status",
        "Classification",
        "Amount A",
        "Amount B",
        "Difference",
        "Decided by",
        "Decided at",
        "Reason",
    ]
    row = _write_header(sheet, row, headers)
    header_row = row - 1
    decisions = [
        match
        for match in matches
        if match.status in {"manual", "accepted", "timing_difference", "approved_adjustment"}
        or match.decided_by
    ]
    for match in decisions:
        values = [
            match.id,
            _status_label(match.status),
            match.classification.replace("_", " ").title(),
            _money(match.left_amount),
            _money(match.right_amount),
            _money(match.difference_amount),
            match.decided_by or "",
            match.decided_at.strftime("%d-%b-%Y %H:%M") if match.decided_at else "",
            match.decision_reason or "",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.border = BORDER
            if column in {4, 5, 6}:
                cell.number_format = MONEY_FORMAT
        row += 1
    if not decisions:
        sheet.cell(row, 1, "No manual decisions were recorded.")
    _finish_table(sheet, header_row, max(header_row, row - 1), len(headers))
    row += 2
    sheet.cell(row, 1, "Decision audit events").font = SECTION_FONT
    row += 1
    headers = ["Timestamp", "Actor", "Action", "Previous", "New", "Reason", "Record refs"]
    row = _write_header(sheet, row, headers)
    header_row = row - 1
    for event in audit:
        if event.action not in {
            "match_accepted",
            "match_rejected",
            "match_unmatched",
            "manual_match",
            "manual_match_superseded",
            "exception_updated",
            "note_added",
        }:
            continue
        values = [
            event.created_at.strftime("%d-%b-%Y %H:%M") if event.created_at else "",
            event.actor,
            event.action.replace("_", " ").title(),
            _status_label(event.previous_status or ""),
            _status_label(event.new_status or ""),
            event.reason or "",
            ", ".join(str(item) for item in _json_load(event.record_refs_json, [])),
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row, column, value).border = BORDER
        row += 1
    _finish_table(sheet, header_row, max(header_row, row - 1), len(headers))


def _write_audit_sheet(workbook: Workbook, audit: Sequence[ReconAuditEvent], run: ReconRun) -> None:
    sheet = workbook.create_sheet("Audit History")
    row = _write_title(
        sheet,
        "Audit History",
        f"{run.client_name} · {run.period_label} · run {run.run_uuid}",
    )
    headers = [
        "Event ID",
        "Timestamp",
        "Actor",
        "Action",
        "Match ID",
        "Exception ID",
        "Previous status",
        "New status",
        "Reason",
        "Record references",
        "Evidence references",
    ]
    row = _write_header(sheet, row, headers)
    header_row = row - 1
    for event in audit:
        values = [
            event.id,
            event.created_at.strftime("%d-%b-%Y %H:%M:%S") if event.created_at else "",
            event.actor,
            event.action.replace("_", " ").title(),
            event.match_id or "",
            event.exception_id or "",
            _status_label(event.previous_status or ""),
            _status_label(event.new_status or ""),
            event.reason or "",
            ", ".join(str(item) for item in _json_load(event.record_refs_json, [])),
            ", ".join(str(item) for item in _json_load(event.evidence_refs_json, [])),
        ]
        for column, value in enumerate(values, start=1):
            sheet.cell(row, column, value).border = BORDER
        row += 1
    if not audit:
        sheet.cell(row, 1, "The audit trail is empty.")
    _finish_table(sheet, header_row, max(header_row, row - 1), len(headers))


def _write_sources_sheet(workbook: Workbook, matches: Sequence[ReconMatch], run: ReconRun) -> None:
    sheet = workbook.create_sheet("Source References")
    row = _write_title(
        sheet,
        "Source References",
        f"Every row below points back to the stored source document. Run {run.run_uuid[:8]}.",
    )
    headers = [
        "Match ID",
        "Side",
        "Row ID",
        "File ID",
        "File name",
        "Kind",
        "Page",
        "BBox",
        "Reference",
        "Party",
        "GSTIN",
        "Date",
        "Amount",
        "Currency",
    ]
    row = _write_header(sheet, row, headers)
    header_row = row - 1
    for match in matches:
        for side, key in (("A", "left_records_json"), ("B", "right_records_json")):
            for record in _json_load(getattr(match, key), []):
                values = [
                    match.id,
                    side,
                    *(
                        _source_rows([record])[0]
                        if _source_rows([record])
                        else [None] * 12
                    ),
                ]
                for column, value in enumerate(values, start=1):
                    cell = sheet.cell(row, column, value)
                    cell.border = BORDER
                    if column == 13:
                        cell.number_format = MONEY_FORMAT
                row += 1
    if row == header_row + 1:
        sheet.cell(row, 1, "No source records were stored for this run.")
    _finish_table(sheet, header_row, max(header_row, row - 1), len(headers))


def _pdf_safe(text: Any) -> str:
    value = str(text or "")
    replacements = {
        "₹": "Rs. ",
        "\u2013": "-",
        "\u2014": "-",
        "–": "-",
        "—": "-",
        "·": "|",
        "÷": "/",
        "→": "->",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.encode("ascii", "replace").decode("ascii")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_simple_pdf(path: Path, lines: Sequence[tuple[str, float, bool, bool]]) -> None:
    """Write a dependency-free, valid text PDF summary.

    Each line is ``(text, size, bold, rule)``.  This keeps the desktop build
    free of an extra PDF package while still producing a real, printable PDF.
    """

    pages: list[list[tuple[str, float, bool, bool, float]]] = []
    page: list[tuple[str, float, bool, bool, float]] = []
    y = 800.0
    margin = 46.0
    for text, size, bold, rule in lines:
        height = 10.0 if rule else max(12.0, float(size) + 4.0)
        if y - height < 48:
            pages.append(page)
            page = []
            y = 800.0
        page.append((text, float(size), bool(bold), bool(rule), y))
        y -= height
    if page:
        pages.append(page)
    if not pages:
        pages = [[("No content", 10.0, False, False, 800.0)]]

    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    # 1 catalog, 2 pages, 3/4 fonts.  Page and content objects follow.
    catalog_id = add(b"")
    pages_id = add(b"")
    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    page_ids: list[int] = []
    for page_lines in pages:
        commands: list[str] = []
        for text, size, bold, rule, line_y in page_lines:
            if rule:
                commands.append(
                    f"0.80 0.84 0.88 RG 46 {line_y:.2f} m 549 {line_y:.2f} l S"
                )
                continue
            font = "F2" if bold else "F1"
            commands.append(
                f"BT /{font} {size:.2f} Tf 46 {line_y:.2f} Td ({_pdf_safe(text)}) Tj ET"
            )
        stream = ("\n".join(commands)).encode("ascii", "replace")
        content_id = add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
        page_id = add(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        page_ids.append(page_id)
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"
    ).encode()

    buffer = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer.extend(f"{number} 0 obj\n".encode())
        buffer.extend(payload)
        buffer.extend(b"\nendobj\n")
    xref_offset = len(buffer)
    count = len(objects) + 1
    buffer.extend(f"xref\n0 {count}\n".encode())
    buffer.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode())
    buffer.extend(
        (
            f"trailer\n<< /Size {count} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(bytes(buffer))


def _write_pdf_summary(
    path: Path,
    run: ReconRun,
    counts: Mapping,
    totals: Mapping,
    checks: Sequence[Mapping],
    exceptions: Sequence[ReconException],
    generated: datetime,
) -> None:
    lines: list[tuple[str, float, bool, bool]] = []

    def line(text: str, size: float = 10, bold: bool = False, rule: bool = False):
        lines.append((text, size, bold, rule))

    line("Reconciliation Executive Summary", 18, bold=True)
    line(f"{run.client_name}  |  {run.period_label}  |  {run.workflow_label}", 10)
    line(f"Run ID {run.run_uuid}   Generated {generated.strftime('%d-%b-%Y %H:%M')}", 8.5)
    line("", 4, rule=True)
    line("Run position", 11, bold=True)
    metrics = [
        ("Records processed", int(totals.get("records_processed") or 0)),
        ("Matched records", int(totals.get("matched_records") or 0)),
        ("Unmatched records", int(totals.get("unmatched_records") or 0)),
        ("Requiring investigation", int(totals.get("proposed_records") or 0) + int(totals.get("duplicate_records") or 0)),
        ("Duplicate records", int(totals.get("duplicate_records") or 0)),
        ("Amount discrepancies", int(totals.get("amount_discrepancies") or 0)),
        ("Open exceptions", int(totals.get("open_exceptions") or 0)),
        ("Match rate", f"{float(totals.get('match_rate') or 0):.2f}%"),
        ("Unresolved exception value", f"Rs. {float(totals.get('unresolved_amount') or 0):,.2f}"),
        ("Debit total", f"Rs. {float(totals.get('debit_total') or 0):,.2f}"),
        ("Credit total", f"Rs. {float(totals.get('credit_total') or 0):,.2f}"),
        ("Completion", _status_label(run.completion_status)),
    ]
    for label, value in metrics:
        line(f"{label:<30} {value}", 9.5)
    line("", 4, rule=True)
    line("Exceptions by category", 11, bold=True)
    category_counts: dict[str, int] = {}
    for exception in exceptions:
        category_counts[exception.category] = category_counts.get(exception.category, 0) + 1
    if category_counts:
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0])):
            line(f"{_exception_label(category):<38} {count}", 9.5)
    else:
        line("No exceptions recorded.", 9.5)
    line("", 4, rule=True)
    line("Checks and tolerances", 11, bold=True)
    for check in checks:
        line(
            f"{check.get('name', 'Check')}: {_status_label(str(check.get('status') or ''))} "
            f"(difference Rs. {float(check.get('difference') or 0):,.2f})",
            9.5,
        )
        explanation = str(check.get("explanation") or "")
        if explanation:
            line(f"  {explanation[:110]}", 8.5)
    if not checks:
        line("No balance check was applicable to this workflow.", 9.5)
    line("", 4, rule=True)
    line(
        "This summary reports persisted reconciliation evidence only. It does not conclude on ITC eligibility or alter source accounting records.",
        8,
    )
    _write_simple_pdf(path, lines)
