from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from apps.engine.pack.formatting import (
    guard_sheet_capacity,
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


BANK_NOTE = "Bank hints are an assist only; they are not matches."
MONEY_NOTE = (
    "Rupee figures use the invoice amounts in this grid; bank hints are not included in the difference."
)
MONEY_LABELS = (
    ("On the portal (2B)", "portal_total"),
    ("In the books", "books_total"),
    ("Difference", "gap"),
    ("Credit at risk (portal only)", "credit_at_risk"),
    ("Credit claimed without support (books only)", "unsupported_credit"),
    ("Credit notes (kept separate)", "credit_note_total"),
    ("Same bill from another source (not extra credit)", "same_bill_total"),
)
DECISION_LABELS = (
    ("Rows accepted", "accepted"),
    ("Rows rejected", "rejected"),
    ("Rows noted", "noted"),
    ("Still to decide", "undecided"),
    ("New this run", "new"),
)
DECISION_NOTE = (
    "A decision never changes the difference above; it only records what the firm decided."
)
COUNT_ORDER = (
    ("matched", "Matched"),
    ("books_only", "In the books only"),
    ("portal_only", "On the portal only"),
    ("amount_mismatch", "Amount differs"),
    ("likely", "Likely the same bill"),
    ("tax_mismatch", "Tax differs"),
    ("duplicate", "Duplicate"),
    ("split_merged", "Split or merged"),
    ("credit_note", "Credit notes"),
)
GRID_HEADERS = [
    "Status",
    "Why",
    "Decision",
    "Reason",
    "Note",
    "Decided by",
    "Decided on",
    "GSTIN",
    "Party",
    "Invoice no (2B)",
    "Invoice no (books)",
    "Date (2B)",
    "Date (books)",
    "Amount (2B)",
    "Amount (books)",
    "Amount diff",
    "Taxable (2B)",
    "Taxable (books)",
    "CGST (2B)",
    "CGST (books)",
    "SGST (2B)",
    "SGST (books)",
    "IGST (2B)",
    "IGST (books)",
    "Bank hint",
    "Source (2B)",
    "Source (books)",
]
GRID_KEYS = [
    "status",
    "reason",
    "decision_label",
    "decision_reason",
    "decision_note",
    "decision_by",
    "decision_at",
    "gstin",
    "party",
    "invoice_2b",
    "invoice_books",
    "date_2b",
    "date_books",
    "amount_2b",
    "amount_books",
    "amount_diff",
    "tax_taxable_2b",
    "tax_taxable_books",
    "tax_cgst_2b",
    "tax_cgst_books",
    "tax_sgst_2b",
    "tax_sgst_books",
    "tax_igst_2b",
    "tax_igst_books",
    "bank_hint",
    "source_2b",
    "source_books",
]
MONEY_COLS = (14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24)
DATE_COLS = (12, 13)
WRAP_COLS = (2, 4, 5, 9, 25, 26, 27)
UNMATCHED_STATUSES = {
    "books_only",
    "portal_only",
    "amount_mismatch",
    "likely",
    "tax_mismatch",
    "duplicate",
    "split_merged",
    "credit_note",
}
FLAG_STATUSES = UNMATCHED_STATUSES
WIDTHS = [
    16, 46, 14, 30, 40, 16, 20, 18, 28, 20, 20, 14, 14, 14, 16, 14,
    14, 14, 14, 14, 14, 14, 14, 14,
    28, 28, 28,
]
LEGEND = (
    (
        "Shaded status",
        "That row needs your eye: the Why column says what does not agree.",
    ),
    (
        "Decision",
        "Recorded by the firm; it never changes the amounts above.",
    ),
)


def write_master_grid(
    path: Path, result: dict, identity: dict | None = None
) -> Path:
    rows = list((result or {}).get("rows") or [])
    counts = (result or {}).get("counts") or {}
    totals = (result or {}).get("totals") or {}
    decisions = (result or {}).get("decisions") or {}
    book = Workbook()
    cover = book.active
    cover.title = "Cover"
    identity = cover_identity(identity or {}, result or {}, folder_identity(path))
    unmatched = [row for row in rows if str(row.get("status") or "") in UNMATCHED_STATUSES]
    _write_cover(cover, counts, len(rows), totals, decisions, identity, unmatched)
    _write_table(book.create_sheet("Grid"), rows, identity)
    _write_table(book.create_sheet("Unmatched"), unmatched, identity)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return path


def _write_cover(
    sheet,
    counts: dict,
    row_count: int,
    totals: dict | None,
    decisions: dict | None,
    identity: dict,
    unmatched: list[dict] | None = None,
) -> None:
    facts = [
        identity.get("client") or "",
        identity.get("period") or "",
        plural(row_count, "row"),
        f"generated {identity['generated']}",
    ]
    count_pairs = [(label, int(counts.get(key) or 0)) for key, label in COUNT_ORDER]
    count_pairs.append(("Total rows", row_count))
    money_pairs = [
        (label, float((totals or {}).get(key) or 0) + 0.0) for label, key in MONEY_LABELS
    ]
    decision_counts = (decisions or {}).get("counts") or {}
    decision_pairs = [
        (label, int(decision_counts.get(key) or 0)) for label, key in DECISION_LABELS
    ]
    cover_sheet(
        sheet,
        firm=identity.get("firm") or "",
        title="Master reconciliation",
        lines=["  ·  ".join(part for part in facts if part)],
        entries=[
            (
                "Grid",
                "Every row side by side, with the firm's decision.",
                row_count,
            ),
            (
                "Unmatched",
                "Only the rows that do not agree.",
                len(unmatched or []),
            ),
        ],
        blocks=[
            ("How the month stands", count_pairs),
            ("Money at stake", money_pairs),
            ("What the firm decided", decision_pairs),
        ],
        notes=[DECISION_NOTE, BANK_NOTE, MONEY_NOTE],
        legend=LEGEND,
        width=2,
    )
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 18
    sheet.column_dimensions["C"].width = 8
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    cover_print_setup(
        sheet,
        2,
        footer_parts=[
            identity.get("client") or "",
            identity.get("period") or "",
            "Master reconciliation",
        ],
    )


def _date_cell(value):
    """A real date when the text is unambiguous, otherwise the text as received."""
    if value is None or value == "":
        return value
    parsed = parse_date_value(value)
    return parsed if parsed is not None else value


def _write_table(sheet, rows: list[dict], identity: dict | None = None) -> None:
    guard_sheet_capacity(rows, sheet.title)
    for col, header in enumerate(GRID_HEADERS, start=1):
        put(sheet, 1, col, header)
    style_header(sheet, len(GRID_HEADERS), 1, money_cols=MONEY_COLS)
    flagged: list[int] = []
    for row in rows:
        values = [
            _date_cell(value) if index in DATE_COLS else value
            for index, value in enumerate(
                (row.get(key) for key in GRID_KEYS), start=1
            )
        ]
        append_row(sheet, values)
        if str(row.get("status") or "") in FLAG_STATUSES:
            flagged.append(sheet.max_row)
    if not rows:
        append_row(sheet, ["No rows"])
        style_note(sheet, f"A{sheet.max_row}")
    if sheet.max_row > 1:
        style_body(
            sheet,
            2,
            sheet.max_row,
            len(GRID_HEADERS),
            money_cols=MONEY_COLS,
            date_cols=DATE_COLS,
            wrap_cols=WRAP_COLS,
            row_height=None,
        )
    for excel_row in flagged:
        mark_exception(sheet, excel_row, 1)
    last_col = get_column_letter(len(GRID_HEADERS))
    last_row = max(sheet.max_row, 1)
    sheet.auto_filter.ref = f"A1:{last_col}{last_row}"
    sheet.freeze_panes = "A2"
    set_widths(sheet, WIDTHS)
    footer = identity or {}
    print_setup(
        sheet,
        len(GRID_HEADERS),
        header_row=1,
        footer_parts=[
            footer.get("client") or "",
            footer.get("period") or "",
            f"Master reconciliation — {sheet.title}",
        ],
    )
