from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TAX_HEADERS = [
    "Taxable (2B)",
    "Taxable (books)",
    "CGST (2B)",
    "CGST (books)",
    "SGST (2B)",
    "SGST (books)",
    "IGST (2B)",
    "IGST (books)",
]
COUNT_LABELS = [
    "matched",
    "books_only",
    "portal_only",
    "amount_mismatch",
    "likely",
    "Tax differs",
    "Duplicate",
    "Split or merged",
    "Credit notes",
]
NEW_STATUSES = [
    "tax_mismatch",
    "duplicate",
    "split_merged",
    "credit_note",
]
MONEY_LABELS = [
    "On the portal (2B)",
    "In the books",
    "Difference",
    "Credit at risk (portal only)",
    "Credit claimed without support (books only)",
    "Credit notes (kept separate)",
]
TAX_MISMATCH_TAX = {
    "tax_taxable_2b": 10000.0,
    "tax_taxable_books": 10000.0,
    "tax_cgst_2b": 900.0,
    "tax_cgst_books": 850.0,
    "tax_sgst_2b": 900.0,
    "tax_sgst_books": 850.0,
    "tax_igst_2b": 0.0,
    "tax_igst_books": 0.0,
}


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


def _rows() -> list[dict]:
    return [
        _row(
            "matched",
            "Supplier, invoice number, date and amount all agree.",
            invoice_2b="INV/1001",
            invoice_books="INV/1001",
            amount_2b=1180.0,
            amount_books=1180.0,
            amount_diff=0.0,
            **TAX_MISMATCH_TAX,
        ),
        _row(
            "tax_mismatch",
            "Supplier, invoice, date and total agree, but central tax differs by 50.00.",
            invoice_2b="INV/1002",
            invoice_books="INV/1002",
            amount_2b=1170.0,
            amount_books=1170.0,
            amount_diff=0.0,
            **TAX_MISMATCH_TAX,
        ),
        _row(
            "duplicate",
            "This invoice appears 3 times on the portal.",
            invoice_2b="INV/1003",
            amount_2b=590.0,
        ),
        _row(
            "split_merged",
            "This invoice is split across 2 portal lines that add up to one bill.",
            invoice_2b="INV/1004",
            invoice_books="INV/1004",
            amount_2b=2360.0,
            amount_books=2360.0,
            amount_diff=0.0,
        ),
        _row(
            "credit_note",
            "The credit is kept on its own so it never hides a purchase.",
            invoice_2b="CN/9001",
            amount_2b=-590.0,
        ),
    ]


