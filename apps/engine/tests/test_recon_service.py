from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"
OTHER_GSTIN = "29ABCDE1234F1Z5"


class ReconServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()
        from apps.engine.clients import create_client
        from apps.engine.dump import start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        self.client = create_client("Acme")
        self.period = create_period(self.client["id"], "Jul 2026")
        self.job = start_job(self.period["id"])

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def add_file(self, name: str, kind: str, outcome: str = "processed", period_id: int | None = None) -> int:
        from apps.engine.db import StoredFile, get_session

        period_id = period_id or self.period["id"]
        session = get_session()
        try:
            stored = StoredFile(
                job_id=self.job["id"],
                period_id=period_id,
                original_name=name,
                mime="application/pdf",
                size=10,
                storage_key=f"{period_id}/{name}",
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

    def add_row(self, file_id: int, kind: str, payload: dict, page: int = 1) -> int:
        from apps.engine.db import ExtractedRow, get_session

        session = get_session()
        try:
            row = ExtractedRow(
                file_id=file_id,
                period_id=self.period["id"],
                kind=kind,
                payload_json=json.dumps(payload),
                source_page=page,
                source_bbox="10,20,30,40",
                validation_flags="[]",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
        finally:
            session.close()

    def gstr_row(self, **overrides) -> dict:
        row = {
            "gstin": GSTIN,
            "invoice_number": "INV/001",
            "invoice_date": "12-07-2026",
            "invoice_value": 1180,
            "taxable": 1000,
            "igst": 180,
            "trade_name": "Acme Traders",
            "source": "GSTR-2B_July.json#b2b[0]",
            "document_type": "B2B",
        }
        row.update(overrides)
        return row

    def register_row(self, **overrides) -> dict:
        row = {
            "gstin": GSTIN,
            "invoice_number": "INV-1",
            "invoice_date": "2026-07-12",
            "taxable_value": 1000,
            "igst": 180,
            "amount": 1180,
            "party_name": "Acme Traders",
            "voucher_type": "Purchase",
            "register": "purchase",
            "source": "Tally.xml",
        }
        row.update(overrides)
        return row

    def seed_gst_match(self, register_overrides: dict | None = None) -> None:
        gstr_file = self.add_file("GSTR-2B_July.json", "gstr_2b")
        self.add_row(gstr_file, "gstr_2b", self.gstr_row())
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(tally_file, "tally", self.register_row(**(register_overrides or {})))

    def run_workflow(self, workflow_id: str, **kwargs):
        from apps.engine.recon_service import start_reconciliation

        return start_reconciliation(
            self.period["id"],
            workflow_id,
            actor="reviewer@firm.in",
            background=False,
            **kwargs,
        )

    def seed_unmatched(self) -> int:
        gstr_file = self.add_file("GSTR-2B_July.json", "gstr_2b")
        self.add_row(gstr_file, "gstr_2b", self.gstr_row(invoice_number="ONLY-2B", invoice_value=500, taxable=423.73, igst=76.27))
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(tally_file, "tally", self.register_row(invoice_number="ONLY-BOOKS", amount=1180))
        result = self.run_workflow("gst_2b_purchase_register")
        return result["id"]


class RunPersistenceTests(ReconServiceTestBase):
    def test_run_persists_matches_exceptions_rules_and_source_references(self) -> None:
        self.seed_gst_match()
        result = self.run_workflow("gst_2b_purchase_register")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertEqual(result["totals"]["records_processed"], 2)
        self.assertTrue(result["rules_snapshot"]["config"]["amount_tolerance"] >= 0)
        self.assertEqual(result["rules_snapshot"]["ruleset"]["name"], "Default reconciliation rules")

        from apps.engine.recon_service import get_run, get_run_rows, run_audit

        rows = get_run_rows(result["id"], {"page_size": 50})
        self.assertEqual(rows["total"], 1)
        row = rows["rows"][0]
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["left"][0]["file_name"], "GSTR-2B_July.json")
        self.assertEqual(row["right"][0]["file_name"], "Tally.xml")
        self.assertTrue(row["left"][0]["row_id"])
        self.assertTrue(row["right"][0]["source_page"])
        self.assertTrue(row["matched_fields"])

        audit = run_audit(result["id"])
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("run_started", actions)
        self.assertIn("run_completed", actions)
        self.assertTrue(all(event["actor"] == "reviewer@firm.in" for event in audit["events"] if event["action"].startswith("run_")))

    def test_missing_input_is_explained_and_no_run_is_created(self) -> None:
        gstr_file = self.add_file("GSTR-2B_July.json", "gstr_2b")
        self.add_row(gstr_file, "gstr_2b", self.gstr_row())
        result = self.run_workflow("gst_2b_purchase_register")
        self.assertFalse(result.get("available", True))
        self.assertIn("Purchase register", result["message"])
        from apps.engine.recon_service import list_runs

        self.assertEqual(list_runs({})["total"], 0)

    def test_control_centre_metrics_come_from_persisted_runs(self) -> None:
        self.seed_gst_match()
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import control_centre

        centre = control_centre({})
        metrics = centre["metrics"]
        self.assertEqual(metrics["total_runs"], 1)
        self.assertEqual(metrics["records_processed"], 2)
        self.assertEqual(metrics["matched_records"], 2)
        self.assertEqual(metrics["unmatched_records"], 0)
        self.assertEqual(metrics["match_rate"], 100.0)
        self.assertEqual(len(centre["recent_runs"]), 1)
        self.assertEqual(centre["recent_runs"][0]["id"], result["id"])
        self.assertEqual(centre["metrics"]["completion_counts"]["completed"], 1)

    def test_control_centre_filters_by_client_financial_year_and_workflow(self) -> None:
        self.seed_gst_match()
        self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import control_centre

        self.assertEqual(control_centre({"client_id": self.client["id"]})["metrics"]["total_runs"], 1)
        self.assertEqual(control_centre({"financial_year": "2026-27"})["metrics"]["total_runs"], 1)
        self.assertEqual(control_centre({"financial_year": "2025-26"})["metrics"]["total_runs"], 0)
        self.assertEqual(control_centre({"workflow_id": "bank_accounting"})["metrics"]["total_runs"], 0)

    def test_run_survives_engine_restart(self) -> None:
        self.seed_gst_match()
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.db import reset_engine
        from apps.engine.recon_service import get_run, get_run_rows

        reset_engine()
        stored = get_run(result["id"])
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["counts"]["matched"], 1)
        self.assertEqual(get_run_rows(result["id"], {})["total"], 1)

    def test_historical_run_payload_survives_source_row_deletion(self) -> None:
        self.seed_gst_match()
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.db import ExtractedRow, get_session
        from apps.engine.recon_service import get_match_detail, get_run_rows

        row_id = get_run_rows(result["id"], {})["rows"][0]["id"]
        session = get_session()
        try:
            session.query(ExtractedRow).delete()
            session.commit()
        finally:
            session.close()
        detail = get_match_detail(row_id)
        self.assertEqual(detail["match"]["left"][0]["reference"], "INV/001")
        self.assertEqual(detail["match"]["right"][0]["reference"], "INV-1")
        self.assertTrue(detail["match"]["explanation"])


