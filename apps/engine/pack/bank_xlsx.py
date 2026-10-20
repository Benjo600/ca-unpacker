from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.engine.currency import (
    currency_label,
    excel_neutral_number_format,
    excel_number_format,
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
    "Currency",
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
    "Currency",
]

MONEY_FORMAT = "#,##0.00"
MONEY_INFERRED_FORMAT = '#,##0.00" (inferred)"'
DATE_FORMAT = "DD-MM-YYYY"

# Excel's hard worksheet limit.  A bank statement is never truncated: the
# writer raises a clear error instead.
MAX_BANK_SHEET_ROWS = 1_048_575

RED_FILL = PatternFill("solid", fgColor="FFCDD2")
GREEN_FILL = PatternFill("solid", fgColor="C8E6C9")
AMBER_FILL = PatternFill("solid", fgColor="FFF2CC")
BLUE_FILL = PatternFill("solid", fgColor="DDEBF7")
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
COVER_HEADER_FILL = PatternFill("solid", fgColor="2F5597")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color="1F3864")
SUBTITLE_FONT = Font(italic=True, color="595959")
THIN_SIDE = Side(style="thin", color="D9D9D9")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
TOP_ALIGN = Alignment(vertical="top", wrap_text=False)


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
    _guard_capacity(files)
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
        _write_rows(
            sheet,
            item["rows"],
            item.get("currency") or _currency_from_rows(item["rows"]),
        )

    book.save(path)
    return path


def _guard_capacity(files: list[dict]) -> None:
    for item in files:
        rows = item.get("rows") or []
        if len(rows) > MAX_BANK_SHEET_ROWS:
            filename = (item.get("meta") or {}).get("filename") or "statement"
            raise ValueError(
                f"{filename} produced {len(rows):,} transaction rows. "
                f"Excel supports at most {MAX_BANK_SHEET_ROWS:,} data rows per sheet. "
                "No rows were written; split the statement into smaller date ranges."
            )


def _write_rows(sheet, rows: list[dict], currency: dict) -> None:
    if len(rows) > MAX_BANK_SHEET_ROWS:
        raise ValueError(
            f"This sheet would contain {len(rows):,} transaction rows. "
            f"Excel supports at most {MAX_BANK_SHEET_ROWS:,} data rows per sheet."
        )
    sheet.append(HEADERS)
    _style_header(sheet, 1, HEADER_FILL, HEADER_FONT)
    for row in rows:
        flags = _flag_text(
            row.get("flags") if row.get("flags") is not None else row.get("validation_flags")
        )
        code, status = _row_currency(row, currency)
        inferred = status == "inferred"
        money_format = _money_format(code, inferred)
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
                _currency_text(row, currency),
            ]
        )
        excel_row = sheet.max_row
        sheet.cell(excel_row, 1).number_format = DATE_FORMAT
        for col in (4, 5, 6):
            sheet.cell(excel_row, col).number_format = money_format
        for col in range(1, len(HEADERS) + 1):
            cell = sheet.cell(excel_row, col)
            cell.border = CELL_BORDER
            cell.alignment = TOP_ALIGN
        tokens = _flag_tokens(flags)
        if "balance_mismatch" in tokens or "running_balance_break" in tokens:
            fill = RED_FILL
        elif "duplicate_source_row" in tokens:
            fill = AMBER_FILL
        elif inferred or "inferred_from_balance" in tokens:
            fill = BLUE_FILL
        else:
            fill = None
        if fill is not None:
            for col in range(1, len(HEADERS) + 1):
                sheet.cell(excel_row, col).fill = fill
    last_col = get_column_letter(len(HEADERS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    widths = [14, 48, 16, 14, 14, 14, 36, 30, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


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
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Statement currency is shown per file; amounts are never converted."
    sheet["A2"].font = SUBTITLE_FONT
    sheet.append([])
    sheet.append(COVER_HEADERS)
    _style_header(sheet, 4, COVER_HEADER_FILL, HEADER_FONT)
    for item, title in zip(files, names):
        check = item["check"]
        meta = item["meta"]
        currency = item.get("currency") or _currency_from_rows(item.get("rows") or [])
        code, status = _decision_currency(currency)
        inferred = bool(check.get("opening_inferred")) or status == "inferred"
        status_text = str(check.get("status") or "")
        if status_text == "match":
            label = "MATCH"
            fill = GREEN_FILL
        elif status_text == "unverified":
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
                currency_label(currency) if currency else "Unknown",
            ]
        )
        excel_row = sheet.max_row
        if fill is not None:
            for col in range(1, len(COVER_HEADERS) + 1):
                sheet.cell(excel_row, col).fill = fill
        money_format = _money_format(code, inferred)
        sheet.cell(excel_row, 7).number_format = money_format
        sheet.cell(excel_row, 8).number_format = money_format
        sheet.cell(excel_row, 9).number_format = money_format
        for col in range(1, len(COVER_HEADERS) + 1):
            cell = sheet.cell(excel_row, col)
            cell.border = CELL_BORDER
            cell.alignment = TOP_ALIGN
    if any(item["check"].get("opening_inferred") for item in files):
        sheet.cell(4, 7).value = "Opening (inferred)"
    sheet.freeze_panes = "A5"
    sheet.row_dimensions[1].height = 24
    sheet.row_dimensions[2].height = 18
    widths = [36, 22, 18, 18, 14, 10, 18, 16, 16, 12, 12, 34, 20]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _style_header(sheet, row: int, fill: PatternFill, font: Font) -> None:
    for cell in sheet[row]:
        cell.fill = fill
        cell.font = font
        cell.border = CELL_BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _currency_from_rows(rows: list[dict]) -> dict:
    for row in rows:
        if row.get("currency_code") or row.get("currency_status"):
            return {
                "currency_code": row.get("currency_code"),
                "currency_status": row.get("currency_status"),
                "currency_source": row.get("currency_source"),
            }
    return {}


def _decision_currency(currency: dict) -> tuple[str | None, str | None]:
    return (
        (currency.get("currency_code") or "").upper() or None,
        currency.get("currency_status"),
    )


def _row_currency(row: dict, currency: dict) -> tuple[str | None, str | None]:
    code = (row.get("currency_code") or "").upper() or (
        currency.get("currency_code") or ""
    ).upper() or None
    status = row.get("currency_status") or currency.get("currency_status")
    return code, status


def _currency_text(row: dict, currency: dict) -> str:
    code, status = _row_currency(row, currency)
    data = {
        "currency_code": code,
        "currency_status": status,
        "currency_symbols": currency.get("currency_symbols") or [],
    }
    return currency_label(data)


def _money_format(code: str | None, inferred: bool) -> str:
    if code:
        return excel_number_format(code, inferred=inferred)
    return excel_neutral_number_format(inferred)


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
