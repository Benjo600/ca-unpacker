"""Messy real-life cases: credit notes, duplicates, splits, merges, tax gaps.

Each test pins one behaviour from the reconciliation contract, so a failure
here means the engine no longer tells the CA partner the truth about that
case.
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"


def _books(**overrides) -> dict:
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "INV/001",
        "invoice_date": "2026-07-12",
        "invoice_value": Decimal("11800.00"),
        "taxable_value": Decimal("10000.00"),
        "cgst": Decimal("900.00"),
        "sgst": Decimal("900.00"),
        "supplier_name": "Acme Traders",
        "source": "bill.pdf",
    }
    row.update(overrides)
    return row


def _gstr(**overrides) -> dict:
    row = {
        "gstin": GSTIN,
        "invoice_number": "INV-1",
        "invoice_date": "12-07-2026",
        "invoice_value": Decimal("11800.00"),
        "trade_name": "Acme Traders",
        "taxable": Decimal("10000.00"),
        "cgst": Decimal("900.00"),
        "sgst": Decimal("900.00"),
        "source": "GSTR-2B.json#b2b[0]",
        "document_type": "B2B",
    }
    row.update(overrides)
    return row


def _statuses(result: dict) -> list[str]:
    return [row["status"] for row in result["rows"]]


class CreditNoteRowTests(unittest.TestCase):
    def test_credit_note_is_its_own_row_and_leaves_portal_totals_alone(self) -> None:
        from apps.engine.recon import reconcile

        books = [_books()]
        baseline = reconcile(books, [_gstr()])

        cdn = _gstr(
            invoice_number="CN-77",
            document_type="CDNR",
            invoice_value=Decimal("-1180.00"),
            cgst=Decimal("-90.00"),
            sgst=Decimal("-90.00"),
        )
        result = reconcile(books, [_gstr(), cdn])

        self.assertEqual(result["counts"]["credit_note"], 1)
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["counts"]["portal_only"], 0)

        note = next(row for row in result["rows"] if row["status"] == "credit_note")
        self.assertEqual(note["invoice_2b"], "CN-77")
        self.assertEqual(note["amount_2b"], -1180.0)
        self.assertIn("credit is not lost", note["reason"])

        totals = result["totals"]
        self.assertEqual(totals["credit_note_total"], 1180.0)
        # The credit note must not move the money summary or widen the gap.
        self.assertEqual(totals["portal_total"], baseline["totals"]["portal_total"])
        self.assertEqual(totals["books_total"], baseline["totals"]["books_total"])
        self.assertEqual(totals["gap"], baseline["totals"]["gap"])


class DuplicateInvoiceTests(unittest.TestCase):
    def test_second_copy_of_a_books_invoice_is_duplicate_not_books_only(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(), _books()], [_gstr()])

        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertEqual(result["counts"]["books_only"], 0)
        self.assertEqual(sorted(_statuses(result)), ["duplicate", "matched"])

        duplicate = next(row for row in result["rows"] if row["status"] == "duplicate")
        self.assertIn("twice", duplicate["reason"].lower())
        self.assertIn("books", duplicate["reason"].lower())

    def test_same_portal_invoice_twice_both_copies_are_duplicate(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([], [_gstr(), _gstr()])

        self.assertEqual(result["counts"]["portal_only"], 0)
        self.assertEqual(result["counts"]["duplicate"], 2)
        self.assertEqual(_statuses(result), ["duplicate", "duplicate"])

        for row in result["rows"]:
            self.assertEqual(row["status"], "duplicate")
            self.assertIn("2B download", row["reason"])
            self.assertIn("2 times", row["reason"])

    def test_one_invoice_on_each_side_is_not_a_duplicate(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [_gstr()])

        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["counts"]["duplicate"], 0)
        self.assertNotIn("duplicate", _statuses(result))


class SplitAndMergeTests(unittest.TestCase):
    def test_one_books_invoice_split_across_two_portal_lines(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_value=Decimal("11800.00"))],
            [
                _gstr(invoice_value=Decimal("5900.00")),
                _gstr(invoice_value=Decimal("5900.00")),
            ],
        )

        self.assertEqual(result["counts"]["split_merged"], 1)
        self.assertEqual(result["counts"]["portal_only"], 0)
        self.assertEqual(result["counts"]["amount_mismatch"], 0)
        self.assertEqual(_statuses(result), ["split_merged"])

        row = result["rows"][0]
        self.assertEqual(row["amount_2b"], 11800.0)
        self.assertEqual(row["amount_books"], 11800.0)
        self.assertEqual(row["amount_diff"], 0.0)
        self.assertIn("split", row["reason"].lower())

    def test_portal_lines_that_do_not_add_up_stay_portal_only(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_value=Decimal("11800.00"))],
            [
                _gstr(invoice_value=Decimal("5900.00")),
                _gstr(invoice_value=Decimal("4000.00")),
            ],
        )

        self.assertEqual(result["counts"]["split_merged"], 0)
        self.assertEqual(result["counts"]["duplicate"], 0)
        self.assertEqual(result["counts"]["portal_only"], 2)
        self.assertEqual(
            sorted(_statuses(result)), ["books_only", "portal_only", "portal_only"]
        )

    def test_two_books_bills_merged_into_one_portal_line(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [
                _books(invoice_number="BILL/1", invoice_value=Decimal("5000.00")),
                _books(invoice_number="BILL/2", invoice_value=Decimal("4000.00")),
            ],
            [_gstr(invoice_number="INV-1", invoice_value=Decimal("9000.00"))],
        )

        self.assertEqual(result["counts"]["split_merged"], 1)
        self.assertEqual(result["counts"]["books_only"], 0)
        self.assertEqual(result["counts"]["portal_only"], 0)
        self.assertEqual(_statuses(result), ["split_merged"])

        row = result["rows"][0]
        self.assertEqual(row["amount_2b"], 9000.0)
        self.assertEqual(row["invoice_2b"], "INV-1")
        self.assertIn("add up", row["reason"].lower())


class TaxByTaxTests(unittest.TestCase):
    def test_central_tax_gap_is_tax_mismatch_and_names_the_component(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(cgst=Decimal("900.00"))],
            [_gstr(cgst=Decimal("850.00"))],
        )

        self.assertEqual(result["counts"]["tax_mismatch"], 1)
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(_statuses(result), ["tax_mismatch"])

        row = result["rows"][0]
        self.assertIn("central tax", row["reason"])
        self.assertEqual(row["tax_cgst_2b"], 850.0)
        self.assertEqual(row["tax_cgst_books"], 900.0)

    def test_central_tax_gap_within_the_rupee_allowance_stays_matched(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(cgst=Decimal("900.00"))],
            [_gstr(cgst=Decimal("899.50"))],
        )

        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["counts"]["tax_mismatch"], 0)
        self.assertEqual(_statuses(result), ["matched"])

        row = result["rows"][0]
        self.assertEqual(row["tax_cgst_2b"], 899.5)
        self.assertEqual(row["tax_cgst_books"], 900.0)


if __name__ == "__main__":
    unittest.main()
