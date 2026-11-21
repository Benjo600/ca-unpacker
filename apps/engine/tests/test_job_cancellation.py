from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_test_dump import pdf_with_text


def _bank_pdf(target: Path) -> None:
    target.write_bytes(
        pdf_with_text(
            [
                "HDFC Bank Statement",
                "Account Number 50100123456789",
                "IFSC HDFC0001234",
                "Opening Balance 1,000.00",
                "01/07/2026 UPI payment 100.00 1,100.00",
                "Closing Balance 1,100.00",
            ]
        )
    )


class CancelFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"LOCALAPPDATA": self._tmp.name})
        self._env.start()
        from apps.engine.db import reset_engine

        reset_engine()
        from apps.engine.firm import save_firm
        from apps.engine.clients import create_client
        from apps.engine.periods import create_period

        save_firm("Test firm")
        client = create_client("Acme")
        self.period = create_period(client["id"], "Jul 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._env.stop()
        self._tmp.cleanup()

    def _mark_cancel_requested(self, job_id: int) -> None:
        from apps.engine.db import Job, get_session

        session = get_session()
        try:
            job = session.get(Job, job_id)
            job.status = "cancel_requested"
            session.commit()
        finally:
            session.close()

    def test_cancel_job_requests_and_finishes(self) -> None:
        from apps.engine.dump import cancel_job, finish_cancelled_job, job_cancel_requested, start_job

        job = start_job(self.period["id"])
        result = cancel_job(job["id"])
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["status"], "cancel_requested")
        self.assertTrue(job_cancel_requested(job["id"]))

        finish_cancelled_job(job["id"])
        self.assertFalse(job_cancel_requested(job["id"]))

        # Cancelling a finished job is a no-op, not an error.
        again = cancel_job(job["id"])
        self.assertFalse(again["cancelled"])
        self.assertEqual(again["status"], "cancelled")

    def test_cancel_job_unknown_job_raises(self) -> None:
        from apps.engine.dump import cancel_job

        with self.assertRaises(ValueError):
            cancel_job(999999)

    def test_ingest_honours_cancel_request_and_keeps_processed_files(self) -> None:
        from apps.engine.dump import (
            JobCancelled,
            ingest_paths,
            list_period_files,
            start_job,
        )

        inbox = Path(self._tmp.name)
        first = inbox / "one.pdf"
        second = inbox / "two.pdf"
        _bank_pdf(first)
        _bank_pdf(second)

        job = start_job(self.period["id"])
        self._mark_cancel_requested(job["id"])

        with self.assertRaises(JobCancelled):
            ingest_paths(job["id"], [str(first), str(second)])

        from apps.engine.dump import get_job

        payload = get_job(job["id"])
        self.assertEqual(payload["status"], "cancelled")
        self.assertIn("cancelled", (payload["error_message"] or "").lower())
        # Nothing was copied or parsed after the cancel request.
        files = list_period_files(self.period["id"])
        self.assertEqual(len(files), 0)

    def test_parse_period_honours_cancel_request(self) -> None:
        from apps.engine.dump import JobCancelled, start_job
        from apps.engine.pipeline import parse_period

        job = start_job(self.period["id"])
        self._mark_cancel_requested(job["id"])

        with self.assertRaises(JobCancelled):
            parse_period(self.period["id"], job["id"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
