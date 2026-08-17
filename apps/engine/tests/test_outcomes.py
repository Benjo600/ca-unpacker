from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.engine.tests.fixtures_stage4 import make_password_pdf
from apps.engine.tests.test_stage3_bank import write_hdfc


class OutcomeContractTests(unittest.TestCase):
    def test_rows_are_processed_and_record_parser_identity(self) -> None:
        from apps.engine.outcomes import FileOutcome, evaluate_file_outcome

        result = evaluate_file_outcome(
            kind="bank",
            rows=[{"date": "2026-07-01", "flags": ["balance_mismatch"]}],
            parser_metadata={},
        )

        self.assertEqual(result.outcome, FileOutcome.PROCESSED)
        self.assertEqual(result.reason_code, "rows_extracted")
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.warnings, ("balance_mismatch",))
        self.assertEqual(result.parser_id, "bank_pdf")
        self.assertTrue(result.parser_version)

    def test_only_positive_valid_empty_evidence_is_processed(self) -> None:
        from apps.engine.outcomes import FileOutcome, evaluate_file_outcome

        unsupported_empty = evaluate_file_outcome(
            kind="tally", rows=[], parser_metadata={}
        )
        valid_empty = evaluate_file_outcome(
            kind="tally", rows=[], parser_metadata={"valid_empty": True}
        )

        self.assertEqual(unsupported_empty.outcome, FileOutcome.NEEDS_REVIEW)
        self.assertEqual(unsupported_empty.reason_code, "no_rows")
        self.assertEqual(valid_empty.outcome, FileOutcome.PROCESSED)
        self.assertEqual(valid_empty.reason_code, "valid_empty")
        self.assertEqual(valid_empty.row_count, 0)

    def test_password_and_unknown_are_distinct_terminal_outcomes(self) -> None:
        from apps.engine.outcomes import FileOutcome, evaluate_file_outcome

        password = evaluate_file_outcome(
            kind="unknown",
            rows=[],
            parser_metadata={},
            classification_reason="password-protected PDF",
        )
        unknown = evaluate_file_outcome(
            kind="unknown",
            rows=[],
            parser_metadata={},
            classification_reason="no matching file type",
        )

        self.assertEqual(password.outcome, FileOutcome.NEEDS_REVIEW)
        self.assertEqual(password.reason_code, "password_required")
        self.assertEqual(unknown.outcome, FileOutcome.UNCLASSIFIED)
        self.assertEqual(unknown.reason_code, "unknown_type")

    def test_job_status_is_derived_from_terminal_file_outcomes(self) -> None:
        from apps.engine.outcomes import FileOutcome, derive_job_status

        cases = [
            ([FileOutcome.PROCESSED], "done"),
            ([FileOutcome.PROCESSED, FileOutcome.NEEDS_REVIEW], "done_with_warnings"),
            ([FileOutcome.PROCESSED, FileOutcome.UNCLASSIFIED], "done_with_warnings"),
            ([FileOutcome.PROCESSED, FileOutcome.FAILED], "done_with_warnings"),
            ([FileOutcome.UNCLASSIFIED], "done_with_warnings"),
            ([FileOutcome.NEEDS_REVIEW], "done_with_warnings"),
            ([FileOutcome.FAILED], "failed"),
            ([FileOutcome.FAILED, FileOutcome.NEEDS_REVIEW], "failed"),
        ]

        for outcomes, expected in cases:
            with self.subTest(outcomes=outcomes):
                self.assertEqual(derive_job_status(outcomes), expected)


class PersistedOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        reset_engine()
        clear_all_passwords()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
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

    def _ingest(self, *paths: Path) -> dict:
        from apps.engine.dump import ingest_paths, start_job

        job = start_job(self.period["id"])
        return ingest_paths(job["id"], [str(path) for path in paths])

    def test_real_bank_rows_make_a_clean_job_done(self) -> None:
        bank = write_hdfc(self.inbox)

        job = self._ingest(bank)
        file = job["files"][0]

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["intake_discovered_count"], 1)
        self.assertEqual(job["intake_accepted_count"], 1)
        self.assertEqual(file["parse_outcome"], "processed")
        self.assertEqual(file["parse_reason_code"], "rows_extracted")
        self.assertGreaterEqual(file["parse_row_count"], 3)
        self.assertEqual(file["parser_id"], "bank_pdf")
        self.assertIsNotNone(file["processed_at"])

    def test_password_required_is_review_only_and_job_warns(self) -> None:
        source = write_hdfc(self.inbox)
        locked = make_password_pdf(source, self.inbox / "locked.pdf", "secret")

        job = self._ingest(locked)
        file = job["files"][0]

        self.assertEqual(job["status"], "done_with_warnings")
        self.assertEqual(file["parse_outcome"], "needs_review")
        self.assertEqual(file["parse_reason_code"], "password_required")
        self.assertTrue(file["needs_password"])

    def test_unknown_type_is_unclassified_and_job_warns(self) -> None:
        unknown = self.inbox / "notes.bin"
        unknown.write_bytes(b"not a supported accounting export")

        job = self._ingest(unknown)
        file = job["files"][0]

        self.assertEqual(job["status"], "done_with_warnings")
        self.assertEqual(file["parse_outcome"], "unclassified")
        self.assertEqual(file["parse_reason_code"], "unknown_type")
        self.assertIsNotNone(file["processed_at"])

    def test_copy_failure_persists_counts_before_copy_and_fails_job(self) -> None:
        source = self.inbox / "copy-me.txt"
        source.write_text("Tally export placeholder", encoding="utf-8")
        observed_counts: list[tuple[int, int]] = []

        def fail_copy(_source, _dest):
            from apps.engine.db import Job, get_session

            session = get_session()
            try:
                row = session.query(Job).one()
                observed_counts.append(
                    (row.intake_discovered_count, row.intake_accepted_count)
                )
            finally:
                session.close()
            raise OSError("copy denied")

        with patch("apps.engine.dump.shutil.copy2", side_effect=fail_copy):
            job = self._ingest(source)

        file = job["files"][0]
        self.assertEqual(observed_counts, [(1, 1)])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(file["storage_key"], "")
        self.assertEqual(file["parse_outcome"], "failed")
        self.assertEqual(file["parse_reason_code"], "copy_failed")

    def test_parser_exception_is_redacted_and_persisted_per_file(self) -> None:
        tally = self.inbox / "Tally_Daybook.xml"
        tally.write_text(
            "<ENVELOPE><TALLYMESSAGE><VOUCHER VCHTYPE='Sales'/></TALLYMESSAGE></ENVELOPE>",
            encoding="utf-8",
        )

        with patch(
            "apps.engine.pipeline.parse_tally_file",
            side_effect=RuntimeError(
                "Traceback (most recent call last):\n  File parser.py, line 1"
            ),
        ):
            job = self._ingest(tally)

        file = job["files"][0]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(file["parse_outcome"], "failed")
        self.assertEqual(file["parse_reason_code"], "parser_error")
        self.assertTrue(file["parse_reason_message"])
        self.assertEqual(file["parser_id"], "tally")
        self.assertTrue(file["parser_version"])
        self.assertNotIn("Traceback", file["parse_reason_message"])
        self.assertNotIn("parser.py", file["parse_reason_message"])

    def test_infrastructure_failure_leaves_every_accepted_file_terminal(self) -> None:
        from apps.engine.dump import get_job, ingest_paths, start_job

        bank = write_hdfc(self.inbox)
        started = start_job(self.period["id"])

        with patch(
            "apps.engine.dump.parse_period_banks",
            side_effect=RuntimeError("output subsystem unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                ingest_paths(started["id"], [str(bank)])

        job = get_job(started["id"])
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["files"][0]["parse_outcome"], "failed")
        self.assertEqual(job["files"][0]["parse_reason_code"], "infrastructure_error")
        self.assertIsNotNone(job["files"][0]["processed_at"])

    def test_processed_plus_unknown_derives_done_with_warnings(self) -> None:
        bank = write_hdfc(self.inbox)
        unknown = self.inbox / "notes.bin"
        unknown.write_bytes(b"not a supported accounting export")

        job = self._ingest(bank, unknown)

        self.assertEqual(job["status"], "done_with_warnings")
        self.assertEqual(
            {file["parse_outcome"] for file in job["files"]},
            {"processed", "unclassified"},
        )

    def test_reparse_preserves_failed_copy_truth(self) -> None:
        from apps.engine.dump import list_period_files, reparse_period

        source = self.inbox / "copy-me.txt"
        source.write_text("copy failure", encoding="utf-8")
        with patch("apps.engine.dump.shutil.copy2", side_effect=OSError("copy denied")):
            first = self._ingest(source)
        before = list_period_files(self.period["id"])[0]

        reparsed = reparse_period(self.period["id"])
        after = list_period_files(self.period["id"])[0]

        self.assertEqual(first["status"], "failed")
        self.assertEqual(reparsed["status"], "failed")
        self.assertEqual(before["parse_reason_code"], "copy_failed")
        self.assertEqual(after["parse_reason_code"], "copy_failed")
        self.assertTrue(after["parse_reason_message"])


if __name__ == "__main__":
    unittest.main()
