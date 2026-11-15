from __future__ import annotations

import ast
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECON_PY = ROOT / "apps" / "engine" / "recon.py"
GSTIN = "27AAPFU0939F1ZV"
_NETWORK_ROOTS = {"requests", "httpx", "urllib", "aiohttp", "socket", "http"}


def _books(**overrides) -> dict:
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "INV/001",
        "invoice_date": "2026-07-12",
        "invoice_value": 100,
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
        "invoice_value": Decimal("100.40"),
        "trade_name": "Acme Traders",
        "source": "GSTR-2B.json#b2b[0]",
        "document_type": "B2B",
    }
    row.update(overrides)
    return row


def _statuses(result: dict) -> list[str]:
    return [row["status"] for row in result["rows"]]


class ReconMatcherTests(unittest.TestCase):
    def test_matched_same_gstin_normalized_invoice_date_within_rupee(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [_gstr()])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(_statuses(result), ["matched"])
        row = result["rows"][0]
        self.assertEqual(row["invoice_books"], "INV/001")
        self.assertEqual(row["invoice_2b"], "INV-1")

    def test_amount_mismatch_same_key_amounts_far_apart(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(invoice_value=100)], [_gstr(invoice_value=250)])
        self.assertEqual(result["counts"]["amount_mismatch"], 1)
        self.assertEqual(_statuses(result), ["amount_mismatch"])

    def test_portal_only_when_2b_has_no_books(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([], [_gstr()])
        self.assertEqual(result["counts"]["portal_only"], 1)
        self.assertEqual(_statuses(result), ["portal_only"])

    def test_books_only_when_books_has_no_2b(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [])
        self.assertEqual(result["counts"]["books_only"], 1)
        self.assertEqual(_statuses(result), ["books_only"])

    def test_likely_when_invoice_numbers_share_prefix(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_number="AB12")],
            [_gstr(invoice_number="AB12345", invoice_value=100)],
        )
        self.assertEqual(result["counts"]["likely"], 1)
        self.assertEqual(_statuses(result), ["likely"])

    def test_bank_hint_when_debit_matches_within_seven_days(self) -> None:
        from apps.engine.recon import reconcile

        bank = [
            {
                "date": "2026-07-14",
                "description": "NEFT ACME",
                "narration": "NEFT ACME",
                "debit": 100,
                "credit": None,
            }
        ]
        result = reconcile([_books()], [_gstr()], bank)
        self.assertEqual(_statuses(result), ["matched"])
        self.assertTrue(result["rows"][0].get("bank_hint"))

    def test_matched_when_one_date_unparseable(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_date="0142-27-26")],
            [_gstr()],
        )
        self.assertEqual(result["counts"]["matched"], 1)

    def test_different_parseable_dates_are_not_exact_matches(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_date="2026-07-01")],
            [_gstr(invoice_date="12-07-2026")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertNotIn("matched", _statuses(result))

    def test_cdn_2b_row_is_kept_in_its_own_group(self) -> None:
        from apps.engine.recon import reconcile

        cdn = _gstr(document_type="CDNR", invoice_number="CN-9")
        result = reconcile([_books()], [cdn])
        self.assertEqual(result["counts"]["portal_only"], 0)
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["credit_note"], 1)
        self.assertEqual(_statuses(result), ["books_only", "credit_note"])
        self.assertGreater(result["totals"]["credit_note_total"], 0)
        note = next(row for row in result["rows"] if row["status"] == "credit_note")
        self.assertIn("credit is not lost", note["reason"])

    def test_recon_module_has_no_network_imports(self) -> None:
        self.assertTrue(RECON_PY.is_file(), "apps/engine/recon.py missing")
        tree = ast.parse(RECON_PY.read_text(encoding="utf-8"))
        hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = (alias.name or "").split(".", 1)[0]
                    if root in _NETWORK_ROOTS:
                        hits.append(root)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", 1)[0]
                if root in _NETWORK_ROOTS:
                    hits.append(root)
        self.assertEqual(hits, [], f"recon.py must stay offline: {hits}")


class ReconRupeeTotalsTests(unittest.TestCase):
    def test_totals_report_rupees_not_rows(self) -> None:
        from apps.engine.recon import reconcile

        books = [
            _books(),
            _books(invoice_number="INV/002", invoice_value=200, supplier_name="Beta Traders"),
        ]
        gstr = [
            _gstr(invoice_value=100),
            _gstr(invoice_number="INV-2", invoice_value=Decimal("200.00")),
            _gstr(invoice_number="PORTAL-ONLY", invoice_value=Decimal("300.00")),
        ]
        result = reconcile(books, gstr)
        totals = result["totals"]
        self.assertEqual(totals["portal_total"], 600.0)
        self.assertEqual(totals["books_total"], 300.0)
        self.assertEqual(totals["gap"], 300.0)
        self.assertEqual(totals["credit_at_risk"], 300.0)
        self.assertEqual(totals["unsupported_credit"], 0.0)
        self.assertEqual(result["counts"]["matched"], 2)
        self.assertEqual(result["counts"]["portal_only"], 1)

    def test_books_only_credit_is_unsupported_credit(self) -> None:
        from apps.engine.recon import reconcile

        books = [
            _books(),
            _books(
                invoice_number="X-BILL",
                invoice_value=Decimal("500.50"),
                invoice_date="2026-07-14",
                supplier_name="Extra Traders",
            ),
        ]
        result = reconcile(books, [_gstr(invoice_value=100)])
        totals = result["totals"]
        self.assertEqual(totals["portal_total"], 100.0)
        self.assertEqual(totals["books_total"], 600.50)
        self.assertEqual(totals["gap"], -500.50)
        self.assertEqual(totals["credit_at_risk"], 0.0)
        self.assertEqual(totals["unsupported_credit"], 500.50)
        self.assertEqual(result["counts"]["books_only"], 1)

    def test_rows_without_amounts_do_not_break_totals(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([{"supplier_name": "No amount"}], [_gstr(invoice_value=Decimal("75.00"))])
        totals = result["totals"]
        self.assertEqual(totals["portal_total"], 75.0)
        self.assertEqual(totals["books_total"], 0.0)
        self.assertEqual(totals["gap"], 75.0)

    def test_matched_month_totals_to_zero_gap(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [_gstr(invoice_value=Decimal("100.40"))])
        totals = result["totals"]
        self.assertAlmostEqual(round(totals["gap"], 2), 0.40)
        self.assertEqual(totals["credit_at_risk"], 0.0)
        self.assertEqual(totals["unsupported_credit"], 0.0)


class ReconReasonTests(unittest.TestCase):
    def test_amount_mismatch_reason_names_the_difference(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books(invoice_value=100)], [_gstr(invoice_value=250)])
        row = result["rows"][0]
        self.assertIn("differ by 150.00", row["reason"])

    def test_likely_reason_shows_both_invoice_numbers(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_number="AB12")],
            [_gstr(invoice_number="AB12345", invoice_value=100)],
        )
        row = result["rows"][0]
        self.assertEqual(row["status"], "likely")
        self.assertIn("AB12", row["reason"])
        self.assertIn("AB12345", row["reason"])
        self.assertIn("confirm", row["reason"].lower())

    def test_matched_reason_is_plain(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [_gstr()])
        self.assertIn("agree", result["rows"][0]["reason"])

    def test_unmatched_reasons_are_populated(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile([_books()], [])
        self.assertTrue(result["rows"][0]["reason"].strip())

        result = reconcile([], [_gstr()])
        self.assertTrue(result["rows"][0]["reason"].strip())


if __name__ == "__main__":
    unittest.main()