def _result(with_summaries: bool = True) -> dict:
    result: dict = {
        "rows": _rows(),
        "counts": {
            "matched": 1,
            "books_only": 0,
            "portal_only": 0,
            "amount_mismatch": 0,
            "likely": 0,
            "tax_mismatch": 1,
            "duplicate": 1,
            "split_merged": 1,
            "credit_note": 1,
        },
    }
    if with_summaries:
        result["totals"] = {
            "portal_total": 5300.0,
            "books_total": 4710.0,
            "gap": 590.0,
            "credit_at_risk": 0.0,
            "unsupported_credit": 0.0,
            "credit_note_total": 590.0,
        }
        result["decisions"] = {
            "counts": {
                "accepted": 1,
                "rejected": 0,
                "noted": 1,
                "undecided": 3,
                "new": 2,
                "exceptions": 4,
            },
            "money": {
                "accepted": 1180.0,
                "rejected": 0.0,
                "noted": 590.0,
                "undecided": 3530.0,
                "at_stake": 5300.0,
            },
            "by_reason": {"tax_difference": 1},
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


def _cover_labels(book) -> list[str]:
    labels: list[str] = []
    for row in book["Cover"].iter_rows(values_only=True):
        if not row:
            continue
        label = _text(row[0])
        if label:
            labels.append(label)
    return labels


def _headers(sheet) -> list[str]:
    return [_text(cell.value) for cell in sheet[1]]


def _column_map(sheet) -> dict[str, int]:
    return {name: index + 1 for index, name in enumerate(_headers(sheet))}


def _last_col(sheet) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(sheet.max_column)


class ReconMessyPackTests(unittest.TestCase):
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

    # --- cover ------------------------------------------------------------
    def test_cover_lists_every_status_count_in_order(self) -> None:
        book = self._load(self._write(_result()))
        pairs = _cover_pairs(book)
        expected = {
            "matched": 1,
            "books_only": 0,
            "portal_only": 0,
            "amount_mismatch": 0,
            "likely": 0,
            "Tax differs": 1,
            "Duplicate": 1,
            "Split or merged": 1,
            "Credit notes": 1,
        }
        for label in COUNT_LABELS:
            self.assertIn(label, pairs, label)
        for label, value in expected.items():
            self.assertEqual(int(pairs[label] or 0), value, label)
        self.assertEqual(int(pairs["Total rows"]), 5)

        labels = _cover_labels(book)
        positions = [labels.index(label) for label in COUNT_LABELS]
        self.assertEqual(positions, sorted(positions), "count block must keep its order")
        self.assertGreater(labels.index("Total rows"), positions[-1])

    def test_cover_has_credit_note_rupee_line_below_the_old_five(self) -> None:
        book = self._load(self._write(_result()))
        pairs = _cover_pairs(book)
        for label in MONEY_LABELS:
            self.assertIn(label, pairs, label)
        self.assertEqual(float(pairs["Credit notes (kept separate)"] or 0), 590.0)
        labels = _cover_labels(book)
        positions = [labels.index(label) for label in MONEY_LABELS]
        self.assertEqual(positions, sorted(positions), "rupee block must keep its order")

    def test_cover_keeps_decision_block_below_the_rupee_block(self) -> None:
        book = self._load(self._write(_result()))
        pairs = _cover_pairs(book)
        labels = _cover_labels(book)
        self.assertEqual(int(pairs["Rows accepted"] or 0), 1)
        self.assertEqual(int(pairs["Rows noted"] or 0), 1)
        self.assertEqual(int(pairs["Still to decide"] or 0), 3)
        self.assertEqual(int(pairs["New this run"] or 0), 2)
        self.assertGreater(
            labels.index("Rows accepted"),
            labels.index("Credit notes (kept separate)"),
        )

    # --- grid -------------------------------------------------------------
    def test_grid_header_order_around_amount_diff_and_tax_columns(self) -> None:
        from apps.engine.pack.recon_xlsx import GRID_HEADERS, GRID_KEYS, MONEY_COLS, WIDTHS

        self.assertEqual(len(GRID_HEADERS), len(GRID_KEYS))
        self.assertEqual(len(GRID_HEADERS), len(WIDTHS))
        book = self._load(self._write(_result()))
        for sheet_name in ("Grid", "Unmatched"):
            headers = _headers(book[sheet_name])
            self.assertEqual(headers, GRID_HEADERS, sheet_name)
            diff_at = headers.index("Amount diff")
            self.assertEqual(headers[diff_at + 1 : diff_at + 9], TAX_HEADERS, sheet_name)
            self.assertEqual(headers[diff_at + 9], "Bank hint", sheet_name)
            self.assertEqual(headers[:2], ["Status", "Why"], sheet_name)
            self.assertEqual(
                headers[2:7],
                ["Decision", "Reason", "Note", "Decided by", "Decided on"],
                sheet_name,
            )
            self.assertEqual(headers[-1], "Source (books)", sheet_name)
        first_tax = GRID_HEADERS.index("Taxable (2B)") + 1
        for offset in range(8):
            self.assertIn(first_tax + offset, MONEY_COLS)

    def test_grid_writes_tax_values_and_money_format(self) -> None:
        from apps.engine.pack.style import MONEY_FORMAT

        book = self._load(self._write(_result()))
        sheet = book["Grid"]
        col = _column_map(sheet)
        status_col = col["Status"]
        target_row = None
        for row in range(2, sheet.max_row + 1):
            if _text(sheet.cell(row, status_col).value) == "tax_mismatch":
                target_row = row
                break
        self.assertIsNotNone(target_row, "tax_mismatch row missing from grid")
        assert target_row is not None
        for expected, header in zip(
            [
                10000.0,
                10000.0,
                900.0,
                850.0,
                900.0,
                850.0,
                0.0,
                0.0,
            ],
            TAX_HEADERS,
        ):
            cell = sheet.cell(target_row, col[header])
            self.assertAlmostEqual(float(cell.value or 0), expected, places=2, msg=header)
            self.assertEqual(cell.number_format, MONEY_FORMAT, header)

    def test_rows_without_tax_keys_still_write_blank_tax_cells(self) -> None:
        book = self._load(self._write(_result()))
        sheet = book["Grid"]
        col = _column_map(sheet)
        status_col = col["Status"]
        for row in range(2, sheet.max_row + 1):
            status = _text(sheet.cell(row, status_col).value)
            if status not in {"duplicate", "split_merged", "credit_note"}:
                continue
            for header in TAX_HEADERS:
                self.assertIn(sheet.cell(row, col[header]).value, (None, ""), f"{status}/{header}")

    # --- unmatched --------------------------------------------------------
    def test_unmatched_sheet_holds_every_non_matched_status(self) -> None:
        book = self._load(self._write(_result()))
        sheet = book["Unmatched"]
        col = _column_map(sheet)
        statuses = [
            _text(sheet.cell(row, col["Status"]).value)
            for row in range(2, sheet.max_row + 1)
        ]
        for status in NEW_STATUSES:
            self.assertIn(status, statuses)
        self.assertNotIn("matched", statuses)
        self.assertEqual(len(statuses), 4)
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, f"A1:{_last_col(sheet)}{sheet.max_row}")

    def test_unmatched_rows_carry_red_fill(self) -> None:
        from apps.engine.pack.style import RED_BG

        book = self._load(self._write(_result()))
        for sheet_name in ("Grid", "Unmatched"):
            sheet = book[sheet_name]
            status_col = _column_map(sheet)["Status"]
            for row in range(2, sheet.max_row + 1):
                status = _text(sheet.cell(row, status_col).value)
                fill = sheet.cell(row, 1).fill
                self.assertIsNotNone(fill, f"{sheet_name} row {row}")
                if status == "matched":
                    self.assertNotEqual(
                        str(fill.fgColor.rgb)[-6:], RED_BG, f"{sheet_name} row {row}"
                    )
                else:
                    self.assertEqual(
                        str(fill.fgColor.rgb)[-6:], RED_BG, f"{sheet_name}/{status} row {row}"
                    )

    # --- tolerance --------------------------------------------------------
    def test_works_without_totals_or_decisions_keys(self) -> None:
        path = self._write(_result(with_summaries=False), name="bare.xlsx")
        book = self._load(path)
        pairs = _cover_pairs(book)
        for label in MONEY_LABELS:
            self.assertIn(label, pairs, label)
            self.assertEqual(float(pairs[label] or 0), 0.0, label)
        for label in ("Rows accepted", "New this run"):
            self.assertIn(label, pairs, label)
            self.assertEqual(int(pairs[label] or 0), 0, label)
        self.assertEqual(int(pairs["Total rows"]), 5)
        self.assertEqual(_headers(book["Grid"]), _headers(book["Unmatched"]))
        self.assertEqual(book["Grid"].max_row, 6)


if __name__ == "__main__":
    unittest.main()