class ExceptionLifecycleTests(ReconServiceTestBase):
    def test_exception_status_changes_are_audited_and_reopenable(self) -> None:
        run_id = self.seed_unmatched()
        from apps.engine.recon_service import get_exceptions, get_exception_detail, update_exception

        queue = get_exceptions({"run_id": run_id, "status": "outstanding"})
        self.assertGreaterEqual(queue["total"], 2)
        exception_id = queue["exceptions"][0]["id"]
        with self.assertRaises(ValueError):
            update_exception({"id": exception_id, "status": "resolved", "reason": ""}, "reviewer@firm.in")
        update_exception({"id": exception_id, "status": "investigating", "reason": "Checking the supplier portal"}, "reviewer@firm.in")
        update_exception({"id": exception_id, "status": "resolved", "reason": "Supporting invoice received"}, "reviewer@firm.in")
        detail = get_exception_detail(exception_id)
        self.assertEqual(detail["exception"]["status"], "resolved")
        self.assertIn("Supporting invoice received", detail["exception"]["resolution_reason"])
        self.assertTrue(any(event["action"] == "exception_updated" for event in detail["audit"]))
        update_exception({"id": exception_id, "status": "reopened", "reason": "Supplier disputed the credit"}, "reviewer@firm.in")
        reopened = get_exception_detail(exception_id)
        self.assertEqual(reopened["exception"]["status"], "reopened")
        self.assertIsNone(reopened["exception"]["resolved_at"])

    def test_assignment_and_note_are_audited(self) -> None:
        run_id = self.seed_unmatched()
        from apps.engine.recon_service import add_exception_note, get_exceptions, get_exception_detail, update_exception

        exception_id = get_exceptions({"run_id": run_id})["exceptions"][0]["id"]
        update_exception({"id": exception_id, "assigned_to": "partner@firm.in", "reason": "Assigned for partner review"}, "manager@firm.in")
        add_exception_note({"exception_id": exception_id, "note": "Called supplier; awaiting revised invoice."}, "manager@firm.in")
        detail = get_exception_detail(exception_id)
        self.assertEqual(detail["exception"]["assigned_to"], "partner@firm.in")
        self.assertTrue(any(event["action"] == "note_added" for event in detail["audit"]))

    def test_evidence_reference_is_attached_without_touching_source(self) -> None:
        run_id = self.seed_unmatched()
        from apps.engine.recon_service import get_exceptions, get_exception_detail, update_exception

        exception_id = get_exceptions({"run_id": run_id})["exceptions"][0]["id"]
        update_exception(
            {
                "id": exception_id,
                "evidence": [{"label": "Supplier confirmation", "reference": "email-2026-08-02"}],
            },
            "reviewer@firm.in",
        )
        detail = get_exception_detail(exception_id)
        self.assertEqual(detail["exception"]["evidence"][0]["reference"], "email-2026-08-02")


