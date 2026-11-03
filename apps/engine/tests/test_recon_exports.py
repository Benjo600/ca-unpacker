from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _recon() -> dict:
    rows = [
        {
            "status": "matched",
            "reason": "Supplier, invoice number, date and amount all agree.",
            "party": "Acme Traders",
            "gstin": "27AAPFU0939F1ZV",
            "invoice_2b": "INV-1",
            "invoice_books": "INV/001",
            "date_2b": "2026-07-12",
            "date_books": "2026-07-12",
            "amount_2b": 11800.0,
            "amount_books": 11800.0,
            "amount_diff": 0.0,
            "decision": "accepted",
            "decision_label": "Accepted",
            "decision_reason": "",
            "decision_note": "",
            "decision_by": "Test firm",
            "decision_at": "2026-11-03T10:00:00+00:00",
        },
        {
            "status": "tax_mismatch",
            "reason": "Supplier, invoice, date and total agree, but central tax differs by 50.00.",
            "party": "Beta Traders",
            "gstin": "29ABCDE1234F1Z5",
            "invoice_2b": "INV-2",
            "invoice_books": "INV/002",
            "date_2b": "2026-07-14",
            "date_books": "2026-07-14",
            "amount_2b": 11800.0,
            "amount_books": 11800.0,
            "amount_diff": 0.0,
            "decision": "rejected",
            "decision_label": "Rejected",
            "decision_reason": "Rate difference",
            "decision_note": "Supplier to reissue",
            "decision_by": "Test firm",
            "decision_at": "2026-11-03T10:05:00+00:00",
        },
        {
            "status": "credit_note",
            "reason": "Credit note CN-9 from Beta Traders: kept on its own so the credit is not lost.",
            "party": "Beta Traders",
            "gstin": "29ABCDE1234F1Z5",
            "invoice_2b": "CN-9",
            "invoice_books": "",
            "date_2b": "2026-07-20",
            "date_books": "",
            "amount_2b": -1180.0,
            "amount_books": None,
            "amount_diff": None,
            "decision": "",
            "decision_label": "Not decided",
            "decision_reason": "",
            "decision_note": "",
            "decision_by": "",
            "decision_at": "",
        },
        {
            "status": "books_only",
            "reason": "This invoice appears only in the books.",
            "party": "Gamma",
            "gstin": "27AAPFU0939F1ZV",
            "invoice_2b": "",
            "invoice_books": "INV/777",
            "date_2b": "",
            "date_books": "2026-07-21",
            "amount_2b": None,
            "amount_books": 4500.0,
            "amount_diff": None,
            "decision": "noted",
            "decision_label": "Noted",
            "decision_reason": "Supplier has not filed",
            "decision_note": "",
            "decision_by": "Test firm",
            "decision_at": "2026-11-03T10:10:00+00:00",
        },
    ]
    return {
        "rows": rows,
        "counts": {
            "matched": 1,
            "books_only": 1,
            "portal_only": 0,
            "amount_mismatch": 0,
            "likely": 0,
            "tax_mismatch": 1,
            "duplicate": 0,
            "split_merged": 0,
            "credit_note": 1,
        },
        "totals": {
            "portal_total": 22420.0,
            "books_total": 28100.0,
            "gap": -5680.0,
            "credit_at_risk": 0.0,
            "unsupported_credit": 4500.0,
            "credit_note_total": 1180.0,
        },
        "tolerances": {"days": 7, "amount": 2.0},
        "decisions": {
            "counts": {
                "accepted": 1,
                "rejected": 1,
                "noted": 1,
                "undecided": 0,
                "new": 0,
                "exceptions": 3,
            },
            "money": {
                "accepted": 0.0,
                "rejected": 11800.0,
                "noted": 4500.0,
                "undecided": 1180.0,
                "at_stake": 17480.0,
            },
            "by_reason": {"rate_difference": 1, "supplier_not_filed": 1},
        },
    }


