from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_test_dump import pdf_with_text


def write_hdfc(folder: Path) -> Path:
    path = folder / "HDFC_Statement_Jul2026.pdf"
    path.write_bytes(
        pdf_with_text(
            [
                "HDFC Bank Account Statement",
                "Account Number 50100123456789",
                "IFSC HDFC0001234",
                "Opening Balance 150000.00",
                "01/07/2026 UPI merchant Withdrawal 2500.00 147500.00",
                "03/07/2026 NEFT INWARD Deposit 18000.00 165500.00",
                "05/07/2026 Cheque 112233 Withdrawal 1000.00 164500.00",
                "Closing Balance 164500.00",
            ]
        )
    )
    return path


class BankParserTests(unittest.TestCase):
    def test_parse_hdfc_dummy(self) -> None:
        from apps.engine.parsers.bank.parser import parse_bank_pdf
        from apps.engine.validators.balance import check_balance

        with tempfile.TemporaryDirectory() as tmp:
            path = write_hdfc(Path(tmp))
            parsed = parse_bank_pdf(path)
            self.assertEqual(parsed["profile"], "hdfc")
            self.assertGreaterEqual(len(parsed["rows"]), 3)
            dates = [row["date"] for row in parsed["rows"]]
            self.assertIn("2026-07-01", dates)
            check = check_balance(parsed["rows"], parsed["opening_balance"], parsed["stated_closing"])
            self.assertTrue(check["match"], check)


class BankPackPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_dump_writes_excel(self) -> None:
        from apps.engine.clients import create_client
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period
        from apps.engine.pipeline import get_period_pack

        save_firm("Test firm")
        client = create_client("Acme")
        period = create_period(client["id"], "Jul 2026")
        inbox = Path(self._tmp.name) / "inbox"
        inbox.mkdir()
        write_hdfc(inbox)
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(inbox / "HDFC_Statement_Jul2026.pdf")])
        pack = get_period_pack(period["id"])
        self.assertIsNotNone(pack)
        self.assertTrue(pack["exists"])
        self.assertGreaterEqual(pack["row_count"], 3)
        self.assertEqual(pack["balance_status"], "match")
        self.assertTrue(Path(pack["path"]).exists())


