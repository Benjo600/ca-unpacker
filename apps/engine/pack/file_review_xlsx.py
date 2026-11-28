"""Workbook writer for the per-client file review sheet."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

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

CHECKLIST_COLS = (
    ("Grade", "grade_text"),
    ("Document", "label"),
    ("Status", "status_text"),
    ("Evidence", "evidence"),
    ("Why it matters", "why"),
    ("What to do", "action"),
)

# The cross-checks sheet shares the treatment flag columns on purpose, so both
# sheets read the same way.
FLAG_COLS = (
    ("Severity", "severity"),
    ("Area", "area"),
    ("Finding", "title"),
    ("What was seen", "detail"),
    ("Why it was raised", "basis"),
    ("Amounts", "observed_text"),
    ("Working limit", "threshold_text"),
    ("Law or rule", "law_ref"),
    ("What the CA should do", "action"),
)

STATUS_TEXT = {
    "missing": "Not in the pack",
    "attached": "Attached, not read",
    "verified": "Read this period",
}

_GRADE_TEXT = {"essential": "Essential", "recommended": "Recommended"}

LEGEND = (
    (
        "Shaded status",
        "That document or check needs your eye; the next column says why.",
    ),
    (
        "Grade",
        "Essential documents are required for this client; the rest are worth having.",
    ),
)


def _money(value) -> str:
    if value is None:
        return ""
    return f"{float(value):,.2f}"


def _observed_text(observed: Mapping | None) -> str:
    if not observed:
        return ""
    parts: list[str] = []
    label_map = (
        ("count", "line"),
        ("total", "total"),
        ("difference", "difference"),
        ("purchase_total", "purchases"),
        ("portal_total", "portal"),
        ("books_total", "books"),
        ("bank_credits", "bank credits"),
        ("sales_total", "sales"),
        ("missing_days", "missing days"),
    )
    for key, label in label_map:
        value = observed.get(key)
        if value is None:
            continue
        if isinstance(value, float) or isinstance(value, int):
            if key in {"count", "missing_days", "gstin_count", "name_count"}:
                parts.append(plural(value, label))
            else:
                parts.append(f"{label} ₹{_money(value)}")
        else:
            parts.append(f"{label} {value}")
    extra_keys = [
        key
        for key in observed
        if key not in {k for k, _l in label_map} and observed.get(key) is not None
    ]
    for key in sorted(extra_keys)[:4]:
        parts.append(f"{key.replace('_', ' ')}: {observed[key]}")
    return " · ".join(parts)


def _threshold_text(threshold: Mapping | None) -> str:
    if not threshold:
        return ""
    parts = []
    amount = threshold.get("amount")
    if amount is not None:
        parts.append(f"₹{_money(amount)}")
    for key in ("enhanced", "tolerance", "basis", "rate", "gap_days", "as_of"):
        if threshold.get(key) is not None and key != "amount":
            parts.append(str(threshold[key]))
    return " · ".join(parts)


def _write_checklist(sheet, checklist: Sequence[Mapping], identity: dict) -> None:
    sheet.title = "Checklist"
    for col, (title, _key) in enumerate(CHECKLIST_COLS, start=1):
        put(sheet, 1, col, title)
    style_header(sheet, len(CHECKLIST_COLS), 1)
    flagged: list[int] = []

    for item in checklist:
        row = dict(item)
        row["grade_text"] = _GRADE_TEXT.get(str(row.get("grade")), str(row.get("grade")))
        row["status_text"] = STATUS_TEXT.get(str(row.get("status")), str(row.get("status")))
        if row.get("escalated"):
            row["grade_text"] += " (upgraded)"
        append_row(sheet, [row.get(key) or "" for _title, key in CHECKLIST_COLS])
        if str(item.get("status")) in {"missing", "attached"}:
            flagged.append(sheet.max_row)

    if not checklist:
        append_row(sheet, ["", "", "No checklist items for this profile."])
        style_note(sheet, f"A{sheet.max_row}")

    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(CHECKLIST_COLS),
            wrap_cols=(2, 4, 5, 6),
            row_height=None,
        )
    for excel_row in flagged:
        mark_exception(sheet, excel_row, 3)

    set_widths(sheet, (14, 34, 18, 52, 52, 48))
    sheet.freeze_panes = "A2"
    last_col = get_column_letter(len(CHECKLIST_COLS))
    sheet.auto_filter.ref = f"A1:{last_col}{max(sheet.max_row, 1)}"
    print_setup(
        sheet,
        len(CHECKLIST_COLS),
        header_row=1,
        footer_parts=_footer(identity, "Checklist"),
    )


def _write_checks(sheet, flags: Sequence[Mapping], identity: dict) -> None:
    sheet.title = "Cross-checks"
    for col, (title, _key) in enumerate(FLAG_COLS, start=1):
        put(sheet, 1, col, title)
    style_header(sheet, len(FLAG_COLS), 1)
    flagged: list[int] = []

    for flag in flags:
        row = dict(flag)
        row["observed_text"] = _observed_text(flag.get("observed"))
        row["threshold_text"] = _threshold_text(flag.get("threshold"))
        append_row(sheet, [row.get(key) or "" for _title, key in FLAG_COLS])
        if str(flag.get("severity")) in {"review", "check"}:
            flagged.append(sheet.max_row)

    if not flags:
        append_row(sheet, ["", "", "No cross-document problems found this period."])
        style_note(sheet, f"A{sheet.max_row}")

    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(FLAG_COLS),
            wrap_cols=(2, 3, 4, 5, 6, 7, 8, 9),
            row_height=None,
        )
    for excel_row in flagged:
        mark_exception(sheet, excel_row, 1)

    set_widths(sheet, (11, 22, 34, 60, 32, 26, 30, 40, 42))
    sheet.freeze_panes = "A2"
    last_col = get_column_letter(len(FLAG_COLS))
    sheet.auto_filter.ref = f"A1:{last_col}{max(sheet.max_row, 1)}"
    print_setup(
        sheet,
        len(FLAG_COLS),
        header_row=1,
        footer_parts=_footer(identity, "Cross-checks"),
    )


def _footer(identity: dict, sheet_name: str) -> list[str]:
    return [
        identity.get("client") or "",
        identity.get("period") or "",
        f"File review — {sheet_name}",
    ]


def _write_summary(sheet, review: Mapping, identity: dict) -> None:
    """The summary is this workbook's cover: what the file holds, and the index."""
    sheet.title = "Contents"
    readiness_text = {
        "ready": "Ready — the expected documents are in and the cross-checks came back clean.",
        "check": "Needs checking — some documents are attached but unread, or a cross-check needs an eye.",
        "gaps": "Gaps — something the file should contain is missing, or a cross-check needs work.",
    }.get(str(review.get("readiness")), str(review.get("readiness")))
    counts = review.get("counts") or {}
    profile = review.get("profile") or {}
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        f"generated {identity['generated']}",
    ]
    checklist = review.get("checklist") or []
    checks = review.get("checks") or []
    rows = [
        ("Readiness", readiness_text),
        ("Client profile", profile.get("summary") or ""),
        (
            "Missing essentials",
            counts.get("essential_missing", 0),
        ),
        ("Missing nice-to-haves", counts.get("recommended_missing", 0)),
        ("Attached but unread", counts.get("attached_not_read", 0)),
        ("Documents read this period", counts.get("verified", 0)),
        ("Cross-checks to review", counts.get("review", 0)),
        ("Cross-checks to verify", counts.get("check", 0)),
        ("Cross-check notes", counts.get("info", 0)),
        ("Rules as of", review.get("as_of") or ""),
        ("How to read this sheet", review.get("disclaimer") or ""),
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="File review",
        lines=["  ·  ".join(part for part in facts if part)],
        entries=[
            ("Checklist", "Every document this client's file should hold.", len(checklist)),
            ("Cross-checks", "Where two documents disagree with each other.", len(checks)),
        ],
        blocks=[("Where this file stands", rows)],
        notes=[],
        legend=LEGEND,
        width=2,
    )
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 100
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    cover_print_setup(sheet, 2, footer_parts=_footer(identity, "Contents"))


def write_file_review_workbook(
    path: Path, review: Mapping, identity: dict | None = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    identity = cover_identity(
        identity or {}, review or {}, review.get("profile") or {}, folder_identity(path)
    )
    _write_summary(book.active, review, identity)
    _write_checklist(book.create_sheet("Checklist"), review.get("checklist") or [], identity)
    _write_checks(book.create_sheet("Cross-checks"), review.get("checks") or [], identity)
    book.save(path)
    return path
