from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import (
    guard_sheet_capacity,
    money_format,
    parse_date_value,
    plural,
)
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

# GSTR portal data is INR by definition; keep the Indian lakh/crore format.
MONEY_FORMAT = money_format([])

B2B_HEADERS = [
    "GSTIN",
    "Trade name",
    "Invoice no",
    "Date",
    "Value",
    "Taxable",
    "IGST",
    "CGST",
    "SGST",
    "Cess",
    "ITC",
    "Type",
    "Flags",
    "Source",
    "Match",
    "Books ref",
]
B2B_MONEY_COLS = (5, 6, 7, 8, 9, 10)  # Value through Cess
B2B_FLAG_COL = B2B_HEADERS.index("Flags") + 1

HSN_HEADERS = ["HSN", "Taxable", "IGST", "CGST", "SGST", "Cess", "Flags", "Source"]
HSN_MONEY_COLS = (2, 3, 4, 5, 6)
HSN_FLAG_COL = HSN_HEADERS.index("Flags") + 1

SUMMARY_HEADERS = ["Section", "Taxable", "IGST", "CGST", "SGST", "Cess", "Source"]
SUMMARY_MONEY_COLS = (2, 3, 4, 5, 6)

CANNOT_INCLUDE_HEADERS = [
    "Reason",
    "Document",
    "Date",
    "Party",
    "GSTIN",
    "Taxable",
    "IGST",
    "CGST",
    "SGST",
    "Cess",
    "Source",
]
CANNOT_INCLUDE_MONEY_COLS = (6, 7, 8, 9, 10)
CANNOT_INCLUDE_SHEET = "Cannot include"

CDN_TYPES = {"CDN", "CDNR", "CDNA", "CDNRA"}
MATCH_NOTE = "Match columns are empty until reconciliation."
MATCH_FILLED_NOTE = "Match columns filled from the master reconciliation grid."
# "utgst" is a classification, not a defect, so it never marks a row.
INFORMATIONAL_FLAGS = {"utgst"}
UTGST_NOTE = (
    "SGST column holds UTGST for intra-UT rows (supplier and place of supply in the "
    "same Union Territory without a legislature): {rows}. The portal's JSON "
    "folds UTGST into the SGST bucket, so the amount is unchanged."
)

LEGEND = (
    (
        "Shaded flag",
        "That row carries something to check; the Flags column says what.",
    ),
    (
        "utgst",
        "Not a defect: the amount is an intra-Union-Territory supply in the SGST column.",
    ),
)


def write_gstr_2b(
    path: Path,
    rows: list[dict],
    meta: dict | None = None,
    identity: dict | None = None,
) -> Path:
    identity = cover_identity(identity or {}, meta or {}, folder_identity(path))
    b2b = [row for row in rows if not _is_cdn(row)]
    cdn = [row for row in rows if _is_cdn(row)]
    flagged = [row for row in rows if _is_flagged(row)]
    book = _new_book("Cover")
    entries = [
        ("B2B", "Every purchase invoice the portal reports.", len(b2b)),
    ]
    if cdn:
        entries.append(("CDN", "Credit and debit notes, kept apart from invoices.", len(cdn)))
    entries.append(("Flags", "Only the rows that carry a flag.", len(flagged)))
    _write_cover(
        book.active,
        "GSTR-2B pack",
        rows,
        meta,
        [
            ("B2B rows", len(b2b)),
            ("CDN rows", len(cdn)),
            ("Flagged rows", len(flagged)),
            ("Total rows", len(rows)),
        ],
        note=_match_note(rows),
        entries=entries,
        path=path,
        identity=identity,
    )
    _write_b2b_sheet(book.create_sheet("B2B"), b2b, default_type="B2B", identity=identity)
    if cdn:
        _write_b2b_sheet(book.create_sheet("CDN"), cdn, default_type="CDN", identity=identity)
    _write_flags_sheet(book.create_sheet("Flags"), flagged, identity=identity)
    return _save(book, path)


