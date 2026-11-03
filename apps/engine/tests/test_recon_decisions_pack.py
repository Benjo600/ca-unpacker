from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DECISION_HEADERS = ["Decision", "Reason", "Note", "Decided by", "Decided on"]
COVER_LABELS = [
    "Rows accepted",
    "Rows rejected",
    "Rows noted",
    "Still to decide",
    "New this run",
]


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _row(status: str, reason: str, **overrides) -> dict:
    row = {
        "row_key": "",
        "status": status,
        "reason": reason,
        "decision": "",
        "decision_label": "Not decided",
        "decision_reason_code": "",
        "decision_reason": "",
        "decision_note": "",
        "decision_by": "",
        "decision_at": "",
        "needs_decision": True,
        "is_new": False,
        "gstin": "27AAPFU0939F1ZV",
        "party": "Acme Traders",
        "invoice_2b": "",
        "invoice_books": "",
        "date_2b": "",
        "date_books": "",
        "amount_2b": None,
        "amount_books": None,
        "amount_diff": None,
        "bank_hint": "",
        "source_2b": "",
        "source_books": "",
    }
    row.update(overrides)
    return row


def _result(with_decisions: bool = True) -> dict:
    rows = [
        _row(
            "books_only",
            "In the books only",
            row_key="key-accepted",
            decision="accepted",
            decision_label="Accepted",
            decision_reason_code="rate_difference",
            decision_reason="Rate difference agreed",
            decision_note="Supplier confirmed the rate",
            decision_by="Benny",
            decision_at="2026-11-03T10:15:00",
            is_new=True,
            invoice_books="INV/001",
            amount_books=1180.0,
        ),
        _row(
            "amount_mismatch",
            "Amount differs",
            row_key="key-rejected",
            decision="rejected",
            decision_label="Rejected",
            decision_reason_code="rate_difference",
            decision_reason="Rate difference not agreed",
            decision_note="Credit note expected",
            decision_by="Benny",
            decision_at="2026-11-03T10:20:00",
            invoice_2b="INV-1",
            invoice_books="INV/001",
            amount_2b=1250.0,
            amount_books=1180.0,
            amount_diff=-70.0,
        ),
        _row(
            "portal_only",
            "On the portal only",
            row_key="key-undecided",
            is_new=True,
            invoice_2b="INV-1",
            amount_2b=1250.0,
        ),
    ]
    result = {
        "rows": rows,
        "counts": {
            "matched": 0,
            "books_only": 1,
            "portal_only": 1,
            "amount_mismatch": 1,
            "likely": 0,
        },
        "totals": {
            "portal_total": 1250.0,
            "books_total": 1180.0,
            "gap": -70.0,
            "credit_at_risk": 1250.0,
            "unsupported_credit": 1180.0,
        },
    }
    if with_decisions:
        result["decisions"] = {
            "counts": {
                "accepted": 1,
                "rejected": 1,
                "noted": 0,
                "undecided": 1,
                "new": 2,
                "exceptions": 3,
            },
            "money": {
                "accepted": 1180.0,
                "rejected": 70.0,
                "noted": 0.0,
                "undecided": 1250.0,
                "at_stake": 2430.0,
            },
            "by_reason": {"rate_difference": 2},
        }
    return result


def _cover_pairs(book) -> dict[str, object]:
    sheet = book["Cover"]
    pairs: dict[str, object] = {}
    for row in sheet.iter_rows(values_only=True):
        if not row:
            continue
        label = _text(row[0])
        if not label or label in pairs:
            continue
        pairs[label] = row[1] if len(row) > 1 else None
    return pairs


def _last_col(sheet) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(sheet.max_column)


class ReconDecisionsPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, result: dict, name: str = "master.xlsx") -> Path:
        from apps.engine.pack.recon_xlsx import write_master_grid

        return write_master_grid(self.tmp_path / name, result)

    def _load(self, path: Path):
        from openpyxl import load_workbook

        return load_workbook(path)

    def test_decision_headers_follow_why_on_grid_and_unmatched(self) -> None:
        book = self._load(self._write(_result()))
        for sheet_name in ("Grid", "Unmatched"):
            headers = [_text(cell.value) for cell in book[sheet_name][1]]
            self.assertEqual(headers[:2], ["Status", "Why"], sheet_name)
            self.assertEqual(headers[2:7], DECISION_HEADERS, sheet_name)
            self.assertEqual(headers[7], "GSTIN", sheet_name)
            self.assertEqual(headers[-1], "Source (books)", sheet_name)

    def test_decision_cells_hold_remembered_values(self) -> None:
        book = self._load(self._write(_result()))
        sheet = book["Grid"]
        headers = [_text(cell.value) for cell in sheet[1]]
        col = {name: index + 1 for index, name in enumerate(headers)}
        values = {
            _text(sheet.cell(row, col["Status"]).value): [
                _text(sheet.cell(row, col[name]).value) for name in DECISION_HEADERS
            ]
            for row in range(2, sheet.max_row + 1)
        }
        self.assertEqual(
            values["books_only"],
            ["Accepted", "Rate difference agreed", "Supplier confirmed the rate", "Benny", "2026-11-03T10:15:00"],
        )
        self.assertEqual(
            values["amount_mismatch"],
            ["Rejected", "Rate difference not agreed", "Credit note expected", "Benny", "2026-11-03T10:20:00"],
        )
        self.assertEqual(values["portal_only"], ["Not decided", "", "", "", ""])

    def test_cover_shows_decision_counts_block(self) -> None:
        book = self._load(self._write(_result()))
        pairs = _cover_pairs(book)
        expected = {
            "Rows accepted": 1,
            "Rows rejected": 1,
            "Rows noted": 0,
            "Still to decide": 1,
            "New this run": 2,
        }
        for label, value in expected.items():
            self.assertIn(label, pairs)
            self.assertEqual(int(pairs[label]), value, label)
        self.assertIn("Total rows", pairs)
        self.assertEqual(int(pairs["Total rows"]), 3)
        self.assertIn("Difference", pairs)
        self.assertEqual(float(pairs["Difference"]), -70.0)

    def test_cover_note_explains_decisions_do_not_move_the_difference(self) -> None:
        book = self._load(self._write(_result()))
        blob = " ".join(
            _text(cell)
            for row in book["Cover"].iter_rows(values_only=True)
            for cell in row
            if cell is not None
        )
        self.assertIn(
            "A decision never changes the difference above; it only records what the firm decided.",
            blob,
        )

    def test_missing_decisions_summary_still_writes_and_shows_zeros(self) -> None:
        path = self._write(_result(with_decisions=False), name="no-summary.xlsx")
        book = self._load(path)
        headers = [_text(cell.value) for cell in book["Grid"][1]]
        self.assertEqual(headers[2:7], DECISION_HEADERS)
        pairs = _cover_pairs(book)
        for label in COVER_LABELS:
            self.assertIn(label, pairs)
            self.assertEqual(int(pairs[label] or 0), 0, label)

    def test_flagged_rows_keep_red_fill_and_freeze_panes(self) -> None:
        from apps.engine.pack.style import RED_BG

        book = self._load(self._write(_result()))
        sheet = book["Grid"]
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, f"A1:{_last_col(sheet)}{sheet.max_row}")
        for row in range(2, sheet.max_row + 1):
            fill = sheet.cell(row, 1).fill
            self.assertIsNotNone(fill)
            self.assertEqual(str(fill.fgColor.rgb)[-6:], RED_BG, f"row {row}")


if __name__ == "__main__":
    unittest.main()
