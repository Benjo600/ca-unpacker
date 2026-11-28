"""The single source of truth for how every generated Excel pack looks.

Every writer in ``apps/engine/pack`` (and the reconciliation export) calls these
helpers instead of styling cells itself, so a bank pack, a GSTR pack and a
reconciliation grid read like pages of the same document.

The look is deliberately calm and editorial:

* one ink colour for text, one grey for secondary text, one clay accent used
  only for the rule under a cover masthead and for the left edge of an
  exception cell;
* Georgia for the cover title and section headings, Segoe UI for tables;
* no colour blocks, no zebra banding, hairline rules between rows only;
* an exception is marked by a tint on the one status cell plus a clay left
  border, never by painting the whole row, so it stays legible in black and
  white print.

Contracts the writers rely on and this module must never break:

* a table's header row stays exactly where the writer put it;
* money keeps the pack's own number format (Indian lakh/crore for INR);
* no helper merges cells, so every value stays machine-readable.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.worksheet.properties import PageSetupProperties

from apps.engine.pack.formatting import INR_MONEY_FORMAT, plural

# --- palette ---------------------------------------------------------------
# Every colour in a pack comes from here.  Nothing else defines a colour.
INK = "1F1F1D"
SECONDARY = "6B6B66"
HAIRLINE = "D8D5CC"
WARM_PAPER = "FAF9F5"
ACCENT = "C15F3C"
EXCEPTION_TINT = "FBF1EC"
WHITE = "FFFFFF"

# --- type ------------------------------------------------------------------
COVER_FAMILY = "Georgia"  # titles and section headings
BODY_FAMILY = "Segoe UI"  # tables and running text

COVER_TITLE_FONT = Font(name=COVER_FAMILY, size=18, bold=True, color=INK)
SECTION_FONT = Font(name=COVER_FAMILY, size=12, bold=True, color=INK)
HEADER_FONT = Font(name=BODY_FAMILY, size=9, bold=True, color=INK)
BODY_FONT = Font(name=BODY_FAMILY, size=9, color=INK)
LABEL_FONT = Font(name=BODY_FAMILY, size=9, bold=True, color=INK)
META_FONT = Font(name=BODY_FAMILY, size=9, color=SECONDARY)
MUTED_FONT = Font(name=BODY_FAMILY, size=9, italic=True, color=SECONDARY)
LINK_FONT = Font(name=BODY_FAMILY, size=9, color=INK, underline="single")
COVER_META_FONT = Font(name=BODY_FAMILY, size=10, color=SECONDARY)

# --- fills -----------------------------------------------------------------
EXCEPTION_FILL = PatternFill("solid", fgColor=EXCEPTION_TINT)
NO_FILL = PatternFill(fill_type=None)

# --- rules -----------------------------------------------------------------
HAIRLINE_SIDE = Side(style="thin", color=HAIRLINE)
HEADER_RULE = Side(style="thick", color=INK)
ACCENT_SIDE = Side(style="medium", color=ACCENT)

ROW_RULE = Border(bottom=HAIRLINE_SIDE)
HEADER_BORDER = Border(bottom=HEADER_RULE)
EXCEPTION_BORDER = Border(left=ACCENT_SIDE, bottom=HAIRLINE_SIDE)

# --- number formats --------------------------------------------------------
MONEY_FORMAT = INR_MONEY_FORMAT
DATE_FORMAT = "DD-MM-YYYY"

# --- sheet names -----------------------------------------------------------
# A cover is sheet 1 of every workbook, so these names belong to covers and
# nothing else.  A reader that used to open the first sheet opens the first
# sheet that is not one of these instead.
COVER_SHEET_TITLES = ("Contents", "Cover", "Balance Check")

# --- geometry --------------------------------------------------------------
HEADER_HEIGHT = 20
BODY_HEIGHT = 16
SIGN_OFF_HEIGHT = 22

# Excel refuses a cell longer than 32,767 characters and a text cell holding an
# illegal XML control character crashes the save, so every string goes through
# ``sanitize_text`` before it reaches a sheet.
MAX_CELL_CHARS = 32_767
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")
_WRAP_LEFT = Alignment(horizontal="left", vertical="top", wrap_text=True)


# ---------------------------------------------------------------------------
# text safety
# ---------------------------------------------------------------------------
def sanitize_text(value: str) -> str:
    """Return *value* as text Excel can always store.

    Control characters are stripped (they break the XML inside an .xlsx), the
    length is capped at Excel's own limit, and everything else is left exactly
    as it was.
    """
    text = _ILLEGAL_XML.sub("", str(value))
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS]
    return text


def sanitize_value(value: Any) -> Any:
    """Sanitise strings, pass numbers, dates and blanks through untouched."""
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def _as_text_cell(cell) -> None:
    """Store a leading "=" as text so it can never become a live formula."""
    if cell.data_type == "f" or (
        isinstance(cell.value, str) and cell.value.startswith("=")
    ):
        cell.data_type = "s"


def append_row(sheet, values: Iterable[Any]) -> int:
    """Append one sanitised row and return its Excel row number.

    Every writer uses this instead of ``sheet.append`` so that a description
    copied from a client document can never smuggle a formula into the pack.
    """
    row_values = [sanitize_value(value) for value in values]
    sheet.append(row_values)
    row = sheet.max_row
    for index in range(1, len(row_values) + 1):
        _as_text_cell(sheet.cell(row, index))
    return row


def put(sheet, row: int, col: int, value: Any, font: Font | None = None,
        alignment: Alignment | None = None):
    """Write one sanitised value into a cell and return the cell."""
    cell = sheet.cell(row, col)
    cell.value = sanitize_value(value)
    _as_text_cell(cell)
    if font is not None:
        cell.font = font
    if alignment is not None:
        cell.alignment = alignment
    return cell


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
def style_header(
    sheet,
    ncols: int,
    row: int = 1,
    money_cols: Sequence[int] = (),
) -> None:
    """Ink-on-white header band ruled off with a heavy line, no fill blocks."""
    sheet.row_dimensions[row].height = HEADER_HEIGHT
    for col in range(1, ncols + 1):
        cell = sheet.cell(row, col)
        cell.fill = NO_FILL
        cell.font = HEADER_FONT
        cell.border = HEADER_BORDER
        cell.alignment = _RIGHT if col in money_cols else _LEFT


def style_body(
    sheet,
    first_row: int,
    last_row: int,
    ncols: int,
    money_cols: Sequence[int] = (),
    date_cols: Sequence[int] = (),
    right_cols: Sequence[int] = (),
    wrap_cols: Sequence[int] = (),
    money_format: str | None = None,
    row_height: int | None = BODY_HEIGHT,
    auto_align_numbers: bool = False,
) -> None:
    """Hairline rules only: no banding, white background, one type size.

    ``money_cols`` get the pack's money format and are right-aligned;
    ``right_cols`` are right-aligned but keep whatever format the writer set
    (used where a column carries per-row currency suffixes); ``date_cols`` are
    centred and shown as DD-MM-YYYY; ``wrap_cols`` hold long text and wrap.
    ``auto_align_numbers`` right-aligns any remaining numeric cell without
    touching its number format, which suits sheets whose columns are decided
    by the data rather than the writer.
    """
    if last_row < first_row:
        return
    format_string = money_format or MONEY_FORMAT
    for row in range(first_row, last_row + 1):
        if row_height is not None:
            sheet.row_dimensions[row].height = row_height
        for col in range(1, ncols + 1):
            cell = sheet.cell(row, col)
            # A bold label already in the cell (a total line, a section note)
            # keeps its weight; everything else takes the body type.
            if not getattr(cell.font, "bold", False):
                cell.font = BODY_FONT
            cell.border = ROW_RULE
            if col in money_cols:
                cell.number_format = format_string
                cell.alignment = _RIGHT
            elif col in date_cols:
                cell.number_format = DATE_FORMAT
                cell.alignment = _CENTER
            elif col in right_cols:
                cell.alignment = _RIGHT
            elif col in wrap_cols:
                cell.alignment = _WRAP_LEFT
            elif auto_align_numbers and isinstance(cell.value, (int, float)):
                cell.alignment = _RIGHT
            else:
                cell.alignment = _LEFT


def mark_exception(sheet, row: int, col: int, tint: bool = True) -> None:
    """Flag one cell as an exception: clay left edge plus a light tint.

    Only the status cell is marked, never the whole row, so a black-and-white
    print still reads as a normal table with one cell set off.
    """
    cell = sheet.cell(row, col)
    if tint:
        cell.fill = EXCEPTION_FILL
    cell.border = EXCEPTION_BORDER


def set_widths(sheet, widths: Sequence[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


# ---------------------------------------------------------------------------
# print
# ---------------------------------------------------------------------------
def _footer_text(*parts: str) -> str:
    """Join footer parts, escaping Excel's own control characters."""
    clean = [str(part).replace("&", "&&").strip() for part in parts if str(part or "").strip()]
    return "  ·  ".join(clean)


