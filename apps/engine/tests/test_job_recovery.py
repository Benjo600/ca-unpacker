from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class InterruptedJobTests(unittest.TestCase):
    """A crash must never leave a period blocked behind a dead job."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Recovery Test Firm")
        client = create_client("Acme")
        self.period = create_period(client["id"], "Jul 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _job(self, status: str, *, minutes_ago: int = 0) -> int:
        from apps.engine.db import Job, get_session, utcnow

        session = get_session()
        try:
            job = Job(
                client_id=self.period["client_id"],
                period_id=self.period["id"],
                status=status,
            )
            if minutes_ago:
                job.created_at = utcnow() - timedelta(minutes=minutes_ago)
            session.add(job)
            session.commit()
            session.refresh(job)
            return job.id
        finally:
            session.close()

    def _status(self, job_id: int) -> str:
        from apps.engine.db import Job, get_session

        session = get_session()
        try:
            return session.get(Job, job_id).status
        finally:
            session.close()

    def test_stranded_job_is_failed_on_restart(self) -> None:
        from apps.engine.dump import reconcile_interrupted_work

        job_id = self._job("parsing")

        self.assertEqual(reconcile_interrupted_work(), 1)
        self.assertEqual(self._status(job_id), "failed")

    def test_restart_frees_the_period_for_a_new_job(self) -> None:
        from apps.engine.dump import reconcile_interrupted_work, start_job

        self._job("routing")
        reconcile_interrupted_work()

        job = start_job(self.period["id"])  # must not raise "already being processed"
        self.assertEqual(job["status"], "queued")

    def test_finished_jobs_are_left_alone(self) -> None:
        from apps.engine.dump import reconcile_interrupted_work

        job_id = self._job("done")

        self.assertEqual(reconcile_interrupted_work(), 0)
        self.assertEqual(self._status(job_id), "done")

    def test_stale_job_is_replaced_without_a_restart(self) -> None:
        from apps.engine.dump import start_job

        stale = self._job("parsing", minutes_ago=90)

        job = start_job(self.period["id"])
        self.assertEqual(self._status(stale), "failed")
        self.assertEqual(job["status"], "queued")

    def test_a_recently_started_job_still_blocks_the_period(self) -> None:
        from apps.engine.dump import start_job

        self._job("parsing", minutes_ago=1)

        with self.assertRaises(ValueError):
            start_job(self.period["id"])

    def test_reconcile_is_idempotent(self) -> None:
        from apps.engine.dump import reconcile_interrupted_work

        self._job("queued")

        self.assertEqual(reconcile_interrupted_work(), 1)
        self.assertEqual(reconcile_interrupted_work(), 0)


if __name__ == "__main__":
    unittest.main()
