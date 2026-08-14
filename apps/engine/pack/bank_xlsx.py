from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = [
    "Date",
    "Description",
    "Cheque / Ref",
    "Debit",
    "Credit",
    "Balance",
    "Source",
]


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
    _cover_multi(cover, files)

    used: set[str] = {"Balance Check"}
    for item in files:
        title = _sheet_name(item["meta"].get("filename") or "Transactions", used)
        used.add(title)
        sheet = book.create_sheet(title)
        _write_rows(sheet, item["rows"])

    book.save(path)
    return path


def _write_rows(sheet, rows: list[dict]) -> None:
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(
            [
                row.get("date"),
                row.get("description"),
                row.get("cheque_ref"),
                row.get("debit"),
                row.get("credit"),
                row.get("balance"),
                row.get("source"),
            ]
        )
    widths = [14, 48, 16, 14, 14, 14, 36]
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


def _cover_multi(sheet, files: list[dict]) -> None:
    sheet["A1"] = "Bank statement pack"
    sheet["A1"].font = Font(bold=True, size=14)
    sheet["A2"] = "Each source file is checked on its own. Do not mix two statements when you test."
    sheet.append([])
    headers = ["File", "Bank", "Rows", "Opening", "Stated close", "Computed close", "Result"]
    sheet.append(headers)
    for cell in sheet[4]:
        cell.font = Font(bold=True)
    for item in files:
        check = item["check"]
        meta = item["meta"]
        status = "MATCH" if check.get("match") else "MISMATCH"
        sheet.append(
            [
                meta.get("filename"),
                meta.get("profile_label"),
                check.get("row_count"),
                check.get("opening_balance"),
                check.get("stated_closing"),
                check.get("computed_closing"),
                status,
            ]
        )
        fill = PatternFill("solid", fgColor="C8E6C9" if check.get("match") else "FFCDD2")
        for col in range(1, 8):
            sheet.cell(sheet.max_row, col).fill = fill
    widths = [36, 22, 10, 16, 16, 16, 12]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