def write_gstr_1(
    path: Path,
    rows: list[dict],
    meta: dict | None = None,
    identity: dict | None = None,
) -> Path:
    identity = cover_identity(identity or {}, meta or {}, folder_identity(path))
    b2b = [row for row in rows if not _is_hsn(row)]
    hsn = [row for row in rows if _is_hsn(row)]
    flagged = [row for row in rows if _is_flagged(row)]
    book = _new_book("Cover")
    counts = [
        ("B2B rows", len(b2b)),
        ("HSN rows", len(hsn)),
        ("Flagged rows", len(flagged)),
        ("Total rows", len(rows)),
    ]
    entries = [("B2B", "Every outward invoice in this return.", len(b2b))]
    if hsn:
        entries.append(("HSN", "The HSN summary lines.", len(hsn)))
    entries.append(("Flags", "Only the rows that carry a flag.", len(flagged)))
    _write_cover(book.active, "GSTR-1 pack", rows, meta, counts,
                 note=MATCH_NOTE, entries=entries, path=path, identity=identity)
    _write_b2b_sheet(book.create_sheet("B2B"), b2b, default_type="B2B", identity=identity)
    if hsn:
        _write_hsn_sheet(book.create_sheet("HSN"), hsn, identity=identity)
    _write_flags_sheet(book.create_sheet("Flags"), flagged, identity=identity)
    return _save(book, path)


def write_gstr_3b(
    path: Path,
    rows: list[dict],
    meta: dict | None = None,
    identity: dict | None = None,
) -> Path:
    identity = cover_identity(identity or {}, meta or {}, folder_identity(path))
    book = _new_book("Cover")
    _write_cover(
        book.active,
        "GSTR-3B pack",
        rows,
        meta,
        [("Summary rows", len(rows))],
        note=None,
        entries=[("Summary", "The section totals filed for this period.", len(rows))],
        path=path,
        identity=identity,
    )
    _write_summary_sheet(book.create_sheet("Summary"), rows, identity=identity)
    return _save(book, path)


def write_cannot_include(
    path: Path,
    rows: list[dict],
    meta: dict | None = None,
    identity: dict | None = None,
) -> Path:
    """The rows the GSTR upload JSON had to leave out, with the reason for each.

    The workbook opens on a cover and the rows sit on the "Cannot include"
    sheet, whose header stays on row 1 so a reader finds the columns there.
    """
    identity = cover_identity(identity or {}, meta or {}, folder_identity(path))
    book = _new_book("Contents")
    cover = book.active
    sheet = book.create_sheet(CANNOT_INCLUDE_SHEET)
    for col, header in enumerate(CANNOT_INCLUDE_HEADERS, start=1):
        put(sheet, 1, col, header)
    style_header(sheet, len(CANNOT_INCLUDE_HEADERS))
    for row in rows:
        append_row(
            sheet,
            [
                row.get("reason") or "",
                row.get("invoice_number") or "",
                _date_cell(row.get("date")),
                row.get("party") or "",
                row.get("gstin") or "",
                _money(row.get("taxable")),
                _money(row.get("igst")),
                _money(row.get("cgst")),
                _money(row.get("sgst")),
                _money(row.get("cess")),
                row.get("source") or "",
            ],
        )
        excel_row = sheet.max_row
        for col in CANNOT_INCLUDE_MONEY_COLS:
            sheet.cell(excel_row, col).number_format = MONEY_FORMAT
        mark_exception(sheet, excel_row, 1)
    if not rows:
        append_row(sheet, ["Every row could be included"])
        style_note(sheet, f"A{sheet.max_row}")
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(CANNOT_INCLUDE_HEADERS),
            right_cols=CANNOT_INCLUDE_MONEY_COLS,
            date_cols=(3,),
            wrap_cols=(1, 11),
            row_height=None,
        )
    _finish_table(
        sheet,
        len(CANNOT_INCLUDE_HEADERS),
        [52, 20, 14, 28, 18, 14, 12, 12, 12, 12, 28],
        title="Rows the upload file could not carry",
        identity=identity,
    )
    _write_cannot_include_cover(cover, rows, identity)
    return _save(book, path)