def print_setup(
    sheet,
    ncols: int,
    header_row: int | None = 1,
    landscape: bool = True,
    footer_parts: Sequence[str] = (),
    print_area: bool = True,
) -> None:
    """A4, fit to width, gridlines off, header repeated, page-numbered footer."""
    if header_row:
        sheet.print_title_rows = f"{header_row}:{header_row}"
    else:
        sheet.print_title_rows = None
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.orientation = "landscape" if landscape else "portrait"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    sheet.print_options.horizontalCentered = True
    sheet.print_options.gridLines = False
    sheet.page_margins.left = 0.4
    sheet.page_margins.right = 0.4
    sheet.page_margins.top = 0.5
    sheet.page_margins.bottom = 0.5
    sheet.page_margins.header = 0.2
    sheet.page_margins.footer = 0.2
    parts = [str(part) for part in footer_parts if str(part or "").strip()]
    if parts:
        sheet.oddFooter.center.text = f"{_footer_text(*parts)}  ·  Page &P of &N"
        sheet.oddFooter.center.size = 8
        sheet.oddFooter.center.color = SECONDARY
    if print_area:
        last_col = get_column_letter(max(ncols, 1))
        sheet.print_area = f"A1:{last_col}{max(sheet.max_row, 1)}"


def cover_print_setup(sheet, ncols: int = 3, footer_parts: Sequence[str] = ()) -> None:
    """A cover is a page of prose: portrait, one page wide, no repeated header."""
    print_setup(
        sheet,
        ncols,
        header_row=None,
        landscape=False,
        footer_parts=footer_parts,
    )


