"""Two audit-friendly files the CA can hand over: exceptions only, and a
one-page summary of what was decided.

Both read the reconciliation block of a finished pack; nothing is re-parsed and
nothing leaves the computer.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import parse_date_value, plural
from apps.engine.pack.style import (
    append_row,
    cover_heading,
    cover_identity,
    cover_sheet,
    mark_exception,
    print_setup,
    put,
    set_widths,
    style_body,
    style_header,
    style_note,
)

STATUS_LABELS = {
    "matched": "Matched",
    "books_only": "Only in books",
    "portal_only": "Only in 2B",
    "amount_mismatch": "Amount mismatch",
    "likely": "Likely (confirm)",
    "tax_mismatch": "Tax differs",
    "duplicate": "Duplicate",
    "split_merged": "Split or merged",
    "credit_note": "Credit note",
    "same_bill": "Same bill, other source",
}
EXCEPTION_STATUSES = tuple(status for status in STATUS_LABELS if status != "matched")
COUNT_ORDER = (
    ("matched", "Matched"),
    ("books_only", "Only in books"),
    ("portal_only", "Only in 2B"),
    ("amount_mismatch", "Amount mismatch"),
    ("likely", "Likely (confirm)"),
    ("tax_mismatch", "Tax differs"),
    ("duplicate", "Duplicate"),
    ("split_merged", "Split or merged"),
    ("credit_note", "Credit notes"),
    ("same_bill", "Same bill, other source"),
)
MONEY_ORDER = (
    ("On the portal (2B)", "portal_total"),
    ("In the books", "books_total"),
    ("Difference", "gap"),
    ("Credit at risk (portal only)", "credit_at_risk"),
    ("Credit claimed without support (books only)", "unsupported_credit"),
    ("Credit notes (kept separate)", "credit_note_total"),
    ("Same bill from another source (not extra credit)", "same_bill_total"),
)
EXCEPTION_HEADERS = [
    "Status",
    "Why",
    "Party",
    "GSTIN",
    "Invoice (2B)",
    "Invoice (books)",
    "Date (2B)",
    "Date (books)",
    "Amount (2B)",
    "Amount (books)",
    "Amount diff",
    "Decision",
    "Reason",
    "Note",
    "Decided by",
    "Decided on",
]
EXCEPTION_KEYS = [
    "status",
    "reason",
    "party",
    "gstin",
    "invoice_2b",
    "invoice_books",
    "date_2b",
    "date_books",
    "amount_2b",
    "amount_books",
    "amount_diff",
    "decision_label",
    "decision_reason",
    "decision_note",
    "decision_by",
    "decision_at",
]
DECISION_HEADERS = [
    "GSTIN",
    "Invoice",
    "Party",
    "Amount",
    "Decision",
    "Reason",
    "Note",
    "Decided by",
    "Decided on",
]
EXCEPTION_WIDTHS = [16, 44, 26, 18, 18, 18, 12, 12, 14, 14, 12, 12, 22, 34, 18, 20]
DECISION_WIDTHS = [18, 20, 28, 14, 12, 22, 40, 18, 20]
# The two date columns of the exceptions table, as 1-based column numbers.
EXCEPTION_DATE_COLS = (7, 8)


def _status_label(value) -> str:
    return STATUS_LABELS.get(str(value or ""), str(value or ""))


def _date_cell(value):
    """A real date when the text is unambiguous, otherwise the text as received."""
    if value is None or value == "":
        return value
    parsed = parse_date_value(value)
    return parsed if parsed is not None else value


def _header_block(
    title: str, client_name: str, period_label: str, firm: str = ""
) -> dict:
    """Masthead facts for a single-sheet export; returns the resolved identity."""
    identity = cover_identity(firm=firm, client=client_name, period=period_label)
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        f"generated {identity['generated']}",
    ]
    return {
        "identity": identity,
        "title": title,
        "facts": "  ·  ".join(part for part in facts if part),
    }


def _footer(identity: dict, suffix: str) -> list[str]:
    return [
        identity.get("client") or "",
        identity.get("period") or "",
        suffix,
    ]


def _pack_rows(recon: dict) -> list[dict]:
    return list((recon or {}).get("rows") or [])


def _exception_rows(recon: dict) -> list[dict]:
    return [
        row
        for row in _pack_rows(recon)
        if str(row.get("status") or "") in EXCEPTION_STATUSES
    ]


def _row_amount(row: dict) -> float:
    for key in ("amount_diff", "amount_2b", "amount_books"):
        value = row.get(key)
        if value is not None:
            try:
                return abs(float(value))
            except (TypeError, ValueError):
                continue
    return 0.0


def _tolerance_text(recon: dict) -> str:
    tol = (recon or {}).get("tolerances") or {}
    days = int(tol.get("days") or 0)
    amount = tol.get("amount")
    day_text = "same day" if days == 0 else f"±{plural(days, 'day')}"
    amount_text = f"{float(amount):.2f}" if amount is not None else "1.00"
    return f"Allowance used: dates {day_text}, amounts ₹{amount_text}"


def write_exceptions_workbook(
    path: Path,
    *,
    client_name: str,
    period_label: str,
    recon: dict,
    firm: str = "",
) -> Path:
    rows = _exception_rows(recon)
    book = Workbook()
    sheet = book.active
    sheet.title = "Exceptions"
    block = _header_block("Exceptions only", client_name, period_label, firm)
    identity = block["identity"]
    counts = (recon or {}).get("counts") or {}
    row = cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Exceptions only",
        lines=[block["facts"]],
        entries=[],
        blocks=[
            (
                None,
                [(label, int(counts.get(key) or 0)) for key, label in COUNT_ORDER],
            )
        ],
        notes=[
            _tolerance_text(recon),
            "Every problem row is listed once; clean matches are not included.",
        ],
        legend=(),
        sign_off=False,
        width=len(EXCEPTION_HEADERS),
    )
    for col, header in enumerate(EXCEPTION_HEADERS, start=1):
        put(sheet, row, col, header)
    style_header(sheet, len(EXCEPTION_HEADERS), row, money_cols=(9, 10, 11))
    body_start = row + 1
    for item in rows:
        values = [item.get(key) for key in EXCEPTION_KEYS]
        values[0] = _status_label(item.get("status"))
        for index in EXCEPTION_DATE_COLS:
            values[index - 1] = _date_cell(values[index - 1])
        append_row(sheet, values)
    if not rows:
        append_row(sheet, ["No exceptions this month."])
        style_note(sheet, f"A{sheet.max_row}")
    body_end = max(sheet.max_row, body_start)
    style_body(
        sheet,
        body_start,
        body_end,
        len(EXCEPTION_HEADERS),
        money_cols=(9, 10, 11),
        date_cols=EXCEPTION_DATE_COLS,
        wrap_cols=(2, 16, 17),
        row_height=None,
    )
    for excel_row in range(body_start, body_end + 1):
        mark_exception(sheet, excel_row, 1)
    last_col = get_column_letter(len(EXCEPTION_HEADERS))
    sheet.auto_filter.ref = f"A{row}:{last_col}{body_end}"
    sheet.freeze_panes = f"A{body_start}"
    set_widths(sheet, EXCEPTION_WIDTHS)
    sheet.sheet_view.showGridLines = False
    print_setup(
        sheet,
        len(EXCEPTION_HEADERS),
        header_row=row,
        footer_parts=_footer(identity, "Exceptions only"),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return path


def write_audit_summary(
    path: Path,
    *,
    client_name: str,
    period_label: str,
    recon: dict,
    firm: str = "",
) -> Path:
    rows = _pack_rows(recon)
    exceptions = _exception_rows(recon)
    counts = (recon or {}).get("counts") or {}
    totals = (recon or {}).get("totals") or {}
    decisions = (recon or {}).get("decisions") or {}
    decision_counts = decisions.get("counts") or {}

    book = Workbook()
    sheet = book.active
    sheet.title = "Summary"
    block = _header_block("Reconciliation summary", client_name, period_label, firm)
    identity = block["identity"]

    row = cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Reconciliation summary",
        lines=[block["facts"]],
        entries=[],
        blocks=[
            (
                "How the month stands",
                [(label, int(counts.get(key) or 0)) for key, label in COUNT_ORDER],
            ),
            (
                "Money at stake",
                [
                    (label, float(totals.get(key) or 0) + 0.0)
                    for label, key in MONEY_ORDER
                ],
            ),
            (
                "What the firm decided",
                [
                    ("Rows accepted", int(decision_counts.get("accepted") or 0)),
                    ("Rows rejected", int(decision_counts.get("rejected") or 0)),
                    ("Rows noted", int(decision_counts.get("noted") or 0)),
                    ("Still to decide", int(decision_counts.get("undecided") or 0)),
                    ("New this run", int(decision_counts.get("new") or 0)),
                ],
            ),
        ],
        notes=[
            _tolerance_text(recon),
            "A decision records what the firm chose; it never changes the difference above.",
        ],
        legend=(),
        sign_off=False,
        width=len(DECISION_HEADERS),
    )

    row = cover_heading(sheet, row, "Decision log")
    for col, header in enumerate(DECISION_HEADERS, start=1):
        put(sheet, row, col, header)
    style_header(sheet, len(DECISION_HEADERS), row, money_cols=(4,))
    log_start = row + 1
    decided = [
        item
        for item in exceptions
        if str(item.get("decision") or "") in {"accepted", "rejected", "noted"}
    ]
    for item in decided:
        append_row(
            sheet,
            [
                item.get("gstin"),
                item.get("invoice_books") or item.get("invoice_2b"),
                item.get("party"),
                _row_amount(item),
                item.get("decision_label"),
                item.get("decision_reason"),
                item.get("decision_note"),
                item.get("decision_by"),
                item.get("decision_at"),
            ],
        )
    if not decided:
        append_row(sheet, ["No decisions recorded for this month yet."])
        style_note(sheet, f"A{sheet.max_row}")
    log_end = max(sheet.max_row, log_start)
    style_body(
        sheet,
        log_start,
        log_end,
        len(DECISION_HEADERS),
        money_cols=(4,),
        wrap_cols=(3, 6, 7),
        row_height=None,
    )
    set_widths(sheet, DECISION_WIDTHS)
    sheet.column_dimensions["A"].width = 44
    sheet.column_dimensions["B"].width = 18
    sheet.sheet_view.showGridLines = False
    print_setup(
        sheet,
        len(DECISION_HEADERS),
        header_row=row,
        footer_parts=_footer(identity, "Reconciliation summary"),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return path


def mark_undecided(rows: list[dict]) -> list[dict]:
    """Rows that still need an answer, largest amount first."""
    pending = [row for row in rows if not str(row.get("decision") or "")]
    return sorted(pending, key=_row_amount, reverse=True)


__all__ = [
    "write_exceptions_workbook",
    "write_audit_summary",
    "mark_undecided",
    "EXCEPTION_STATUSES",
    "STATUS_LABELS",
]