class DecisionTests(ReconServiceTestBase):
    def test_accept_and_unmatch_are_auditable(self) -> None:
        self.seed_gst_match(register_overrides={"amount": 1200})
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import accept_match, get_match_detail, get_run, get_run_rows, unmatch

        row = get_run_rows(result["id"], {"status": "review"})["rows"][0]
        accepted = accept_match(row["id"], "Reviewed supplier invoice and approved the difference", "partner@firm.in")
        self.assertEqual(accepted["status"], "accepted")
        detail = get_match_detail(row["id"])
        self.assertTrue(any(event["action"] == "match_accepted" for event in detail["audit"]))
        run = get_run(result["id"])
        self.assertEqual(run["totals"]["matched_records"], 2)
        self.assertEqual(run["completion_status"], "completed")

        unmatch(row["id"], "Supplier issued a revised invoice", "partner@firm.in")
        rows = get_run_rows(result["id"], {"status": "unmatched"})
        self.assertEqual(rows["total"], 2)

    def test_reject_releases_both_sides(self) -> None:
        self.seed_gst_match(register_overrides={"amount": 1200})
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import get_match_detail, get_run_rows, reject_match

        row = get_run_rows(result["id"], {"status": "review"})["rows"][0]
        reject_match(row["id"], "Different supplier invoice", "reviewer@firm.in")
        unmatched = get_run_rows(result["id"], {"status": "unmatched"})
        self.assertEqual(unmatched["total"], 2)
        self.assertEqual(len({record["file_name"] for item in unmatched["rows"] for record in item["left"] + item["right"]}), 2)
        old = get_match_detail(row["id"])
        self.assertTrue(old["match"]["is_superseded"])

    def test_manual_match_and_unmatch(self) -> None:
        run_id = self.seed_unmatched()
        from apps.engine.recon_service import get_match_detail, get_run_rows, manual_match, unmatch

        rows = get_run_rows(run_id, {"status": "unmatched"})["rows"]
        left = next(item for item in rows if item["left"])
        right = next(item for item in rows if item["right"])
        left_id = left["left"][0]["row_id"]
        right_id = right["right"][0]["row_id"]
        matched = manual_match(
            {
                "run_id": run_id,
                "left_ids": [left_id],
                "right_ids": [right_id],
                "reason": "Supplier confirmed the invoice reference by email",
            },
            "partner@firm.in",
        )
        self.assertEqual(matched["status"], "manual")
        detail = get_match_detail(matched["id"])
        self.assertTrue(any(event["action"] == "manual_match" for event in detail["audit"]))
        unmatch(matched["id"], "Wrong counterparty selected", "partner@firm.in")
        self.assertEqual(get_run_rows(run_id, {"status": "unmatched"})["total"], 2)

    def test_manual_allocation_requires_complete_allocation(self) -> None:
        from apps.engine.recon_service import manual_match

        gstr_file = self.add_file("GSTR-2B_July.json", "gstr_2b")
        self.add_row(gstr_file, "gstr_2b", self.gstr_row(invoice_number="INV-9"))
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(tally_file, "tally", self.register_row(invoice_number="INV-9-A", amount=600))
        self.add_row(tally_file, "tally", self.register_row(invoice_number="INV-9-B", amount=580))
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import get_run_rows

        rows = get_run_rows(result["id"], {"status": "review"})["rows"]
        proposal = next(item for item in rows if item["match_type"] == "one_to_many")
        left_id = proposal["left"][0]["row_id"]
        right_ids = [record["row_id"] for record in proposal["right"]]
        with self.assertRaises(ValueError):
            manual_match(
                {
                    "run_id": result["id"],
                    "left_ids": [left_id],
                    "right_ids": right_ids,
                    "reason": "Allocation without amounts",
                },
                "reviewer@firm.in",
            )
        matched = manual_match(
            {
                "run_id": result["id"],
                "left_ids": [left_id],
                "right_ids": right_ids,
                "allocations": [
                    {"left_id": left_id, "right_id": right_ids[0], "amount": 600},
                    {"left_id": left_id, "right_id": right_ids[1], "amount": 580},
                ],
                "reason": "Split invoice confirmed by supplier",
            },
            "reviewer@firm.in",
        )
        self.assertEqual(matched["status"], "manual")
        self.assertEqual(len(matched["allocations"]), 2)