# ---------------------------------------------------------------------------
# cover / contents
# ---------------------------------------------------------------------------
def generated_stamp() -> str:
    """The local date and time a pack was written, in DD-MM-YYYY HH:MM."""
    return datetime.now().strftime("%d-%m-%Y %H:%M")


def is_cover_sheet(name: str) -> bool:
    """True when *name* is one a cover may carry."""
    wanted = str(name or "").strip().casefold()
    return any(title.casefold() == wanted for title in COVER_SHEET_TITLES)


def data_sheet_name(sheet_names: Sequence[str], preferred: str = "") -> str:
    """The sheet a reader should open for *preferred*, else the first data sheet.

    Every workbook opens on a cover now, so "the first sheet" is no longer the
    data.  The sheet asked for wins, then the first sheet whose name is not a
    cover, then the first sheet there is (a single-sheet export keeps working).
    """
    names = [str(name) for name in sheet_names or ()]
    if preferred and preferred in names:
        return preferred
    for name in names:
        if not is_cover_sheet(name):
            return name
    return names[0] if names else ""


_IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "firm": ("firm", "firm_name", "practice", "practice_name"),
    "client": ("client", "client_name", "client_label"),
    "period": ("period", "period_label", "return_period", "rtnprd", "fp", "ret_period"),
}


def folder_identity(path) -> dict[str, str]:
    """Client and period read off a pack's own folder, when it is one.

    Packs are written to ``<pack root>/<client>/<period>/file.xlsx``, so the two
    folder names are the client and the period by construction.  Nothing is
    guessed: a file written anywhere else (a test's temp folder, a desktop copy)
    simply yields no identity, and the cover leaves those lines out.
    """
    try:
        from apps.engine.library import get_library_path
        from apps.engine.settings import load_settings

        roots = [get_library_path() / "packs"]
        custom = str(load_settings().get("output_root") or "").strip()
        if custom:
            roots.append(Path(custom))
        parent = Path(path).parent.resolve()
        for root in roots:
            try:
                relative = parent.relative_to(root.resolve())
            except (ValueError, OSError):
                continue
            if len(relative.parts) >= 2:
                return {"client": relative.parts[-2], "period": relative.parts[-1]}
    except Exception:  # a workbook must never fail over a cover line
        return {}
    return {}


