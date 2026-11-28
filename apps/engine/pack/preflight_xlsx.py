"""The Preflight_Report workbook: a cover, then one row per finding.

Same look as every other pack - the header band, hairline body rules and the
type scale all come from ``pack.style``.  A blocking finding carries the
exception mark on its level cell, so it cannot be mistaken for a warning at a
glance without the row being painted out.

The cover is sheet 1 and the findings are sheet 2 ("Preflight"); the findings
header stays on row 1 of its own sheet, so readers that look the sheet up by
name keep working.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import plural
from apps.engine.pack.style import (
    append_row,
    cover_identity,
    cover_print_setup,
    cover_sheet,
    folder_identity,
    mark_exception,
    print_setup,
    put,
    set_widths,
    style_body,
    style_header,
    style_note,
)

PREFLIGHT_HEADERS = ["Level", "Code", "What is wrong", "Count", "Where to look"]
PREFLIGHT_WIDTHS = [12, 22, 62, 8, 54]
LEVEL_LABELS = {"blocking": "BLOCKING", "warning": "WARNING"}
DATA_SHEET = "Preflight"

LEGEND = (
    (
        "Shaded level",
        "BLOCKING means the pack was not written; WARNING means it was, but look first.",
    ),
)


def write_preflight_report(path: Path, report, identity: dict | None = None) -> Path:
    """Write *report* (a ``PreflightReport``) to *path* and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    cover = book.active
    cover.title = "Contents"
    sheet = book.create_sheet(DATA_SHEET)
    for col, header in enumerate(PREFLIGHT_HEADERS, start=1):
        put(sheet, 1, col, header)
    style_header(sheet, len(PREFLIGHT_HEADERS))

    blocking_rows: list[int] = []
    for issue in report.issues:
        samples = "; ".join(sample.text() for sample in issue.samples)
        append_row(
            sheet,
            [
                LEVEL_LABELS.get(issue.level, issue.level.upper()),
                issue.code,
                issue.message,
                issue.count,
                samples,
            ],
        )
        if issue.level == "blocking":
            blocking_rows.append(sheet.max_row)

    if not report.issues:
        append_row(sheet, ["", "", "Pre-flight found nothing to report.", 0, ""])
        style_note(sheet, f"A{sheet.max_row}")

    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(PREFLIGHT_HEADERS),
            right_cols=(4,),
            wrap_cols=(3, 5),
            row_height=None,
        )
    for excel_row in blocking_rows:
        mark_exception(sheet, excel_row, 1)

    last_col = get_column_letter(len(PREFLIGHT_HEADERS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    set_widths(sheet, PREFLIGHT_WIDTHS)
    _stamp = _report_stamp(report)
    who = cover_identity(identity or {}, folder_identity(path))
    print_setup(
        sheet,
        len(PREFLIGHT_HEADERS),
        header_row=1,
        landscape=False,
        footer_parts=[who.get("client") or "", who.get("period") or "", "Pre-flight report"],
    )
    _write_cover(cover, report, who, path, _stamp)
    book.save(path)
    return path


def _write_cover(sheet, report, identity: dict, path: Path, stamp: str) -> None:
    issues = list(getattr(report, "issues", ()) or ())
    blocking = sum(1 for issue in issues if getattr(issue, "level", "") == "blocking")
    warnings = sum(1 for issue in issues if getattr(issue, "level", "") == "warning")
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        plural(len(issues), "finding"),
        f"{blocking} blocking",
        f"{warnings} warning" + ("" if warnings == 1 else "s"),
        f"generated {stamp or identity['generated']}",
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Pre-flight report",
        lines=["  ·  ".join(part for part in facts if part)],
        entries=[(DATA_SHEET, "Everything the gate found before the pack was written.", len(issues))],
        notes=[
            "A blocking finding stops the pack: no workbook is written for that run."
        ],
        legend=LEGEND,
        width=3,
    )
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["B"].width = 78
    sheet.column_dimensions["C"].width = 8
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    cover_print_setup(
        sheet,
        3,
        footer_parts=[
            identity.get("client") or "",
            identity.get("period") or "",
            "Pre-flight report",
        ],
    )


def _report_stamp(report) -> str:
    """The report's own timestamp in DD-MM-YYYY HH:MM, when it has one."""
    raw = getattr(report, "generated_at", "")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    try:
        return datetime.fromisoformat(raw).strftime("%d-%m-%Y %H:%M")
    except ValueError:
        return ""