class ComplexStatementTests(unittest.TestCase):
    def test_complex_folder_balances(self) -> None:
        from apps.engine.parsers.bank.parser import parse_bank_pdf
        from apps.engine.validators.balance import check_balance

        folder = ROOT / "test-dump" / "complex-statements"
        files = list(folder.glob("*_complex.pdf"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            parsed = parse_bank_pdf(path)
            check = check_balance(
                parsed["rows"], parsed["opening_balance"], parsed["stated_closing"]
            )
            self.assertGreaterEqual(len(parsed["rows"]), 10, path.name)
            self.assertEqual(check["status"], "match", (path.name, check))


class BankWorkbookPolishTests(unittest.TestCase):
    def test_single_file_sheet_cover_source_and_flags(self) -> None:
        from openpyxl import load_workbook

        from apps.engine.pack.bank_xlsx import write_bank_workbook
        from apps.engine.validators.balance import check_balance

        rows = [
            {
                "date": "2026-07-01",
                "description": "UPI merchant",
                "cheque_ref": None,
                "debit": 2500.00,
                "credit": None,
                "balance": 147500.00,
                "source": "HDFC_Statement_Jul2026.pdf#p1",
            },
            {
                "date": "2026-07-03",
                "description": "NEFT INWARD",
                "cheque_ref": None,
                "debit": None,
                "credit": 18000.00,
                "balance": 165500.00,
                "source": "HDFC_Statement_Jul2026.pdf#p1",
            },
        ]
        check = check_balance(rows, 150000.00, 165500.00)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.xlsx"
            write_bank_workbook(
                path,
                [
                    {
                        "rows": rows,
                        "check": check,
                        "meta": {
                            "filename": "HDFC_Statement_Jul2026.pdf",
                            "profile_label": "HDFC",
                            "account_number": "50100123456789",
                            "ifsc": "HDFC0001234",
                        },
                    }
                ],
            )
            book = load_workbook(path)
            self.assertIn("Transactions", book.sheetnames)
            cover = book["Balance Check"]
            headers = [cell.value for cell in cover[4]]
            self.assertIn("Result", headers)
            result_col = headers.index("Result") + 1
            results = [cover.cell(row, result_col).value for row in range(5, cover.max_row + 1)]
            self.assertTrue(any(value in {"MATCH", "MISMATCH"} for value in results), results)
            sheet = book["Transactions"]
            tx_headers = [cell.value for cell in sheet[1]]
            self.assertIn("Flags", tx_headers)
            self.assertIn("Source", tx_headers)
            source_col = tx_headers.index("Source") + 1
            sources = [sheet.cell(row, source_col).value for row in range(2, sheet.max_row + 1)]
            self.assertTrue(any(source and "#p" in str(source) for source in sources), sources)

    def test_opening_inferred_when_opening_missing(self) -> None:
        from apps.engine.validators.balance import check_balance

        rows = [{"debit": 100.0, "credit": None, "balance": 900.0}]
        check = check_balance(rows, None, 900.0)
        self.assertIn("opening_inferred", check)
        self.assertTrue(check["opening_inferred"])


class DumpJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _period(self):
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        client = create_client("Acme")
        return create_period(client["id"], "Jul 2026")

    def test_start_job_rejects_in_progress(self) -> None:
        from apps.engine.db import Job, get_session
        from apps.engine.dump import start_job

        period = self._period()
        first = start_job(period["id"])
        with self.assertRaises(ValueError) as ctx:
            start_job(period["id"])
        self.assertIn("already", str(ctx.exception).lower())

        session = get_session()
        try:
            row = session.get(Job, first["id"])
            self.assertIsNotNone(row)
            row.status = "done"
            session.commit()
        finally:
            session.close()

        second = start_job(period["id"])
        self.assertNotEqual(second["id"], first["id"])

    def test_ingest_failure_marks_job_failed_without_traceback(self) -> None:
        from unittest.mock import patch

        from apps.engine.dump import get_job, ingest_paths, start_job

        period = self._period()
        inbox = Path(self._tmp.name) / "inbox"
        inbox.mkdir()
        source = inbox / "notes.txt"
        source.write_text("hello", encoding="utf-8")
        job = start_job(period["id"])
        with patch(
            "apps.engine.dump.parse_period_banks",
            side_effect=RuntimeError("Traceback (most recent call last):\n  File boom"),
        ):
            with self.assertRaises(RuntimeError):
                ingest_paths(job["id"], [str(source)])
        done = get_job(job["id"])
        self.assertIsNotNone(done)
        self.assertEqual(done["status"], "failed")
        self.assertNotIn("Traceback", done["error_message"] or "")
        self.assertTrue(done["error_message"])

    def test_reparse_period_after_override(self) -> None:
        from apps.engine.dump import (
            ingest_paths,
            list_period_files,
            override_kind,
            reparse_period,
            start_job,
        )
        from apps.engine.pipeline import get_period_pack

        period = self._period()
        inbox = Path(self._tmp.name) / "inbox"
        inbox.mkdir()
        write_hdfc(inbox)
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(inbox / "HDFC_Statement_Jul2026.pdf")])
        files = list_period_files(period["id"])
        bank = next(row for row in files if row["kind"] == "bank")
        updated = override_kind(bank["id"], "bank")
        self.assertEqual(updated["kind"], "bank")
        parsed = reparse_period(period["id"])
        self.assertEqual(parsed["status"], "done")
        pack = get_period_pack(period["id"])
        self.assertIsNotNone(pack)
        self.assertTrue(pack["exists"])


class LongStatementTests(unittest.TestCase):
    def test_long_folder_if_present(self) -> None:
        from apps.engine.parsers.bank.parser import parse_bank_pdf
        from apps.engine.validators.balance import check_balance

        folder = ROOT / "test-dump" / "long-statements"
        files = list(folder.glob("*_LONG.pdf"))
        if not files:
            self.skipTest("long statements not generated yet")
        for path in files:
            parsed = parse_bank_pdf(path)
            check = check_balance(
                parsed["rows"], parsed["opening_balance"], parsed["stated_closing"]
            )
            self.assertGreaterEqual(len(parsed["rows"]), 80, path.name)
            self.assertEqual(check["status"], "match", (path.name, check, len(parsed["rows"])))


if __name__ == "__main__":
    unittest.main()
