"""A swallowed failure in job bookkeeping must leave a trace in the log."""

from __future__ import annotations

import unittest

from apps.engine.dump import _mark_unfinished_files_failed


class QuietExceptionLoggingTest(unittest.TestCase):
    def test_failed_bookkeeping_is_logged_instead_of_disappearing(self):
        class BrokenSession:
            def expire_all(self) -> None:
                raise RuntimeError("database is locked")

            def rollback(self) -> None:
                raise RuntimeError("rollback failed too")

        with self.assertLogs("apps.engine.dump", level="WARNING") as captured:
            # Still returns None: the job handler carries on and reports the
            # original failure. The point is that the cause is no longer lost.
            self.assertIsNone(_mark_unfinished_files_failed(BrokenSession(), 42))

        logged = "\n".join(captured.output)
        self.assertIn("Could not mark unfinished files of job 42", logged)
        self.assertIn("database is locked", logged)


if __name__ == "__main__":
    unittest.main()
