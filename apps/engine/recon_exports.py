"""Two audit-friendly files the CA can hand over: exceptions only, and a
one-page summary of what was decided.

Both read the reconciliation block of a finished pack; nothing is re-parsed and
nothing leaves the computer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.style import (
    MONEY_FORMAT,
    print_setup,
    style_body,
    style_count_pairs,
    style_header,
    style_note,
    style_title,
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
)
MONEY_ORDER = (
    ("On the portal (2B)", "portal_total"),
    ("In the books", "books_total"),
    ("Difference", "gap"),
    ("Credit at risk (portal only)", "credit_at_risk"),
    ("Credit claimed without support (books only)", "unsupported_credit"),
    ("Credit notes (kept separate)", "credit_note_total"),
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


def _status_label(value) -> str:
    return STATUS_LABELS.get(str(value or ""), str(value or ""))


def _header_block(sheet, title: str, client_name: str, period_label: str) -> None:
    sheet["A1"] = title
    style_title(sheet, "A1")
    sheet.append([f"Client: {client_name or '-'}   Period: {period_label or '-'}"])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append([f"Prepared {datetime.now().strftime('%d %b %Y, %H:%M')} from the local pack."])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append([])


def _append_pairs(sheet, pairs) -> tuple[int, int]:
    first = sheet.max_row + 1
    for label, value in pairs:
        sheet.append([label, value])
        if isinstance(value, float):
            sheet.cell(sheet.max_row, 2).number_format = MONEY_FORMAT
    return first, sheet.max_row


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
    day_text = "same day" if days == 0 else f"±{days} days"
    amount_text = f"{float(amount):.2f}" if amount is not None else "1.00"
    return f"Allowance used: dates {day_text}, amounts ₹{amount_text}"


def write_exceptions_workbook(
    path: Path,
    *,
    client_name: str,
    period_label: str,
    recon: dict,
) -> Path:
    rows = _exception_rows(recon)
    book = Workbook()
    sheet = book.active
    sheet.title = "Exceptions"
    _header_block(sheet, "Exceptions only", client_name, period_label)
    counts = (recon or {}).get("counts") or {}
    pairs = [(label, int(counts.get(key) or 0)) for key, label in COUNT_ORDER]
    first, last = _append_pairs(sheet, pairs)
    style_count_pairs(sheet, first, last)
    sheet.append([])
    sheet.append([_tolerance_text(recon)])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append(["Every problem row is listed once; clean matches are not included."])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append([])
    sheet.append(EXCEPTION_HEADERS)
    style_header(sheet, len(EXCEPTION_HEADERS))
    body_start = sheet.max_row + 1
    for row in rows:
        values = [row.get(key) for key in EXCEPTION_KEYS]
        values[0] = _status_label(row.get("status"))
        sheet.append(values)
    if not rows:
        sheet.append(["No exceptions this month."])
        style_note(sheet, f"A{sheet.max_row}")
    body_end = max(sheet.max_row, body_start)
    style_body(
        sheet,
        body_start,
        body_end,
        len(EXCEPTION_HEADERS),
        money_cols=(9, 10, 11),
    )
    last_col = get_column_letter(len(EXCEPTION_HEADERS))
    sheet.auto_filter.ref = f"A{body_start - 1}:{last_col}{body_end}"
    sheet.freeze_panes = f"A{body_start}"
    for index, width in enumerate(EXCEPTION_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    print_setup(sheet, len(EXCEPTION_HEADERS), header_row=body_start - 1)
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
    _header_block(sheet, "Reconciliation summary", client_name, period_label)

    sheet.append(["How the month stands"])
    style_header(sheet, 2)
    first, last = _append_pairs(
        sheet, [(label, int(counts.get(key) or 0)) for key, label in COUNT_ORDER]
    )
    style_count_pairs(sheet, first, last)
    sheet.append([])

    sheet.append(["Money at stake"])
    style_header(sheet, 2)
    first, last = _append_pairs(
        sheet,
        [(label, float(totals.get(key) or 0) + 0.0) for label, key in MONEY_ORDER],
    )
    style_count_pairs(sheet, first, last)
    sheet.append([])

    sheet.append(["What the firm decided"])
    style_header(sheet, 2)
    first, last = _append_pairs(
        sheet,
        [
            ("Rows accepted", int(decision_counts.get("accepted") or 0)),
            ("Rows rejected", int(decision_counts.get("rejected") or 0)),
            ("Rows noted", int(decision_counts.get("noted") or 0)),
            ("Still to decide", int(decision_counts.get("undecided") or 0)),
            ("New this run", int(decision_counts.get("new") or 0)),
        ],
    )
    style_count_pairs(sheet, first, last)
    sheet.append([])
    sheet.append([_tolerance_text(recon)])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append([
        "A decision records what the firm chose; it never changes the difference above."
    ])
    style_note(sheet, f"A{sheet.max_row}")
    sheet.append([])

    sheet.append(["Decision log"])
    style_header(sheet, 2)
    sheet.append(DECISION_HEADERS)
    style_header(sheet, len(DECISION_HEADERS))
    log_start = sheet.max_row + 1
    decided = [
        row
        for row in exceptions
        if str(row.get("decision") or "") in {"accepted", "rejected", "noted"}
    ]
    for row in decided:
        sheet.append(
            [
                row.get("gstin"),
                row.get("invoice_books") or row.get("invoice_2b"),
                row.get("party"),
                _row_amount(row),
                row.get("decision_label"),
                row.get("decision_reason"),
                row.get("decision_note"),
                row.get("decision_by"),
                row.get("decision_at"),
            ]
        )
    if not decided:
        sheet.append(["No decisions recorded for this month yet."])
        style_note(sheet, f"A{sheet.max_row}")
    log_end = max(sheet.max_row, log_start)
    style_body(
        sheet,
        log_start,
        log_end,
        len(DECISION_HEADERS),
        money_cols=(4,),
    )
    for index, width in enumerate(DECISION_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.column_dimensions["A"].width = 44
    sheet.column_dimensions["B"].width = 18
    print_setup(sheet, len(DECISION_HEADERS), header_row=log_start - 1)
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