def _write_cannot_include_cover(sheet, rows: list[dict], identity: dict) -> None:
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        plural(len(rows), "row"),
        f"generated {identity['generated']}",
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Rows the upload file could not carry",
        lines=["  ·  ".join(part for part in facts if part)],
        entries=[
            (
                CANNOT_INCLUDE_SHEET,
                "Rows the GSTR upload JSON had to leave out, with the reason for each.",
                len(rows),
            )
        ],
        notes=[
            "These rows are in the pack and in the portal download; they are only "
            "missing from the JSON that would be uploaded."
        ],
        legend=LEGEND,
        width=2,
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
            "Rows the upload file could not carry",
        ],
    )


def _new_book(title: str) -> Workbook:
    book = Workbook()
    book.active.title = title[:31]
    return book


def _save(book: Workbook, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return path


def _write_cover(
    sheet,
    pack_title: str,
    rows: list[dict],
    meta: dict | None,
    counts: list[tuple[str, int]],
    note: str | None,
    entries: list[tuple[str, str, int | None]] = (),
    path: Path | None = None,
    identity: dict | None = None,
) -> None:
    identity = identity or cover_identity(
        meta or {},
        rows[0] if rows else {},
        folder_identity(path) if path else {},
    )
    gstin = _cover_gstin(rows, meta) or ""
    period = _cover_period(rows, meta) or identity.get("period") or ""
    facts = [identity.get("client") or "", period or "", f"GSTIN {gstin}" if gstin else "",
             plural(len(rows), "row"), f"generated {identity['generated']}"]
    notes = [text for text in (note, _utgst_note(rows)) if text]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title=pack_title,
        lines=["  ·  ".join(part for part in facts if part)],
        entries=entries,
        blocks=[(None, counts)],
        notes=notes,
        legend=LEGEND,
        width=2,
    )
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 30
    sheet.column_dimensions["C"].width = 10
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    cover_print_setup(
        sheet,
        2,
        footer_parts=[
            identity.get("client") or "",
            period or "",
            pack_title,
        ],
    )


def _write_b2b_sheet(
    sheet, rows: list[dict], default_type: str, identity: dict | None = None
) -> None:
    guard_sheet_capacity(rows, sheet.title)
    _write_header(sheet, B2B_HEADERS, money_cols=B2B_MONEY_COLS)
    flagged: list[int] = []
    for row in rows:
        values = _b2b_values(row, _row_type(row, default_type))
        append_row(sheet, values)
        excel_row = sheet.max_row
        for col in B2B_MONEY_COLS:
            sheet.cell(excel_row, col).number_format = MONEY_FORMAT
        if _is_flagged(row):
            flagged.append(excel_row)
    if not rows:
        append_row(sheet, ["No rows extracted"])
        style_note(sheet, f"A{sheet.max_row}")
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(B2B_HEADERS),
            right_cols=B2B_MONEY_COLS,
            date_cols=(4,),
            wrap_cols=(2, 13, 14),
            row_height=None,
        )
    for excel_row in flagged:
        mark_exception(sheet, excel_row, B2B_FLAG_COL)
    _finish_table(
        sheet,
        len(B2B_HEADERS),
        [14, 28, 20, 14, 14, 14, 12, 12, 12, 12, 12, 10, 22, 28, 14, 16],
        title=sheet.title,
        identity=identity,
    )