class ExceptionWorkbookTests(unittest.TestCase):
    def test_exceptions_file_has_only_the_problem_rows(self) -> None:
        from openpyxl import load_workbook

        from apps.engine.recon_exports import write_exceptions_workbook

        with tempfile.TemporaryDirectory() as tmp:
            path = write_exceptions_workbook(
                Path(tmp) / "Exceptions_Only.xlsx",
                client_name="Test client",
                period_label="Jul 2026",
                recon=_recon(),
            )
            book = load_workbook(path, data_only=True)
            sheet = book["Exceptions"]
            values = [list(row) for row in sheet.iter_rows(values_only=True)]
            flat = [" ".join(str(cell) for cell in row if cell is not None) for row in values]
            blob = "\n".join(flat)

            self.assertIn("Exceptions only", blob)
            self.assertIn("Test client", blob)
            self.assertIn("Allowance used: dates ±7 days, amounts ₹2.00", blob)
            headers = next(row for row in values if row and row[0] == "Status")
            self.assertEqual(headers[:3], ["Status", "Why", "Party"])
            self.assertIn("Decision", headers)
            self.assertIn("Decided by", headers)

            header_index = values.index(headers)
            body = values[header_index + 1 :]
            statuses = [
                row[0]
                for row in body
                if row
                and row[0]
                in {
                    "Only in books",
                    "Tax differs",
                    "Credit note",
                    "Matched",
                }
            ]
            self.assertEqual(sorted(statuses), ["Credit note", "Only in books", "Tax differs"])
            self.assertNotIn("Matched", statuses)

    def test_empty_exceptions_still_write_a_readable_file(self) -> None:
        from openpyxl import load_workbook

        from apps.engine.recon_exports import write_exceptions_workbook

        recon = _recon()
        recon["rows"] = [row for row in recon["rows"] if row["status"] == "matched"]
        with tempfile.TemporaryDirectory() as tmp:
            path = write_exceptions_workbook(
                Path(tmp) / "Exceptions_Only.xlsx",
                client_name="Test client",
                period_label="Jul 2026",
                recon=recon,
            )
            book = load_workbook(path, data_only=True)
            self.assertIn("Exceptions", book.sheetnames)


class AuditSummaryTests(unittest.TestCase):
    def test_summary_has_money_counts_tolerance_and_decision_log(self) -> None:
        from openpyxl import load_workbook

        from apps.engine.recon_exports import write_audit_summary

        with tempfile.TemporaryDirectory() as tmp:
            path = write_audit_summary(
                Path(tmp) / "Reconciliation_Summary.xlsx",
                client_name="Test client",
                period_label="Jul 2026",
                recon=_recon(),
            )
            book = load_workbook(path, data_only=True)
            sheet = book["Summary"]
            values = [list(row) for row in sheet.iter_rows(values_only=True)]
            pairs = {
                str(row[0]).strip(): row[1]
                for row in values
                if row and row[0] and len(row) > 1
            }

            self.assertEqual(pairs.get("Matched"), 1)
            self.assertEqual(pairs.get("Tax differs"), 1)
            self.assertEqual(pairs.get("Credit notes"), 1)
            self.assertEqual(pairs.get("Credit notes (kept separate)"), 1180.0)
            self.assertEqual(pairs.get("Rows accepted"), 1)
            self.assertEqual(pairs.get("Rows rejected"), 1)
            self.assertEqual(pairs.get("Rows noted"), 1)
            self.assertEqual(pairs.get("Still to decide"), 0)
            self.assertEqual(pairs.get("Allowance used: dates ±7 days, amounts ₹2.00"), None)
            blob = "\n".join(
                " ".join(str(cell) for cell in row if cell is not None) for row in values
            )
            self.assertIn("Allowance used: dates ±7 days, amounts ₹2.00", blob)
            self.assertIn("never changes the difference", blob)
            self.assertIn("Decision log", blob)
            self.assertIn("Rate difference", blob)
            self.assertIn("Supplier to reissue", blob)
            self.assertIn("Test firm", blob)

    def test_summary_without_decisions_says_so(self) -> None:
        from openpyxl import load_workbook

        from apps.engine.recon_exports import write_audit_summary

        recon = _recon()
        for row in recon["rows"]:
            row["decision"] = ""
            row["decision_label"] = "Not decided"
            row["decision_reason"] = ""
            row["decision_note"] = ""
            row["decision_by"] = ""
            row["decision_at"] = ""
        recon["decisions"]["counts"] = {
            "accepted": 0,
            "rejected": 0,
            "noted": 0,
            "undecided": 3,
            "new": 0,
            "exceptions": 3,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = write_audit_summary(
                Path(tmp) / "Reconciliation_Summary.xlsx",
                client_name="Test client",
                period_label="Jul 2026",
                recon=recon,
            )
            book = load_workbook(path, data_only=True)
            blob = "\n".join(
                " ".join(str(cell) for cell in row if cell is not None)
                for row in book["Summary"].iter_rows(values_only=True)
            )
            self.assertIn("No decisions recorded", blob)


if __name__ == "__main__":
    unittest.main()
