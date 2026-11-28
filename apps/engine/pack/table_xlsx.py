from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import (
    DATE_KEYS,
    guard_sheet_capacity,
    money_format,
    parse_date_value,
    plural,
)
from apps.engine.pack.style import (
    DATE_FORMAT,
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

MONEY_FORMAT = "#,##0.00"
MONEY_KEYS = {
    "taxable",
    "tax",
    "invoice_value",
    "taxable_value",
    "amount",
    "rate",
    "gross",
    "discount",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "debit",
    "credit",
    "balance",
    "opening_balance",
    "closing_balance",
    "aging_current",
    "aging_1_30",
    "aging_31_60",
    "aging_61_90",
    "aging_91_120",
    "aging_over_120",
}
# Defect markers only. Informational flags such as "utgst" (an intra-UT supply
# whose SGST column really holds UTGST) must never mark a row.
FLAG_MARKERS = (
    "gstin_checksum",
    "hsn_length",
    "invoice_math",
    "item_layout_uncertain",
    "unparsed_rows",
    "invoice_number_missing",
    "date_missing",
    "date_unlabelled",
    "currency_unknown",
    "taxable_derived",
    "tax_derived",
    "invoice_value_derived",
    "sap_",
)
LONG_TEXT_KEYS = {
    "description",
    "trade_name",
    "party_name",
    "supplier_name",
    "raw_excerpt",
    "narration",
    "particulars",
}

# One plain sentence per register, used on its cover index.
SHEET_BLURBS = {
    "Purchase register": "One row per purchase bill, as read from the documents.",
    "Sales register": "One row per sales bill, as read from the books.",
    "Books": "The book entries as read from the accounting export.",
    "Needs review": "Files the reader could not place, with the reason for each.",
    "SAP reports": "Rows taken from the SAP reports in this dump.",
    "Invoices": "One row per purchase invoice, with its totals.",
    "Line items": "The item lines behind each invoice.",
}
DEFAULT_BLURB = "The extracted rows for this period."

LEGEND = (
    (
        "Shaded flag",
        "That row carries something to check; the Flags column says what.",
    ),
)


def write_table(
    path: Path,
    sheet_name: str,
    rows: list[dict],
    columns: list[tuple[str, str]],
    identity: dict | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    cover = book.active
    cover.title = "Contents"
    data_sheet = book.create_sheet(sheet_name[:31])
    _fill_sheet(data_sheet, sheet_name, rows, columns)
    _cover(
        cover,
        title=sheet_name,
        entries=[(data_sheet.title, SHEET_BLURBS.get(sheet_name, DEFAULT_BLURB), len(rows))],
        columns=len(columns),
        row_count=len(rows),
        identity=cover_identity(identity or {}, folder_identity(path)),
        path=path,
        sheet_name=sheet_name,
    )
    book.save(path)
    return path


def write_purchase_workbook(
    path: Path,
    invoices: list[dict],
    line_items: list[dict],
    invoice_cols: list[tuple[str, str]],
    line_cols: list[tuple[str, str]],
    identity: dict | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    cover = book.active
    cover.title = "Contents"
    invoices_sheet = book.create_sheet("Invoices")
    _fill_sheet(invoices_sheet, "Invoices", invoices, invoice_cols)
    items_sheet = book.create_sheet("Line items")
    _fill_sheet(items_sheet, "Line items", line_items, line_cols)
    _cover(
        cover,
        title="Purchase register",
        entries=[
            ("Invoices", SHEET_BLURBS["Invoices"], len(invoices)),
            ("Line items", SHEET_BLURBS["Line items"], len(line_items)),
        ],
        columns=max(len(invoice_cols), len(line_cols)),
        row_count=len(invoices) + len(line_items),
        identity=cover_identity(identity or {}, folder_identity(path)),
        path=path,
        sheet_name="Purchase register",
    )
    book.save(path)
    return path


def _cover(
    sheet,
    *,
    title: str,
    entries: list[tuple[str, str, int | None]],
    columns: int,
    row_count: int,
    identity: dict,
    path: Path,
    sheet_name: str,
) -> None:
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        plural(row_count, "row"),
        plural(columns, "column"),
        f"generated {identity['generated']}",
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title=title,
        lines=["  ·  ".join(part for part in facts if part)],
        entries=entries,
        blocks=[],
        notes=[],
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
        footer_parts=[identity.get("client") or "", identity.get("period") or "", sheet_name],
    )


def _fill_sheet(sheet, sheet_name: str, rows: list[dict], columns: list[tuple[str, str]]) -> None:
    guard_sheet_capacity(rows, sheet_name)
    sheet.title = sheet_name[:31]
    for col, (title, _key) in enumerate(columns, start=1):
        put(sheet, 1, col, title)
    money_cols = tuple(
        index for index, (_title, key) in enumerate(columns, start=1) if key in MONEY_KEYS
    )
    date_cols = tuple(
        index for index, (_title, key) in enumerate(columns, start=1) if key in DATE_KEYS
    )
    style_header(sheet, len(columns), 1, money_cols=money_cols)
    format_string = money_format(rows)
    flag_col = next(
        (index for index, (title, key) in enumerate(columns, start=1) if key == "flags" or title == "Flags"),
        None,
    )
    flagged: list[int] = []
    for row in rows:
        values = []
        for index, (_title, key) in enumerate(columns, start=1):
            value = _cell(row.get(key))
            if index in date_cols:
                value = _date_cell(value)
            values.append(value)
        append_row(sheet, values)
        excel_row = sheet.max_row
        for index in money_cols:
            sheet.cell(excel_row, index).number_format = format_string
        if flag_col is not None:
            flag_text = str(sheet.cell(excel_row, flag_col).value or "")
            if any(marker in flag_text for marker in FLAG_MARKERS):
                flagged.append(excel_row)
    if not rows:
        append_row(sheet, ["No rows extracted"])
        style_note(sheet, f"A{sheet.max_row}")
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(columns),
            right_cols=money_cols,
            date_cols=date_cols,
            wrap_cols=tuple(
                index for index, (_title, key) in enumerate(columns, start=1)
                if key in LONG_TEXT_KEYS or key == "flags" or key == "source"
            ),
            row_height=None,
        )
    if flag_col is not None:
        for excel_row in flagged:
            mark_exception(sheet, excel_row, flag_col)
    widths = []
    for _title, key in columns:
        width = 16
        if key in LONG_TEXT_KEYS:
            width = 40
        if key == "source":
            width = 28
        widths.append(width)
    set_widths(sheet, widths)
    last_col = get_column_letter(max(len(columns), 1))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    print_setup(sheet, len(columns), header_row=1, footer_parts=[sheet.title])


def _cell(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return value


def _date_cell(value):
    """A real date when the text is unambiguous, otherwise the text as received."""
    if value is None or value == "":
        return value
    parsed = parse_date_value(value)
    return parsed if parsed is not None else value