def _write_hsn_sheet(sheet, rows: list[dict], identity: dict | None = None) -> None:
    guard_sheet_capacity(rows, sheet.title)
    _write_header(sheet, HSN_HEADERS, money_cols=HSN_MONEY_COLS)
    flagged: list[int] = []
    for row in rows:
        append_row(
            sheet,
            [
                row.get("hsn") or row.get("invoice_number"),
                _money(row.get("taxable")),
                _money(row.get("igst")),
                _money(row.get("cgst")),
                _money(row.get("sgst")),
                _money(row.get("cess")),
                _flag_text(_flag_items(row)),
                row.get("source"),
            ],
        )
        excel_row = sheet.max_row
        for col in HSN_MONEY_COLS:
            sheet.cell(excel_row, col).number_format = MONEY_FORMAT
        if _is_flagged(row):
            flagged.append(excel_row)
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(HSN_HEADERS),
            right_cols=HSN_MONEY_COLS,
            wrap_cols=(7, 8),
            row_height=None,
        )
    for excel_row in flagged:
        mark_exception(sheet, excel_row, HSN_FLAG_COL)
    _finish_table(sheet, len(HSN_HEADERS), [14, 14, 12, 12, 12, 12, 22, 28], title=sheet.title, identity=identity)


def _write_summary_sheet(sheet, rows: list[dict], identity: dict | None = None) -> None:
    guard_sheet_capacity(rows, sheet.title)
    _write_header(sheet, SUMMARY_HEADERS, money_cols=SUMMARY_MONEY_COLS)
    for row in rows:
        append_row(
            sheet,
            [
                row.get("section"),
                _money(row.get("taxable")),
                _money(row.get("igst")),
                _money(row.get("cgst")),
                _money(row.get("sgst")),
                _money(row.get("cess")),
                row.get("source"),
            ],
        )
        excel_row = sheet.max_row
        for col in SUMMARY_MONEY_COLS:
            sheet.cell(excel_row, col).number_format = MONEY_FORMAT
    if not rows:
        append_row(sheet, ["No rows extracted"])
        style_note(sheet, f"A{sheet.max_row}")
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(SUMMARY_HEADERS),
            right_cols=SUMMARY_MONEY_COLS,
            wrap_cols=(7,),
            row_height=None,
        )
    _finish_table(sheet, len(SUMMARY_HEADERS), [44, 14, 12, 12, 12, 12, 28], title=sheet.title, identity=identity)


def _write_flags_sheet(sheet, rows: list[dict], identity: dict | None = None) -> None:
    guard_sheet_capacity(rows, sheet.title)
    _write_header(sheet, B2B_HEADERS, money_cols=B2B_MONEY_COLS)
    if not rows:
        append_row(sheet, ["none"])
        style_note(sheet, f"A{sheet.max_row}")
    else:
        for row in rows:
            append_row(sheet, _b2b_values(row, _row_type(row, "B2B")))
            excel_row = sheet.max_row
            for col in B2B_MONEY_COLS:
                sheet.cell(excel_row, col).number_format = MONEY_FORMAT
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(B2B_HEADERS),
            right_cols=B2B_MONEY_COLS,
            date_cols=(4,),
            wrap_cols=(2, 13, 14),
            row_height=None,
        )
    if rows:
        for excel_row in range(2, sheet.max_row + 1):
            mark_exception(sheet, excel_row, B2B_FLAG_COL)
    _finish_table(
        sheet,
        len(B2B_HEADERS),
        [14, 28, 20, 14, 14, 14, 12, 12, 12, 12, 12, 10, 22, 28, 14, 16],
        title=sheet.title,
        identity=identity,
    )


def _match_note(rows: list[dict]) -> str:
    for row in rows:
        if str(row.get("match_status") or "").strip():
            return MATCH_FILLED_NOTE
    return MATCH_NOTE


def _write_header(sheet, headers: list[str], money_cols: tuple[int, ...] = ()) -> None:
    for col, header in enumerate(headers, start=1):
        put(sheet, 1, col, header)
    style_header(sheet, len(headers), 1, money_cols=money_cols)


