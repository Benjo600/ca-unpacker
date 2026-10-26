from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.style import (
    GREEN_FILL,
    RED_FILL,
    fill_row,
    print_setup,
    set_widths,
    style_body,
    style_header,
    style_note,
    style_title,
)

HEADERS = [
    "Date",
    "Description",
    "Cheque / Ref",
    "Debit",
    "Credit",
    "Balance",
    "Source",
    "Flags",
]

COVER_HEADERS = [
    "File",
    "Bank",
    "Sheet",
    "Account no",
    "IFSC",
    "Rows",
    "Opening",
    "Stated close",
    "Computed close",
    "Result",
    "Broken at",
    "Flags",
]

MONEY_INFERRED_FORMAT = '#,##0.00" (inferred)"'


def write_bank_pack(path: Path, rows: list[dict], check: dict, meta: dict) -> Path:
    return write_bank_workbook(
        path,
        [
            {
                "rows": rows,
                "check": check,
                "meta": meta,
            }
        ],
    )


def write_bank_workbook(path: Path, files: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    cover = book.active
    cover.title = "Balance Check"

    used: set[str] = {"Balance Check"}
    names: list[str] = []
    if len(files) == 1:
        names.append("Transactions")
        used.add("Transactions")
    else:
        for item in files:
            title = _sheet_name(item["meta"].get("filename") or "Transactions", used)
            used.add(title)
            names.append(title)

    _cover_multi(cover, files, names)

    for item, title in zip(files, names):
        sheet = book.create_sheet(title)
        _write_rows(sheet, item["rows"])

    book.save(path)
    return path


def _write_rows(sheet, rows: list[dict]) -> None:
    sheet.append(HEADERS)
    style_header(sheet, len(HEADERS))
    flagged: list[int] = []
    for row in rows:
        flags = _flag_text(row.get("flags") if row.get("flags") is not None else row.get("validation_flags"))
        sheet.append(
            [
                _as_date(row.get("date")),
                row.get("description"),
                row.get("cheque_ref"),
                _money(row.get("debit")),
                _money(row.get("credit")),
                _money(row.get("balance")),
                row.get("source"),
                flags,
            ]
        )
        tokens = _flag_tokens(flags)
        if "balance_mismatch" in tokens or "running_balance_break" in tokens:
            flagged.append(sheet.max_row)
    style_body(sheet, 2, max(sheet.max_row, 1), len(HEADERS), money_cols=(4, 5, 6), date_cols=(1,))
    for excel_row in flagged:
        fill_row(sheet, excel_row, len(HEADERS), RED_FILL)
    last_col = get_column_letter(len(HEADERS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    set_widths(sheet, [14, 48, 16, 14, 14, 14, 36, 28])
    print_setup(sheet, len(HEADERS), header_row=1)


def _sheet_name(filename: str, used: set[str]) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[\[\]\*\?:/\\]", " ", stem)[:28].strip() or "Transactions"
    name = cleaned
    n = 2
    while name in used:
        name = f"{cleaned[:26]}_{n}"
        n += 1
    return name


def _cover_multi(sheet, files: list[dict], names: list[str]) -> None:
    sheet["A1"] = "Bank statement pack"
    style_title(sheet, "A1")
    sheet["A2"] = "Each source file is checked on its own. Do not mix two statements when you test."
    style_note(sheet, "A2")
    sheet.append([])
    sheet.append(COVER_HEADERS)
    style_header(sheet, len(COVER_HEADERS), row=4)
    inferred_rows: list[int] = []
    status_rows: list[tuple[int, object]] = []
    for item, title in zip(files, names):
        check = item["check"]
        meta = item["meta"]
        inferred = bool(check.get("opening_inferred"))
        status = str(check.get("status") or "")
        if status == "match":
            label = "MATCH"
            fill = GREEN_FILL
        elif status == "unverified":
            label = "COULD NOT VERIFY"
            fill = None
        else:
            label = "MISMATCH"
            fill = RED_FILL
        sheet.append(
            [
                meta.get("filename"),
                meta.get("profile_label"),
                title,
                meta.get("account_number"),
                meta.get("ifsc"),
                check.get("row_count"),
                check.get("opening_balance"),
                check.get("stated_closing"),
                check.get("computed_closing"),
                label,
                check.get("broken_at_row"),
                _flag_text(check.get("flags")),
            ]
        )
        excel_row = sheet.max_row
        if inferred:
            inferred_rows.append(excel_row)
        if fill is not None:
            status_rows.append((excel_row, fill))
    if any(item["check"].get("opening_inferred") for item in files):
        sheet.cell(4, 7).value = "Opening (inferred)"
    style_body(sheet, 5, max(sheet.max_row, 1), len(COVER_HEADERS), money_cols=(7, 8, 9))
    for excel_row in inferred_rows:
        sheet.cell(excel_row, 7).number_format = MONEY_INFERRED_FORMAT
    for excel_row, fill in status_rows:
        fill_row(sheet, excel_row, len(COVER_HEADERS), fill)
    set_widths(sheet, [36, 22, 18, 18, 14, 10, 18, 16, 16, 12, 12, 28])
    print_setup(sheet, len(COVER_HEADERS), header_row=4)


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return value


def _money(value):
    if value is None or value == "":
        return None
    return float(value)


def _flag_text(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value if item)


def _flag_tokens(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(item) for item in value if item]
