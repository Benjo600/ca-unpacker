from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class DesktopWarningApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        reset_engine()
        clear_all_passwords()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Contract firm")
        client = create_client("Acme")
        self.period = create_period(client["id"], "Jul 2026")
        self.inbox = Path(self._tmp.name) / "inbox"
        self.inbox.mkdir()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        clear_all_passwords()
        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def test_desktop_job_response_versions_exact_file_outcome_counts(self) -> None:
        """A missing or miscounted terminal outcome must fail this API contract."""
        from apps.desktop.app import DesktopApi
        from apps.engine.dump import ingest_paths, start_job

        unknown = self.inbox / "notes.bin"
        unknown.write_bytes(b"not a supported accounting export")
        started = start_job(self.period["id"])
        ingest_paths(started["id"], [str(unknown)])

        result = DesktopApi().get_job(started["id"])

        self.assertTrue(result["ok"])
        job = result["job"]
        self.assertEqual(job["api_version"], 1)
        self.assertEqual(
            job["outcome_counts"],
            {
                "processed": 0,
                "needs_review": 0,
                "failed": 0,
                "unclassified": 1,
            },
        )
        self.assertEqual(job["status"], "done_with_warnings")
        self.assertEqual(job["intake_discovered_count"], 1)
        self.assertEqual(job["intake_accepted_count"], 1)
        self.assertEqual(job["files"][0]["parse_outcome"], "unclassified")
        self.assertTrue(job["files"][0]["parse_reason_message"])

    def test_desktop_job_response_exposes_persisted_file_outcome_fields(self) -> None:
        """Removing persisted parser evidence from the desktop response is a contract break."""
        from apps.desktop.app import DesktopApi
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.tests.test_stage3_bank import write_hdfc

        source = write_hdfc(self.inbox)
        started = start_job(self.period["id"])
        ingest_paths(started["id"], [str(source)])

        result = DesktopApi().get_job(started["id"])

        file = result["job"]["files"][0]
        self.assertEqual(file["parse_outcome"], "processed")
        self.assertEqual(file["parse_reason_code"], "rows_extracted")
        self.assertTrue(file["parse_reason_message"])
        self.assertGreater(file["parse_row_count"], 0)
        self.assertIsInstance(file["parse_warnings"], list)
        self.assertEqual(file["parser_id"], "bank_pdf")
        self.assertTrue(file["parser_version"])
        self.assertTrue(file["processed_at"])