def _finish_table(
    sheet,
    ncols: int,
    widths: list[int],
    title: str = "",
    identity: dict | None = None,
) -> None:
    last_col = get_column_letter(max(ncols, 1))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    set_widths(sheet, widths)
    who = identity or {}
    print_setup(
        sheet,
        ncols,
        header_row=1,
        footer_parts=[
            who.get("client") or "",
            who.get("period") or "",
            title or sheet.title,
        ],
    )


def _b2b_values(row: dict, doc_type: str) -> list:
    return [
        row.get("gstin"),
        row.get("trade_name"),
        row.get("invoice_number"),
        _date_cell(row.get("invoice_date_iso") or row.get("invoice_date")),
        _money(row.get("invoice_value")),
        _money(row.get("taxable")),
        _money(row.get("igst")),
        _money(row.get("cgst")),
        _money(row.get("sgst")),
        _money(row.get("cess")),
        row.get("itc_availability") if row.get("itc_availability") is not None else row.get("itc"),
        doc_type,
        _flag_text(_flag_items(row)),
        row.get("source"),
        row.get("match_status") or None,
        row.get("books_ref") or None,
    ]


def _cover_gstin(rows: list[dict], meta: dict | None) -> str | None:
    if meta:
        for key in ("gstin", "filer_gstin"):
            if meta.get(key):
                return meta[key]
    for row in rows:
        for key in ("filer_gstin", "recipient_gstin"):
            if row.get(key):
                return row[key]
    return None


def _cover_period(rows: list[dict], meta: dict | None) -> str | None:
    if meta:
        for key in ("period", "rtnprd", "fp", "ret_period"):
            if meta.get(key):
                return meta[key]
    for row in rows:
        for key in ("period", "rtnprd", "fp", "ret_period"):
            if row.get(key):
                return row[key]
    return None


def _cover_source(rows: list[dict]) -> str | None:
    if not rows:
        return None
    source = str(rows[0].get("source") or "")
    return source.split("#", 1)[0] or None


def _row_type(row: dict, default: str) -> str:
    raw = row.get("document_type")
    if raw is None or str(raw).strip() == "":
        if _looks_hsn(row):
            return "HSN"
        return default
    return str(raw).strip()


def _is_hsn(row: dict) -> bool:
    return _row_type(row, "B2B").upper() == "HSN" or _looks_hsn(row)


def _looks_hsn(row: dict) -> bool:
    source = str(row.get("source") or "")
    if "#hsn" in source.lower():
        return True
    if str(row.get("trade_name") or "").strip().lower() == "hsn summary":
        return True
    return str(row.get("document_type") or "").strip().upper() == "HSN"


def _is_cdn(row: dict) -> bool:
    return str(row.get("document_type") or "").strip().upper() in CDN_TYPES


def _is_flagged(row: dict) -> bool:
    return any(item.lower() not in INFORMATIONAL_FLAGS for item in _flag_items(row))


def _flag_items(row: dict) -> list[str]:
    flags = row.get("flags")
    if flags is None or flags == "":
        items: list[str] = []
    elif isinstance(flags, str):
        items = [part.strip() for part in flags.split(",") if part.strip()]
    else:
        items = [str(item).strip() for item in flags if str(item).strip()]
    if row.get("intra_ut") and not any(item.lower() == "utgst" for item in items):
        items = items + ["utgst"]
    return items


def _utgst_note(rows: list[dict]) -> str | None:
    count = sum(1 for row in rows if row.get("intra_ut"))
    return UTGST_NOTE.format(rows=plural(count, "row")) if count else None


def _flag_text(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value if item)


def _date_cell(value):
    """A real date when the text is unambiguous, otherwise the text as received."""
    if value is None or value == "":
        return value
    parsed = parse_date_value(value)
    return parsed if parsed is not None else value


def _money(value):
    if value is None or value == "":
        return None
    return float(value)
