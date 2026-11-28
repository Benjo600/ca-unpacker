"""Workbook writer for the per-client treatment review."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import plural
from apps.engine.pack.style import (
    LABEL_FONT,
    MONEY_FORMAT,
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
HEAD_COLS = (
    ("Suggested head", "head"),
    ("Lines matched", "count"),
    ("Amount", "amount"),
    ("Matched words", "keywords_text"),
    ("Sample", "sample_text"),
)

LEGEND = (
    (
        "Shaded severity",
        "That finding needs your eye; the next columns say why it was raised.",
    ),
    (
        "Working limit",
        "The threshold the finding was measured against, with the rule behind it.",
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
    if observed.get("count") is not None:
        parts.append(plural(observed["count"], "line"))
    for key, label in (("total", "total"), ("largest", "largest single"), ("turnover", "turnover")):
        if observed.get(key) is not None:
            parts.append(f"{label} ₹{_money(observed[key])}")
    if observed.get("sales_lines") is not None and observed.get("count") is None:
        parts.append(plural(observed["sales_lines"], "sales line"))
    return " · ".join(parts)


def _threshold_text(threshold: Mapping | None) -> str:
    if not threshold:
        return ""
    amount = threshold.get("amount")
    if amount is None:
        return str(threshold.get("basis") or "")
    text = f"₹{_money(amount)}"
    if threshold.get("enhanced"):
        text += f" (enhanced ₹{_money(threshold['enhanced'])})"
    if threshold.get("basis"):
        text += f" {threshold['basis']}"
    if threshold.get("rate"):
        text += f" · rate {threshold['rate']}"
    if threshold.get("as_of"):
        text += f" · {threshold['as_of']}"
    return text.strip()


def _footer(identity: dict, sheet_name: str) -> list[str]:
    return [
        identity.get("client") or "",
        identity.get("period") or "",
        f"Treatment review — {sheet_name}",
    ]


def _write_cover(sheet, treatment: Mapping, identity: dict) -> None:
    flags = treatment.get("flags") or []
    heads = treatment.get("expense_heads") or []
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        f"generated {identity['generated']}",
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Treatment review",
        lines=["  ·  ".join(part for part in facts if part)],
        entries=[
            ("Treatment notes", "Where a head of income or expense needs a decision.", len(flags)),
            ("Expense heads", "What the line items look like once grouped.", len(heads)),
            ("Profile", "The client profile the notes were measured against.", None),
        ],
        notes=[
            "This sheet is a working note for the firm. Nothing here has been filed."
        ],
        legend=LEGEND,
        width=2,
    )
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 18
    sheet.column_dimensions["C"].width = 8
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    cover_print_setup(sheet, 2, footer_parts=_footer(identity, "Cover"))


def _write_flags(sheet, flags: Sequence[Mapping], identity: dict) -> None:
    sheet.title = "Treatment notes"
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
        append_row(sheet, ["", "", "No treatment flags for this period."])
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

    set_widths(sheet, (11, 18, 34, 60, 32, 26, 30, 34, 42))
    sheet.freeze_panes = "A2"
    last_col = get_column_letter(len(FLAG_COLS))
    sheet.auto_filter.ref = f"A1:{last_col}{max(sheet.max_row, 1)}"
    print_setup(
        sheet,
        len(FLAG_COLS),
        header_row=1,
        footer_parts=_footer(identity, "Treatment notes"),
    )


def _write_heads(sheet, heads: Sequence[Mapping], unmapped: Mapping | None, identity: dict) -> None:
    sheet.title = "Expense heads"
    for col, (title, _key) in enumerate(HEAD_COLS, start=1):
        put(sheet, 1, col, title)
    style_header(sheet, len(HEAD_COLS), 1, money_cols=(3,))

    for head in heads:
        samples = head.get("samples") or []
        sample_text = " | ".join(
            f"{item.get('date') or ''} {item.get('party') or ''} {item.get('narration') or ''}".strip()
            for item in samples[:3]
        )
        append_row(
            sheet,
            [
                head.get("head") or "",
                head.get("count") or 0,
                head.get("amount"),
                ", ".join(head.get("keywords") or []),
                sample_text,
            ],
        )
        sheet.cell(sheet.max_row, 3).number_format = MONEY_FORMAT

    if unmapped and unmapped.get("count"):
        append_row(
            sheet,
            [
                "Not matched to a suggested head",
                unmapped.get("count"),
                unmapped.get("amount"),
                "",
                " | ".join(
                    f"{item.get('date') or ''} {item.get('party') or ''} {item.get('narration') or ''}".strip()
                    for item in (unmapped.get("samples") or [])[:3]
                ),
            ],
        )
        sheet.cell(sheet.max_row, 3).number_format = MONEY_FORMAT

    if sheet.max_row == 1:
        append_row(sheet, ["No line items were available for head mapping."])
        style_note(sheet, f"A{sheet.max_row}")

    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(HEAD_COLS),
            right_cols=(2,),
            wrap_cols=(1, 4, 5),
            row_height=None,
        )

    set_widths(sheet, (34, 13, 16, 30, 70))
    sheet.freeze_panes = "A2"
    last_col = get_column_letter(len(HEAD_COLS))
    sheet.auto_filter.ref = f"A1:{last_col}{max(sheet.max_row, 1)}"
    print_setup(
        sheet,
        len(HEAD_COLS),
        header_row=1,
        footer_parts=_footer(identity, "Expense heads"),
    )


def _write_profile(sheet, treatment: Mapping, identity: dict) -> None:
    sheet.title = "Profile"
    profile = treatment.get("profile") or {}
    rows = [
        ("Client profile", profile.get("summary") or "Not set"),
        ("Profession", profile.get("profession_label") or ""),
        ("Profession group", profile.get("profession_group") or ""),
        ("Entity type", profile.get("entity_type_label") or ""),
        (
            "GST registration",
            "Registered"
            if profile.get("gst_registered") is True
            else "Not registered"
            if profile.get("gst_registered") is False
            else "Not set",
        ),
        ("GSTIN", profile.get("gstin") or ""),
        ("Typical GST rate", profile.get("gst_rate") or ""),
        ("GST note", profile.get("gst_note") or ""),
        ("Watch for", profile.get("watch") or ""),
        ("Rules as of", treatment.get("as_of") or ""),
        ("How to read this sheet", treatment.get("disclaimer") or ""),
    ]
    details = profile.get("details") or {}
    for key in ("books", "banks", "broker", "notes"):
        value = details.get(key)
        if value:
            rows.append((key.capitalize(), ", ".join(value) if isinstance(value, list) else value))

    put(sheet, 1, 1, "Field")
    put(sheet, 1, 2, "Value")
    style_header(sheet, 2)
    for label, value in rows:
        append_row(sheet, [label, value])
    if sheet.max_row > 1:
        style_body(sheet, 2, sheet.max_row, 2, wrap_cols=(2,), row_height=None)
        for row in range(2, sheet.max_row + 1):
            sheet.cell(row, 1).font = LABEL_FONT
    set_widths(sheet, (26, 100))
    sheet.freeze_panes = "A2"
    print_setup(sheet, 2, header_row=1, footer_parts=_footer(identity, "Profile"))


def write_treatment_workbook(
    path: Path, treatment: Mapping, identity: dict | None = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    identity = cover_identity(
        identity or {}, treatment or {}, treatment.get("profile") or {}, folder_identity(path)
    )
    cover = book.active
    cover.title = "Cover"
    _write_cover(cover, treatment, identity)
    _write_flags(book.create_sheet("Treatment notes"), treatment.get("flags") or [], identity)
    _write_heads(
        book.create_sheet("Expense heads"),
        treatment.get("expense_heads") or [],
        treatment.get("unmapped"),
        identity,
    )
    _write_profile(book.create_sheet("Profile"), treatment, identity)
    book.save(path)
    return path
