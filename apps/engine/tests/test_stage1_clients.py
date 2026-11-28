from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Stage1PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_no_firm_until_saved(self) -> None:
        from apps.engine.firm import get_firm

        self.assertIsNone(get_firm())

    def test_client_survives_engine_restart(self) -> None:
        from apps.engine.clients import create_client, list_clients
        from apps.engine.db import reset_engine
        from apps.engine.firm import save_firm
        from apps.engine.library import get_db_path

        save_firm("Mehta & Associates")
        created = create_client("Acme Traders", "27AAPFU0939F1ZV")
        self.assertEqual(created["name"], "Acme Traders")
        self.assertTrue(get_db_path().exists())

        reset_engine()
        names = [row["name"] for row in list_clients()]
        self.assertEqual(names, ["Acme Traders"])

    def test_reject_empty_client_name(self) -> None:
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm

        save_firm("Mehta & Associates")
        with self.assertRaises(ValueError):
            create_client("   ")


class DeleteClientWhileJobRunningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm

        save_firm("Mehta & Associates")
        self.client = create_client("Acme Traders")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _add_job(self, status: str) -> tuple[int, int]:
        from apps.engine.db import Job, get_session
        from apps.engine.periods import create_period

        period = create_period(self.client["id"], "Oct 2026")
        session = get_session()
        try:
            job = Job(period_id=period["id"], client_id=self.client["id"], status=status)
            session.add(job)
            session.commit()
            return period["id"], job.id
        finally:
            session.close()

    def test_client_with_a_running_job_cannot_be_deleted(self) -> None:
        from apps.engine.clients import delete_client, list_clients

        self._add_job("parsing")
        with self.assertRaises(ValueError) as caught:
            delete_client(self.client["id"])
        self.assertIn("still being processed", str(caught.exception))
        self.assertEqual([row["id"] for row in list_clients()], [self.client["id"]])

    def test_client_is_deletable_once_the_job_finishes(self) -> None:
        from apps.engine.clients import delete_client, list_clients
        from apps.engine.db import Job, get_session

        _, job_id = self._add_job("parsing")
        session = get_session()
        try:
            job = session.get(Job, job_id)
            job.status = "done"
            session.commit()
        finally:
            session.close()

        delete_client(self.client["id"])
        self.assertEqual(list_clients(), [])


if __name__ == "__main__":
    unittest.main()