class WorkflowCoverageTests(ReconServiceTestBase):
    def test_gstr_2b_invoices(self) -> None:
        gstr_file = self.add_file("GSTR-2B_July.json", "gstr_2b")
        self.add_row(gstr_file, "gstr_2b", self.gstr_row())
        invoice_file = self.add_file("Acme_Invoice.pdf", "invoice")
        self.add_row(
            invoice_file,
            "invoice",
            {
                "supplier_gstin": GSTIN,
                "invoice_number": "INV-1",
                "invoice_date": "2026-07-12",
                "taxable_value": 1000,
                "igst": 180,
                "invoice_value": 1180,
                "supplier_name": "Acme Traders",
                "source": "Acme_Invoice.pdf",
            },
        )
        result = self.run_workflow("gst_2b_invoices")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)

    def test_invoices_purchase_register(self) -> None:
        invoice_file = self.add_file("Acme_Invoice.pdf", "invoice")
        self.add_row(invoice_file, "invoice", {"supplier_gstin": GSTIN, "invoice_number": "INV-1", "invoice_date": "2026-07-12", "invoice_value": 1180, "supplier_name": "Acme Traders"})
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(tally_file, "tally", self.register_row())
        result = self.run_workflow("invoices_purchase_register")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)

    def test_gstr_1_sales_register(self) -> None:
        gstr_file = self.add_file("GSTR-1_July.json", "gstr_1")
        self.add_row(
            gstr_file,
            "gstr_1",
            {
                "gstin": OTHER_GSTIN,
                "invoice_number": "S/001",
                "invoice_date": "2026-07-12",
                "invoice_value": 590,
                "taxable": 500,
                "cgst": 45,
                "sgst": 45,
                "customer_name": "Beta Customer",
                "document_type": "B2B",
            },
        )
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(
            tally_file,
            "tally",
            {
                "customer_gstin": OTHER_GSTIN,
                "invoice_number": "S-1",
                "invoice_date": "2026-07-12",
                "taxable_value": 500,
                "cgst": 45,
                "sgst": 45,
                "amount": 590,
                "party_name": "Beta Customer",
                "voucher_type": "Sales",
                "register": "sales",
                "source": "Tally.xml",
            },
        )
        result = self.run_workflow("gstr_1_sales_register")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)

    def test_bank_statement_vs_ledger(self) -> None:
        bank_file = self.add_file("Bank_July.pdf", "bank")
        self.add_row(bank_file, "bank", {"date": "2026-07-14", "description": "NEFT ACME TRADERS INV/001", "debit": 1180, "credit": None, "balance": 11180, "closing_balance": 11180, "source": "Bank_July.pdf"})
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(
            tally_file,
            "tally",
            {
                "date": "2026-07-12",
                "invoice_number": "INV/001",
                "party_name": "Acme Traders",
                "amount": 1180,
                "voucher_type": "Payment",
                "closing_balance": 11180,
                "source": "Tally.xml",
            },
        )
        result = self.run_workflow("bank_accounting")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)
        self.assertTrue(result["checks"])

    def test_vendor_statement_vs_purchase_ledger(self) -> None:
        statement_file = self.add_file("Acme_Vendor_Statement.xlsx", "vendor_statement")
        self.add_row(
            statement_file,
            "vendor_statement",
            {
                "party_name": "Acme Traders",
                "invoice_number": "INV/001",
                "invoice_date": "2026-07-12",
                "amount": 1180,
                "debit": 1180,
                "credit": None,
                "source": "Acme_Vendor_Statement.xlsx",
            },
        )
        tally_file = self.add_file("Tally.xml", "tally")
        self.add_row(tally_file, "tally", self.register_row())
        result = self.run_workflow("vendor_statement_purchase_ledger")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)

    def test_gl_subledger_balance(self) -> None:
        sap_file = self.add_file("SAP_GL.xlsx", "sap")
        self.add_row(
            sap_file,
            "sap",
            {
                "gl_account": "210000",
                "account_name": "Creditors",
                "opening_balance": 5000,
                "debit": 2000,
                "credit": 3000,
                "closing_balance": 6000,
                "source": "SAP_GL.xlsx",
            },
        )
        self.add_row(
            sap_file,
            "sap",
            {
                "gl_account": "210000",
                "account_name": "Creditors",
                "vendor_number": "V-100",
                "opening_balance": 5000,
                "debit": 2000,
                "credit": 3000,
                "closing_balance": 6000,
                "source": "SAP_GL.xlsx",
            },
        )
        result = self.run_workflow("gl_subledger")
        self.assertTrue(result["available"])
        self.assertEqual(result["counts"]["matched"], 1)


