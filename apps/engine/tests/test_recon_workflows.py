from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"
OTHER_GSTIN = "29ABCDE1234F1Z5"


def _invoice(**overrides) -> dict:
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "INV/001",
        "invoice_date": "2026-07-12",
        "taxable_value": 1000,
        "tax": 180,
        "invoice_value": 1180,
        "supplier_name": "Acme Traders",
        "source": "bill.pdf",
    }
    row.update(overrides)
    return row


def _register(**overrides) -> dict:
    row = {
        "gstin": GSTIN,
        "invoice_number": "INV-1",
        "invoice_date": "2026-07-12",
        "taxable_value": 1000,
        "tax": 180,
        "amount": 1180,
        "party_name": "Acme Traders",
        "voucher_type": "Purchase",
        "source": "Tally.xml",
    }
    row.update(overrides)
    return row


def _bank(**overrides) -> dict:
    row = {
        "date": "2026-07-14",
        "description": "NEFT ACME TRADERS INV/001",
        "debit": 1180,
        "credit": None,
        "source": "HDFC.pdf",
    }
    row.update(overrides)
    return row


def _ledger(**overrides) -> dict:
    row = {
        "date": "2026-07-12",
        "invoice_number": "INV/001",
        "party_name": "Acme Traders",
        "amount": 1180,
        "voucher_type": "Payment",
        "source": "Tally.xml",
    }
    row.update(overrides)
    return row


def _statuses(result: dict) -> list[str]:
    return [row["status"] for row in result["rows"]]