def cover_identity(
    *sources: Mapping | None,
    firm: str = "",
    client: str = "",
    period: str = "",
    generated: str = "",
) -> dict[str, str]:
    """Find the firm, client and period for a cover from the data at hand.

    Writers are handed a ``meta``/``result`` mapping, not a database handle, so
    the cover shows what is verifiably known: an explicit value always wins, a
    known key in a source mapping is used next, and anything still unknown is
    left blank rather than guessed.
    """
    found = {"firm": firm, "client": client, "period": period, "generated": generated}
    for key, names in _IDENTITY_KEYS.items():
        if found[key]:
            continue
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            for name in names:
                value = source.get(name)
                if isinstance(value, str) and value.strip():
                    found[key] = value.strip()
                    break
            if found[key]:
                break
    found["generated"] = found["generated"] or generated_stamp()
    return found


def _rule(sheet, row: int, ncols: int, colour: str | None = None) -> None:
    """Draw one thin rule across *ncols* columns of an otherwise empty row."""
    edge = Side(style="thin", color=colour or ACCENT)
    for col in range(1, max(ncols, 1) + 1):
        cell = sheet.cell(row, col)
        cell.fill = NO_FILL
        cell.border = Border(bottom=edge)


def cover_rule(sheet, row: int, ncols: int = 3, height: int | None = None,
               accent: bool = True) -> None:
    """The clay rule under a masthead (or a hairline between two blocks)."""
    _rule(sheet, row, ncols, ACCENT if accent else HAIRLINE)
    if height is not None:
        sheet.row_dimensions[row].height = height


def cover_masthead(
    sheet,
    *,
    firm: str = "",
    title: str = "",
    lines: Sequence[str] = (),
    width: int = 3,
) -> int:
    """Firm, pack title and the plain facts, then one clay rule.

    Returns the first row the caller may use after the masthead.
    """
    row = 1
    if firm:
        put(sheet, row, 1, firm.upper(), COVER_TITLE_FONT)
        row += 1
    if title:
        # With a firm name above it the pack title is a section heading; on its
        # own it carries the page.
        put(sheet, row, 1, title, SECTION_FONT if firm else COVER_TITLE_FONT)
        row += 1
    for line in lines:
        if line:
            put(sheet, row, 1, line, COVER_META_FONT)
            row += 1
    cover_rule(sheet, row, width, height=6)
    return row + 2


def cover_heading(sheet, row: int, text: str) -> int:
    """A Georgia section heading; returns the next free row."""
    put(sheet, row, 1, text, SECTION_FONT)
    return row + 1


def cover_index(
    sheet,
    row: int,
    entries: Sequence[tuple[str, str, int | None]],
    heading: str = "Contents",
) -> int:
    """A linked index: sheet name, one-line description, row count.

    ``entries`` is ``(sheet name, description, row count)``; a count of
    ``None`` is left out.  Each name is an internal link to that sheet.
    """
    row = cover_heading(sheet, row, heading)
    for name, description, count in entries:
        cell = put(sheet, row, 1, name, LINK_FONT)
        cell.hyperlink = Hyperlink(ref=cell.coordinate, location=f"'{name}'!A1")
        detail = (
            f"{plural(count, 'row')} · {description}" if count is not None else description
        )
        put(sheet, row, 2, detail, META_FONT)
        row += 1
    cover_rule(sheet, row, 2, accent=False)
    return row + 1


def cover_pairs(
    sheet,
    row: int,
    pairs: Sequence[tuple[str, Any]],
    heading: str | None = None,
    money_format: str | None = None,
) -> int:
    """A ruled label/value block: bold label in A, value in B."""
    if heading:
        row = cover_heading(sheet, row, heading)
    for label, value in pairs:
        label_cell = put(sheet, row, 1, label, LABEL_FONT, _LEFT)
        label_cell.border = ROW_RULE
        value_cell = put(sheet, row, 2, value, BODY_FONT)
        value_cell.border = ROW_RULE
        if isinstance(value, bool):
            value_cell.alignment = _LEFT
        elif isinstance(value, (int, float)):
            value_cell.alignment = _RIGHT
            if isinstance(value, float):
                value_cell.number_format = money_format or MONEY_FORMAT
        else:
            value_cell.alignment = _LEFT
        row += 1
    return row + 1


