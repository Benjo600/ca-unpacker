from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def write_table(path: Path, sheet_name: str, rows: list[dict], columns: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = sheet_name[:31]
    sheet.append([title for title, _key in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([_cell(row.get(key)) for _title, key in columns])
    for index, (_title, key) in enumerate(columns, start=1):
        width = 16
        if key in {"description", "trade_name", "party_name", "raw_excerpt"}:
            width = 40
        if key == "source":
            width = 28
        sheet.column_dimensions[get_column_letter(index)].width = width
    if not rows:
        sheet.append(["No rows extracted"])
    book.save(path)
    return path


def _cell(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return value