class GenericRecordMatcherTests(unittest.TestCase):
    def test_matched_on_gstin_invoice_number_and_amount(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records([_invoice()], [_register()])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(_statuses(result), ["matched"])
        self.assertEqual(result["rows"][0]["left"]["reference"], "INV/001")
        self.assertEqual(result["rows"][0]["right"]["reference"], "INV-1")

    def test_amount_difference_is_reported(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records([_invoice()], [_register(amount=1200)])
        self.assertEqual(result["counts"]["amount_mismatch"], 1)
        row = result["rows"][0]
        self.assertEqual(row["status"], "amount_mismatch")
        self.assertAlmostEqual(row["differences"]["amount"], 20.0)

    def test_missing_records_are_kept_on_each_side(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records([_invoice()], [])
        self.assertEqual(result["counts"]["left_only"], 1)
        result = compare_records([], [_register()])
        self.assertEqual(result["counts"]["right_only"], 1)

    def test_tax_difference_is_a_review_not_a_silent_match(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records([_invoice(tax=180)], [_register(tax=200)])
        self.assertEqual(result["counts"]["review_required"], 1)
        self.assertEqual(result["rows"][0]["reason_code"], "tax_differs")

    def test_duplicate_reference_is_not_paired_arbitrarily(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records(
            [_invoice(), _invoice(source="bill-copy.pdf")],
            [_register()],
        )
        self.assertEqual(result["counts"]["duplicate"], 3)
        self.assertTrue(
            all(row["status"] == "duplicate" for row in result["rows"])
        )

    def test_amount_only_is_never_an_automatic_match(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records(
            [_invoice(gstin=GSTIN, supplier_gstin=GSTIN, party_name="Alpha")],
            [
                _register(
                    gstin=OTHER_GSTIN,
                    invoice_number="OTHER-9",
                    party_name="Beta",
                    amount=1180,
                )
            ],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["left_only"], 1)
        self.assertEqual(result["counts"]["right_only"], 1)

    def test_shared_invoice_prefix_requires_review(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records(
            [_invoice(invoice_number="AB12")],
            [_register(invoice_number="AB12345")],
        )
        self.assertEqual(result["counts"]["review_required"], 1)
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["rows"][0]["reason_code"], "reference_prefix")

    def test_different_currencies_are_not_silently_matched(self) -> None:
        from apps.engine.recon import compare_records

        result = compare_records(
            [_invoice(currency_code="USD")],
            [_register(currency_code="INR")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["review_required"], 1)
        self.assertEqual(result["rows"][0]["reason_code"], "currency_differs")


class BankLedgerMatcherTests(unittest.TestCase):
    def test_reference_and_amount_match_bank_line_to_voucher(self) -> None:
        from apps.engine.recon import compare_bank_ledger

        result = compare_bank_ledger([_bank()], [_ledger()])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["rows"][0]["status"], "matched")

    def test_reference_with_different_amount_is_a_mismatch(self) -> None:
        from apps.engine.recon import compare_bank_ledger

        result = compare_bank_ledger([_bank(debit=1100)], [_ledger(amount=1180)])
        self.assertEqual(result["counts"]["amount_mismatch"], 1)
        row = result["rows"][0]
        self.assertEqual(row["status"], "amount_mismatch")
        self.assertAlmostEqual(row["differences"]["amount"], 80.0)

    def test_amount_only_bank_line_is_not_matched(self) -> None:
        from apps.engine.recon import compare_bank_ledger

        result = compare_bank_ledger(
            [_bank(description="CASH WITHDRAWAL")],
            [_ledger(invoice_number="SOMETHING-ELSE")],
        )
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["left_only"], 1)
        self.assertEqual(result["counts"]["right_only"], 1)

    def test_amount_date_and_party_without_reference_requires_review(self) -> None:
        from apps.engine.recon import compare_bank_ledger

        result = compare_bank_ledger(
            [_bank(description="NEFT ACME TRADERS")],
            [_ledger(invoice_number="UNRELATED")],
        )
        self.assertEqual(result["counts"]["review_required"], 1)
        self.assertEqual(result["rows"][0]["reason_code"], "bank_fuzzy")


class ReconWorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

        from apps.engine.db import reset_engine

        reset_engine()
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        client = create_client("Acme")
        self.period = create_period(client["id"], "Jul 2026")
        from apps.engine.dump import start_job

        self.job = start_job(self.period["id"])

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def _add_file(self, name: str, kind: str, outcome: str = "processed") -> int:
        from apps.engine.db import StoredFile, get_session

        session = get_session()
        try:
            stored = StoredFile(
                job_id=self.job["id"],
                period_id=self.period["id"],
                original_name=name,
                mime="application/pdf",
                size=10,
                storage_key=f"{self.period['id']}/{name}",
                detected_kind=kind,
                confidence=1.0,
                classify_reason="",
                parse_outcome=outcome,
                parse_row_count=1,
            )
            session.add(stored)
            session.commit()
            session.refresh(stored)
            return stored.id
        finally:
            session.close()

    def _add_row(self, file_id: int, kind: str, payload: dict) -> None:
        from apps.engine.db import ExtractedRow, get_session

        session = get_session()
        try:
            session.add(
                ExtractedRow(
                    file_id=file_id,
                    period_id=self.period["id"],
                    kind=kind,
                    payload_json=json.dumps(payload),
                    source_page=1,
                    source_bbox="1,2,3,4",
                    validation_flags="[]",
                )
            )
            session.commit()
        finally:
            session.close()

    def test_missing_comparison_input_is_explained_not_faked(self) -> None:
        file_id = self._add_file("GSTR-2B_July.json", "gstr_2b")
        self._add_row(
            file_id,
            "gstr_2b",
            {
                "gstin": GSTIN,
                "invoice_number": "INV/001",
                "invoice_date": "12-07-2026",
                "invoice_value": 1180,
                "taxable": 1000,
                "source": "GSTR-2B_July.json#b2b[0]",
                "document_type": "B2B",
            },
        )

        from apps.engine.recon_workflows import (
            reconciliation_workspace,
            run_reconciliation,
        )

        workspace = reconciliation_workspace()
        period = workspace["periods"][0]
        flow = next(
            item for item in period["workflows"] if item["id"] == "gst_2b_invoices"
        )
        self.assertFalse(flow["available"])
        self.assertEqual(flow["missing"], ["Purchase invoices"])

        result = run_reconciliation(self.period["id"], "gst_2b_invoices")
        self.assertFalse(result["available"])
        self.assertIn("Purchase invoices", result["message"])
        self.assertNotIn("rows", result)

    def test_run_returns_real_counts_totals_and_source_rows(self) -> None:
        gstr_file = self._add_file("GSTR-2B_July.json", "gstr_2b")
        self._add_row(
            gstr_file,
            "gstr_2b",
            {
                "gstin": GSTIN,
                "invoice_number": "INV/001",
                "invoice_date": "12-07-2026",
                "invoice_value": 1180,
                "taxable": 1000,
                "source": "GSTR-2B_July.json#b2b[0]",
                "document_type": "B2B",
            },
        )
        invoice_file = self._add_file("Acme_Invoice.pdf", "invoice")
        self._add_row(invoice_file, "invoice", _invoice())
        self._add_row(
            invoice_file,
            "invoice",
            {
                "invoice_number": "INV/001",
                "description": "Professional fees",
                "amount": 1180,
            },
        )

        from apps.engine.recon_workflows import run_reconciliation

        result = run_reconciliation(self.period["id"], "gst_2b_invoices")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["counts"]["right_only"], 0)
        self.assertEqual(result["totals"]["left_amount"], 1180.0)
        self.assertEqual(result["totals"]["right_amount"], 1180.0)
        row = result["rows"][0]
        self.assertEqual(row["left"]["file_name"], "GSTR-2B_July.json")
        self.assertEqual(row["right"]["file_name"], "Acme_Invoice.pdf")
        self.assertTrue(row["left"]["row_id"])
        self.assertTrue(row["right"]["row_id"])

    def test_dashboard_uses_persisted_file_outcomes(self) -> None:
        self._add_file("Bank_July.pdf", "bank", "processed")
        self._add_file("Unknown.pdf", "unknown", "needs_review")

        from apps.engine.dashboard import get_dashboard

        dashboard = get_dashboard()
        self.assertEqual(dashboard["totals"]["documents"], 2)
        self.assertEqual(dashboard["totals"]["processed"], 1)
        self.assertEqual(dashboard["totals"]["needs_review"], 1)
        self.assertEqual(dashboard["totals"]["attention"], 1)
        self.assertEqual(len(dashboard["attention"]), 1)
        self.assertEqual(dashboard["attention"][0]["file_name"], "Unknown.pdf")
        self.assertTrue(dashboard["recent_activity"])


if __name__ == "__main__":
    unittest.main()
