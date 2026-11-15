"""Shared Excel look-and-feel for every pack the app writes.

Keeping the palette, fonts and helpers in one place means the bank, GST,
reconciliation and register workbooks all come out looking like they belong
to the same product. Only openpyxl is used, and every colour is a plain ARGB
string so tests can assert on it directly.

Design rules the writers rely on:

* A table's header row stays exactly where the writer put it (never shifted),
  so downstream code and tests can still find headers at a fixed row.
* Banding is applied to alternating data rows, then any status fill (red /
  green / amber) is painted on top so flags always win.
* Money keeps the exact ``#,##0.00`` format the older code used.
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

# --- palette ---------------------------------------------------------------
HEADER_BG = "1F3864"
HEADER_FG = "FFFFFF"
BAND_BG = "F2F6FB"
LABEL_BG = "E8EEF7"
RED_BG = "FFCDD2"
GREEN_BG = "C8E6C9"
AMBER_BG = "FFF2CC"
BORDER_BG = "C9D3E3"
TITLE_FG = "1F3864"
MUTED_FG = "5B6472"

# --- reusable style objects ------------------------------------------------
HEADER_FILL = PatternFill("solid", fgColor=HEADER_BG)
BAND_FILL = PatternFill("solid", fgColor=BAND_BG)
LABEL_FILL = PatternFill("solid", fgColor=LABEL_BG)
RED_FILL = PatternFill("solid", fgColor=RED_BG)
GREEN_FILL = PatternFill("solid", fgColor=GREEN_BG)
AMBER_FILL = PatternFill("solid", fgColor=AMBER_BG)

HEADER_FONT = Font(bold=True, color=HEADER_FG, size=11)
TITLE_FONT = Font(bold=True, size=14, color=TITLE_FG)
LABEL_FONT = Font(bold=True, color=TITLE_FG, size=11)
TOTAL_FONT = Font(bold=True, size=11)
MUTED_FONT = Font(italic=True, size=9, color=MUTED_FG)

THIN_SIDE = Side(style="thin", color=BORDER_BG)
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

MONEY_FORMAT = "#,##0.00"
DATE_FORMAT = "DD-MM-YYYY"
HEADER_HEIGHT = 24

_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")
_WRAP_LEFT = Alignment(horizontal="left", vertical="top", wrap_text=True)


def style_header(sheet, ncols: int, row: int = 1) -> None:
    """Turn *row* into a coloured, bordered, frozen-style header band."""
    sheet.row_dimensions[row].height = HEADER_HEIGHT
    for col in range(1, ncols + 1):
        cell = sheet.cell(row, col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = _CENTER
        cell.border = CELL_BORDER


def style_body(
    sheet,
    first_row: int,
    last_row: int,
    ncols: int,
    money_cols: tuple[int, ...] = (),
    date_cols: tuple[int, ...] = (),
    band: bool = True,
) -> None:
    """Border every body cell, band alternate rows and set number formats."""
    if last_row < first_row:
        return
    for offset, row in enumerate(range(first_row, last_row + 1)):
        banded = band and offset % 2 == 1
        for col in range(1, ncols + 1):
            cell = sheet.cell(row, col)
            cell.border = CELL_BORDER
            if banded:
                cell.fill = BAND_FILL
            if col in money_cols:
                cell.number_format = MONEY_FORMAT
                cell.alignment = _RIGHT
            elif col in date_cols:
                cell.number_format = DATE_FORMAT
                cell.alignment = _CENTER


def fill_row(sheet, row: int, ncols: int, fill) -> None:
    """Paint a whole row with *fill* (used for status flags; beats banding)."""
    for col in range(1, ncols + 1):
        sheet.cell(row, col).fill = fill


def style_title(sheet, cell_ref: str = "A1") -> None:
    sheet[cell_ref].font = TITLE_FONT


def style_note(sheet, cell_ref: str) -> None:
    """Small italic note - used for the 'how to read me' lines."""
    sheet[cell_ref].font = MUTED_FONT


def style_count_pairs(sheet, first_row: int, last_row: int, value_col: int = 2) -> None:
    """Label/value rows on the cover sheets: bold label, bordered pair."""
    if last_row < first_row:
        return
    for row in range(first_row, last_row + 1):
        label = sheet.cell(row, 1)
        label.font = LABEL_FONT
        label.fill = LABEL_FILL
        label.border = CELL_BORDER
        label.alignment = _LEFT
        value = sheet.cell(row, value_col)
        value.border = CELL_BORDER
        value.alignment = _LEFT


def set_widths(sheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def print_setup(sheet, ncols: int, header_row: int = 1, landscape: bool = True) -> None:
    """Repeat the header on every printed page and fit the columns to width."""
    sheet.print_title_rows = f"{header_row}:{header_row}"
    sheet.page_setup.orientation = "landscape" if landscape else "portrait"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    sheet.print_options.horizontalCentered = True
    sheet.page_margins.left = 0.4
    sheet.page_margins.right = 0.4
    sheet.page_margins.top = 0.5
    sheet.page_margins.bottom = 0.5
    last_col = get_column_letter(max(ncols, 1))
    sheet.print_area = f"A1:{last_col}{max(sheet.max_row, 1)}"