def cover_notes(sheet, row: int, notes: Iterable[str]) -> int:
    """Plain sentences under a block, in secondary ink."""
    for note in notes:
        if note:
            put(sheet, row, 1, note, MUTED_FONT)
            row += 1
    return row + 1


def cover_legend(
    sheet,
    row: int,
    entries: Sequence[tuple[str, str]],
    heading: str = "How to read this sheet",
) -> int:
    """A flag legend in plain words; the first column carries the mark itself."""
    row = cover_heading(sheet, row, heading)
    for label, meaning in entries:
        cell = put(sheet, row, 1, label, LABEL_FONT, _LEFT)
        cell.fill = EXCEPTION_FILL
        cell.border = Border(left=ACCENT_SIDE, bottom=HAIRLINE_SIDE)
        put(sheet, row, 2, meaning, META_FONT)
        row += 1
    return row + 1


def cover_sign_off(sheet, row: int, heading: str = "Sign-off") -> int:
    """Prepared / Reviewed / Date with empty ruled boxes for pen and paper."""
    row = cover_heading(sheet, row, heading)
    for label in ("Prepared by", "Reviewed by", "Date"):
        put(sheet, row, 1, label, LABEL_FONT, _LEFT)
        for col in (2, 3):
            box = sheet.cell(row, col)
            box.value = None
            box.border = Border(bottom=HAIRLINE_SIDE)
        sheet.row_dimensions[row].height = SIGN_OFF_HEIGHT
        row += 1
    return row


def cover_sheet(
    sheet,
    *,
    firm: str = "",
    title: str = "",
    lines: Sequence[str] = (),
    entries: Sequence[tuple[str, str, int | None]] = (),
    index_heading: str = "Contents",
    blocks: Sequence[tuple[str | None, Sequence[tuple[str, Any]]]] = (),
    notes: Iterable[str] = (),
    legend: Sequence[tuple[str, str]] = (),
    sign_off: bool = True,
    width: int = 3,
) -> int:
    """Write a whole cover in the standard order and return the last row.

    Order: masthead and clay rule, the linked index, the pack's own check or
    summary blocks, plain notes, the flag legend, then the sign-off lines.
    """
    row = cover_masthead(sheet, firm=firm, title=title, lines=lines, width=width)
    if entries:
        row = cover_index(sheet, row, entries, heading=index_heading)
    for heading, pairs in blocks:
        row = cover_pairs(sheet, row, pairs, heading=heading)
    row = cover_notes(sheet, row, notes)
    if legend:
        row = cover_legend(sheet, row, legend)
    if sign_off:
        row = cover_sign_off(sheet, row)
    return row


# ---------------------------------------------------------------------------
# small pieces the older writers still ask for
# ---------------------------------------------------------------------------
def style_note(sheet, cell_ref: str) -> None:
    """A quiet single-line note."""
    sheet[cell_ref].font = MUTED_FONT


__all__ = [
    "INK",
    "SECONDARY",
    "HAIRLINE",
    "WARM_PAPER",
    "ACCENT",
    "EXCEPTION_TINT",
    "WHITE",
    "COVER_TITLE_FONT",
    "SECTION_FONT",
    "HEADER_FONT",
    "BODY_FONT",
    "LABEL_FONT",
    "META_FONT",
    "MUTED_FONT",
    "LINK_FONT",
    "EXCEPTION_FILL",
    "NO_FILL",
    "HEADER_BORDER",
    "ROW_RULE",
    "EXCEPTION_BORDER",
    "MONEY_FORMAT",
    "DATE_FORMAT",
    "HEADER_HEIGHT",
    "BODY_HEIGHT",
    "MAX_CELL_CHARS",
    "sanitize_text",
    "sanitize_value",
    "append_row",
    "put",
    "plural",
    "style_header",
    "style_body",
    "mark_exception",
    "set_widths",
    "print_setup",
    "cover_print_setup",
    "generated_stamp",
    "COVER_SHEET_TITLES",
    "is_cover_sheet",
    "data_sheet_name",
    "folder_identity",
    "cover_identity",
    "cover_masthead",
    "cover_heading",
    "cover_rule",
    "cover_index",
    "cover_pairs",
    "cover_notes",
    "cover_legend",
    "cover_sign_off",
    "cover_sheet",
    "style_note",
]
