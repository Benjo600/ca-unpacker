from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.currency import (
    currency_label,
    excel_neutral_number_format,
    excel_number_format,
)
from apps.engine.pack.formatting import parse_date_value, plural
from apps.engine.pack.style import (
    COVER_META_FONT,
    COVER_TITLE_FONT,
    DATE_FORMAT,
    MUTED_FONT,
    SECTION_FONT,
    append_row,
    cover_identity,
    cover_index,
    cover_legend,
    cover_notes,
    cover_rule,
    cover_sign_off,
    folder_identity,
    mark_exception,
    print_setup,
    put,
    set_widths,
    style_body,
    style_header,
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

# Kept for callers that build a format string by hand.
MONEY_FORMAT = "#,##0.00"
MONEY_INFERRED_FORMAT = '#,##0.00" (inferred)"'

# Excel's hard worksheet limit.  A bank statement is never truncated: the
# writer raises a clear error instead.
MAX_BANK_SHEET_ROWS = 1_048_575

# The "Flags" column is the one cell that carries the exception mark.
FLAGS_COL = HEADERS.index("Flags") + 1
CURRENCY_NOTE = (
    "Statement currency is shown on every row; amounts are never converted."
)
LEGEND = (
    ("Shaded flag", "That row needs your check before you rely on it."),
    ("Result", "MATCH means the running balance adds up; MISMATCH means it does not."),
)


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


def _pending_approval_rows(rows: list[dict]) -> list[dict]:
    """Rows invented from a balance gap, which a CA has to approve by hand."""
    pending = []
    for row in rows or []:
        if str(row.get("approval") or "").lower() == "approved":
            continue
        if row.get("needs_approval"):
            pending.append(row)
            continue
        flags = row.get("flags") if row.get("flags") is not None else row.get("validation_flags")
        if "inferred_from_balance" in _flag_tokens(_flag_text(flags)):
            pending.append(row)
    return pending


def _write_pending_sheet(sheet, rows: list[dict], currency: dict, identity: dict) -> None:
    put(sheet, 1, 1, "Rows inferred from a gap in the balance", COVER_TITLE_FONT)
    put(
        sheet,
        2,
        1,
        f"{plural(len(rows), 'row')} below are NOT printed in the statement. They exist "
        "only because the running balance jumped. Check each one on its source page, "
        "then approve or remove before using this pack.",
        MUTED_FONT,
    )
    _write_rows(sheet, rows, currency, header_row=4)
    print_setup(
        sheet,
        len(HEADERS),
        header_row=4,
        footer_parts=_footer_parts(identity, sheet.title),
    )


def write_bank_workbook(
    path: Path, files: list[dict], identity: dict | None = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _guard_capacity(files)
    book = Workbook()
    cover = book.active
    if cover is None:  # a new workbook always starts with one sheet
        raise ValueError("Workbook has no active sheet")
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

    identity = _identity(files, path, identity)
    pending_sheets: list[tuple[str, int]] = []

    for item, title in zip(files, names):
        currency = item.get("currency") or _currency_from_rows(item["rows"])
        sheet = book.create_sheet(title)
        _write_rows(sheet, item["rows"], currency)
        print_setup(
            sheet,
            len(HEADERS),
            header_row=1,
            footer_parts=_footer_parts(identity, title),
        )
        pending = _pending_approval_rows(item["rows"])
        if pending:
            approval_sheet = book.create_sheet(_sheet_name(f"Approve {title}", used))
            used.add(approval_sheet.title)
            _write_pending_sheet(approval_sheet, pending, currency, identity)
            pending_sheets.append((approval_sheet.title, len(pending)))

    _cover_multi(cover, files, names, identity, pending_sheets)
    book.save(path)
    return path


def _identity(
    files: list[dict], path: Path | None = None, given: dict | None = None
) -> dict:
    """Firm, client and period, when the caller, the folder or a meta knows them."""
    sources: list[dict] = [given or {}]
    for item in files or []:
        meta = item.get("meta") or {}
        sources.extend([meta, item.get("check") or {}, item])
    if path is not None:
        sources.append(folder_identity(path))
    return cover_identity(*sources)


def _footer_parts(identity: dict, sheet_name: str = "") -> list[str]:
    parts = [
        identity.get("client") or "",
        identity.get("period") or "",
        f"Bank statement pack — {sheet_name}" if sheet_name else "Bank statement pack",
    ]
    return [part for part in parts if part]


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


def _write_rows(sheet, rows: list[dict], currency: dict, header_row: int = 1) -> None:
    if len(rows) > MAX_BANK_SHEET_ROWS:
        raise ValueError(
            f"This sheet would contain {len(rows):,} transaction rows. "
            f"Excel supports at most {MAX_BANK_SHEET_ROWS:,} data rows per sheet."
        )
    for col, name in enumerate(HEADERS, start=1):
        put(sheet, header_row, col, name)
    style_header(sheet, len(HEADERS), header_row)
    exceptions: list[int] = []
    for row in rows:
        flags = _flag_text(
            row.get("flags") if row.get("flags") is not None else row.get("validation_flags")
        )
        code, status = _row_currency(row, currency)
        inferred = status == "inferred"
        money_format = _money_format(code, inferred)
        append_row(
            sheet,
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
            ],
        )
        excel_row = sheet.max_row
        sheet.cell(excel_row, 1).number_format = DATE_FORMAT
        for col in (4, 5, 6):
            sheet.cell(excel_row, col).number_format = money_format
        tokens = _flag_tokens(flags)
        if (
            "balance_mismatch" in tokens
            or "running_balance_break" in tokens
            or "duplicate_source_row" in tokens
            or "inferred_from_balance" in tokens
        ):
            exceptions.append(excel_row)
    if sheet.max_row > header_row:
        style_body(
            sheet,
            header_row + 1,
            sheet.max_row,
            len(HEADERS),
            right_cols=(4, 5, 6),
            date_cols=(1,),
            wrap_cols=(8,),
            row_height=None,
        )
    for excel_row in exceptions:
        mark_exception(sheet, excel_row, FLAGS_COL)
    last_col = get_column_letter(len(HEADERS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A{header_row}:{last_col}{last_row}"
    sheet.freeze_panes = f"A{header_row + 1}"
    set_widths(sheet, [14, 48, 16, 14, 14, 14, 36, 30, 18])


def _sheet_name(filename: str, used: set[str]) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[\[\]\*\?:/\\]", " ", stem)[:28].strip() or "Transactions"
    name = cleaned
    n = 2
    while name in used:
        name = f"{cleaned[:26]}_{n}"
        n += 1
    return name


def _cover_multi(
    sheet,
    files: list[dict],
    names: list[str],
    identity: dict,
    pending_sheets: list[tuple[str, int]],
) -> None:
    """The summary sheet.

    Its table header has to stay on row 4 and its first data row on row 5:
    readers and tests find the columns there, so the masthead is fixed to the
    three rows above the table and the index, legend and sign-off sit under it.
    """
    total_rows = sum(int(item["check"].get("row_count") or 0) for item in files)
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        plural(len(files), "file"),
        plural(total_rows, "row"),
        f"generated {identity.get('generated') or ''}".strip(),
        CURRENCY_NOTE,
    ]
    lines: list[tuple[str, object]] = []
    if identity.get("firm"):
        lines.append((str(identity["firm"]).upper(), COVER_TITLE_FONT))
        lines.append(("Bank statement pack", SECTION_FONT))
    else:
        lines.append(("Bank statement pack", COVER_TITLE_FONT))
    lines.append(("  ·  ".join(part for part in facts if part), COVER_META_FONT))

    for offset, (text, font) in enumerate(lines, start=1):
        put(sheet, offset, 1, text, font)
    cover_rule(sheet, max(len(lines), 1), len(COVER_HEADERS))

    for col, name in enumerate(COVER_HEADERS, start=1):
        put(sheet, 4, col, name)
    style_header(sheet, len(COVER_HEADERS), 4, money_cols=(7, 8, 9))

    mismatch_rows: list[int] = []
    for item, title in zip(files, names):
        check = item["check"]
        meta = item["meta"]
        currency = item.get("currency") or _currency_from_rows(item.get("rows") or [])
        code, status = _decision_currency(currency)
        inferred = bool(check.get("opening_inferred")) or status == "inferred"
        status_text = str(check.get("status") or "")
        if status_text == "match":
            label = "MATCH"
        elif status_text == "unverified":
            label = "COULD NOT VERIFY"
        else:
            label = "MISMATCH"
        append_row(
            sheet,
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
            ],
        )
        excel_row = sheet.max_row
        money_format = _money_format(code, inferred)
        for col in (7, 8, 9):
            sheet.cell(excel_row, col).number_format = money_format
        if label == "MISMATCH":
            mismatch_rows.append(excel_row)

    first_data = 5
    last_data = max(sheet.max_row, first_data)
    style_body(
        sheet,
        first_data,
        last_data,
        len(COVER_HEADERS),
        right_cols=(6, 7, 8, 9, 11),
        wrap_cols=(1, 12),
        row_height=None,
    )
    if any(item["check"].get("opening_inferred") for item in files):
        put(sheet, 4, 7, "Opening (inferred)")
    for excel_row in mismatch_rows:
        mark_exception(sheet, excel_row, COVER_HEADERS.index("Result") + 1)

    row = last_data + 2
    notes = []
    pending_total = sum(count for _name, count in pending_sheets)
    if pending_total:
        notes.append(
            f"{plural(pending_total, 'row')} were inferred from a gap in the balance and are "
            "not in the statement. Approve them on the \"Approve …\" sheet before using "
            "this pack."
        )
    row = cover_notes(sheet, row, notes)
    row = cover_legend(sheet, row, LEGEND)
    entries = [
        (title, f"Transactions from {item['meta'].get('filename') or 'the statement'}.", len(item.get("rows") or []))
        for item, title in zip(files, names)
    ]
    entries.extend(
        (name, "Rows inferred from a balance gap, waiting for approval.", count)
        for name, count in pending_sheets
    )
    row = cover_index(sheet, row, entries)
    cover_sign_off(sheet, row)

    sheet.freeze_panes = "A5"
    sheet.row_dimensions[1].height = 22
    sheet.row_dimensions[2].height = 18
    set_widths(sheet, [36, 22, 18, 18, 14, 10, 18, 16, 16, 12, 12, 34, 20])
    sheet.column_dimensions["A"].width = 36
    print_setup(
        sheet,
        len(COVER_HEADERS),
        header_row=4,
        footer_parts=_footer_parts(identity, "Balance Check"),
    )


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
    """A real date when the text is unambiguous, otherwise the text as received."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date_value(value)
    return parsed if parsed is not None else value


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
