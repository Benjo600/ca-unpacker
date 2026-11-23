"""Inferred bank rows must be marked and kept out of the approved totals.

A row that is invented to bridge a gap in the running balance is not a
transaction from the statement. It may be kept, but only as something the CA
has to approve on purpose.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook


def _txn(day: str, description: str, debit: float | None, credit: float | None, balance: float) -> dict:
    return {
        "date": day,
        "description": description,
        "cheque_ref": None,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "source_page": 1,
        "source_bbox": "0,0,1,1",
        "source": "statement.pdf#p1@0,0,1,1",
        "raw_text": "",
        "flags": [],
    }


class InferredRowMarkingTests(unittest.TestCase):
    def test_inferred_row_asks_for_approval(self) -> None:
        from apps.engine.parsers.bank.parser import _implied_gap_row

        row = _txn("2026-07-05", "UPI payment", None, 4000.0, 4011.71)
        inferred = _implied_gap_row(row, Decimal("12761.71"))

        self.assertIsNotNone(inferred)
        assert inferred is not None
        self.assertTrue(inferred.get("needs_approval"))
        self.assertEqual(inferred.get("approval"), "pending")
        self.assertIn("inferred_from_balance", inferred.get("flags") or [])
        self.assertIn("not in the statement", inferred["description"].lower())


class PendingApprovalSheetTests(unittest.TestCase):
    def _files(self, rows_one: list[dict]) -> list[dict]:
        return [
            {
                "meta": {"filename": "statement.pdf"},
                "rows": rows_one,
                "currency": {"code": "INR", "source": "stated"},
                "check": {
                    "status": "unverified",
                    "row_count": len(rows_one),
                    "opening_balance": None,
                    "stated_closing": None,
                    "computed_closing": None,
                    "broken_at_row": None,
                    "flags": [],
                },
            }
        ]

    def test_pack_puts_inferred_rows_on_their_own_sheet(self) -> None:
        from apps.engine.pack.bank_xlsx import write_bank_workbook

        approved = _txn("2026-07-05", "UPI payment", None, 4000.0, 4011.71)
        inferred = _txn("2026-07-05", "Inferred from the balance gap — not in the statement", 3800.0, None, 211.71)
        inferred["flags"] = ["inferred_from_balance"]
        inferred["needs_approval"] = True
        inferred["approval"] = "pending"

        with tempfile.TemporaryDirectory() as folder:
            path = write_bank_workbook(Path(folder) / "pack.xlsx", self._files([approved, inferred]))
            book = load_workbook(path)
            approve_sheets = [name for name in book.sheetnames if "approve" in name.lower()]
            self.assertEqual(len(approve_sheets), 1, book.sheetnames)
            sheet = book[approve_sheets[0]]
            text = " ".join(str(cell.value or "") for row in sheet.iter_rows() for cell in row)
            self.assertIn("not in the statement", text.lower())
            self.assertIn("approve", text.lower())

    def test_pack_without_inferred_rows_has_no_approval_sheet(self) -> None:
        from apps.engine.pack.bank_xlsx import write_bank_workbook

        approved = _txn("2026-07-05", "UPI payment", None, 4000.0, 4011.71)
        with tempfile.TemporaryDirectory() as folder:
            path = write_bank_workbook(Path(folder) / "pack.xlsx", self._files([approved]))
            book = load_workbook(path)
            self.assertEqual(
                [name for name in book.sheetnames if "approve" in name.lower()], []
            )


if __name__ == "__main__":
    unittest.main()
