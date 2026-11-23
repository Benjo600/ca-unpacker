"""Same bill arriving from two book sources must not read as extra credit.

A CA often has the same purchase twice in the books — once in the Tally ledger
("PUR-88") and once in the supplier's invoice PDF ("ACME/26-27/0142") — while
the GST portal carries it once. Before, the second book copy fell through to
``books_only`` and was reported as "credit claimed without support", which
inflates the money at risk for a bill that is fully supported.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"
OTHER_GSTIN = "29AADCH8449J1Z0"


def _books(**overrides) -> dict:
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "ACME/26-27/0142",
        "invoice_date": "2026-07-12",
        "invoice_value": 11800,
        "supplier_name": "Acme Traders",
        "source": "Tax_Invoice_Acme.pdf",
    }
    row.update(overrides)
    return row


def _tally(**overrides) -> dict:
    row = _books(invoice_number="PUR-88", source="Tally_Daybook.xml")
    row.update(overrides)
    return row


def _gstr(**overrides) -> dict:
    row = {
        "gstin": GSTIN,
        "invoice_number": "ACME/26-27/0142",
        "invoice_date": "12-07-2026",
        "invoice_value": 11800,
        "trade_name": "Acme Traders",
        "source": "GSTR-2B_July.json#b2b[0]",
        "document_type": "B2B",
    }
    row.update(overrides)
    return row


class SameBillAcrossSourcesTests(unittest.TestCase):
    def test_second_book_copy_is_not_unsupported_credit(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(), _tally()], [_gstr()])
        counts = result["counts"]

        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["same_bill"], 1)
        self.assertEqual(counts["books_only"], 0)
        totals = result["totals"]
        self.assertEqual(totals["unsupported_credit"], 0)
        # One bill recorded in two book sources is still one bill.
        self.assertEqual(totals["books_total"], 11800.0)
        self.assertEqual(totals["same_bill_total"], 11800.0)
        self.assertEqual(totals["gap"], 0.0)

    def test_same_bill_row_explains_itself(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(), _tally()], [_gstr()])
        row = next(row for row in result["rows"] if row["status"] == "same_bill")
        self.assertEqual(row["invoice_books"], "PUR-88")
        self.assertIn("ACME/26-27/0142", row["reason"])
        self.assertIn("same bill", row["reason"].lower())

    def test_different_amount_is_still_books_only(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(), _tally(invoice_value=9500)], [_gstr()])
        self.assertEqual(result["counts"]["same_bill"], 0)
        self.assertEqual(result["counts"]["books_only"], 1)
        self.assertEqual(result["totals"]["unsupported_credit"], 9500.0)

    def test_different_supplier_is_still_books_only(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(), _tally(supplier_gstin=OTHER_GSTIN, supplier_name="Other Traders")],
            [_gstr()],
        )
        self.assertEqual(result["counts"]["same_bill"], 0)
        self.assertEqual(result["counts"]["books_only"], 1)

    def test_two_separate_portal_lines_still_match_one_each(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(), _tally(invoice_number="PUR-89")],
            [_gstr(), _gstr(invoice_number="PUR-89", invoice_value=11800)],
        )
        self.assertEqual(result["counts"]["matched"], 2)
        self.assertEqual(result["counts"]["same_bill"], 0)


if __name__ == "__main__":
    unittest.main()