class RulesHistoryExportTests(ReconServiceTestBase):
    def test_rule_versions_are_snapshotted_per_run(self) -> None:
        self.seed_gst_match(register_overrides={"amount": 1200})
        from apps.engine.recon_service import save_rule_set, get_ruleset

        first = save_rule_set({"name": "Strict review", "workflow_id": "gst_2b_purchase_register", "config": {"amount_tolerance": 0.5}, "notes": "First version"}, "partner@firm.in")
        second = save_rule_set({"name": "Strict review", "workflow_id": "gst_2b_purchase_register", "config": {"amount_tolerance": 2.0}, "notes": "Second version"}, "partner@firm.in")
        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        result = self.run_workflow("gst_2b_purchase_register", ruleset_id=second["id"])
        self.assertEqual(result["ruleset_version"], 2)
        self.assertEqual(result["rules_snapshot"]["config"]["amount_tolerance"], 2.0)
        later = save_rule_set({"name": "Strict review", "workflow_id": "gst_2b_purchase_register", "config": {"amount_tolerance": 0.1}}, "partner@firm.in")
        self.assertEqual(later["version"], 3)
        from apps.engine.recon_service import get_run

        stored = get_run(result["id"])
        self.assertEqual(stored["rules_snapshot"]["config"]["amount_tolerance"], 2.0)
        self.assertEqual(get_ruleset(first["id"])["config"]["amount_tolerance"], 0.5)

    def test_rerun_preserves_history_and_compare(self) -> None:
        self.seed_gst_match()
        first = self.run_workflow("gst_2b_purchase_register")
        second = self.run_workflow("gst_2b_purchase_register")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second["parent_run_id"], None)
        from apps.engine.recon_service import compare_runs, get_run, list_runs, rerun

        third = rerun(first["id"], "partner@firm.in", background=False)
        self.assertEqual(third["parent_run_id"], first["id"])
        self.assertEqual(list_runs({})["total"], 3)
        self.assertEqual(get_run(first["id"])["counts"]["matched"], 1)
        comparison = compare_runs(first["id"], second["id"])
        self.assertEqual(comparison["run_a"]["id"], first["id"])
        self.assertEqual(comparison["run_b"]["id"], second["id"])
        self.assertEqual(comparison["change_count"], 0)

    def test_excel_and_pdf_exports_are_real_files(self) -> None:
        self.seed_gst_match(register_overrides={"amount": 1200})
        result = self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import accept_match, get_run_rows
        from apps.engine.recon_report import export_reconciliation

        row = get_run_rows(result["id"], {"status": "review"})["rows"][0]
        accept_match(row["id"], "Approved after checking source invoice", "partner@firm.in")
        exported = export_reconciliation(result["id"])
        xlsx = Path(exported["xlsx"])
        pdf = Path(exported["pdf"])
        self.assertTrue(xlsx.is_file())
        self.assertTrue(pdf.is_file())
        book = load_workbook(xlsx)
        for name in (
            "Executive Summary",
            "Matched",
            "Unmatched Source",
            "Unmatched Destination",
            "Exceptions & Variances",
            "Duplicates",
            "Partial Matches",
            "Manual Adjustments",
            "Audit History",
            "Source References",
        ):
            self.assertIn(name, book.sheetnames)
        self.assertEqual(book["Executive Summary"]["A1"].value, "Reconciliation Executive Summary")
        self.assertEqual(pdf.read_bytes()[:4], b"%PDF")
        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        self.assertGreaterEqual(len(reader.pages), 1)
        self.assertIn("Reconciliation Executive Summary", reader.pages[0].extract_text())
        self.assertGreater(xlsx.stat().st_size, 4000)
        self.assertIn("TOTAL", [cell.value for cell in book["Matched"][book["Matched"].max_row]])

    def test_filter_options_use_real_data(self) -> None:
        self.seed_gst_match()
        self.run_workflow("gst_2b_purchase_register")
        from apps.engine.recon_service import recon_filter_options

        options = recon_filter_options()
        self.assertEqual(options["clients"][0]["name"], "Acme")
        self.assertIn("2026-27", options["financial_years"])
        self.assertGreaterEqual(len(options["workflows"]), 7)
        self.assertTrue(options["source_files"])
