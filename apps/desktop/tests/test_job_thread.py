from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class JobThreadFailureTests(unittest.TestCase):
    """A crashing worker must still leave the job failed, not stuck running."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.dump import start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Job Thread Firm")
        client = create_client("Acme")
        period = create_period(client["id"], "Jul 2026")
        self.job_id = start_job(period["id"])["id"]

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _status(self) -> str:
        from apps.engine.dump import get_job

        return get_job(self.job_id)["status"]

    def _join_threads(self) -> None:
        import apps.desktop.app as desktop_app

        for thread in list(desktop_app._job_threads):
            thread.join(timeout=10)

    def test_worker_exception_marks_the_job_failed(self) -> None:
        import apps.desktop.app as desktop_app

        def boom() -> None:
            raise RuntimeError("parser exploded")

        desktop_app._run_job_thread(self.job_id, boom)
        self._join_threads()

        self.assertEqual(self._status(), "failed")

    def test_job_is_still_failed_when_crash_logging_fails(self) -> None:
        import apps.desktop.app as desktop_app

        def boom() -> None:
            raise RuntimeError("parser exploded")

        original = desktop_app._log_crash

        def failing_log(_message: str) -> None:
            raise OSError(28, "No space left on device")

        desktop_app._log_crash = failing_log
        try:
            desktop_app._run_job_thread(self.job_id, boom)
            self._join_threads()
        finally:
            desktop_app._log_crash = original

        self.assertEqual(
            self._status(),
            "failed",
            "a failed log write must not leave the period stuck on 'parsing'",
        )


class StartupFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_second_instance_reports_instead_of_exiting_silently(self) -> None:
        from unittest import mock

        import apps.desktop.app as desktop_app

        messages: list[str] = []
        with mock.patch.object(desktop_app, "_acquire_single_instance_mutex", return_value=False), \
             mock.patch.object(desktop_app, "_show_fatal", side_effect=messages.append), \
             mock.patch.object(desktop_app, "_enable_fault_handler"), \
             mock.patch.object(desktop_app.webview, "create_window") as create_window:
            desktop_app.main()

        self.assertTrue(messages, "the user must be told the app is already open")
        create_window.assert_not_called()

    def test_startup_crash_shows_a_dialog_and_still_raises(self) -> None:
        from unittest import mock

        import apps.desktop.app as desktop_app

        messages: list[str] = []
        with mock.patch.object(desktop_app, "init_library"), \
             mock.patch.object(desktop_app, "get_engine", side_effect=RuntimeError("schema v4")), \
             mock.patch.object(desktop_app, "_show_fatal", side_effect=messages.append), \
             mock.patch.object(desktop_app, "_enable_fault_handler"), \
             mock.patch.object(desktop_app, "_log_crash") as log_crash:
            with self.assertRaises(RuntimeError):
                desktop_app.main()

        log_crash.assert_called_once()
        self.assertTrue(messages)
        self.assertIn("schema v4", messages[0])


if __name__ == "__main__":
    unittest.main()

