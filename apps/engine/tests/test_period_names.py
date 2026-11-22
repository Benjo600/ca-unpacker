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


class PeriodNameTests(unittest.TestCase):
    """A period name ends up in folder names and filters, so it must be a month."""

    def test_common_spellings_become_one_canonical_name(self) -> None:
        from apps.engine.periods import normalize_period_label

        for raw in ["Oct 2026", "october 2026", "OCT-2026", "  Oct/2026 ", "10/2026", "10-2026"]:
            self.assertEqual(normalize_period_label(raw), "Oct 2026", raw)

    def test_nonsense_is_refused_with_plain_words(self) -> None:
        from apps.engine.periods import normalize_period_label

        for raw in ["", "   ", "13 2026", "Oct-26", "next month", "Oct", "2026", "0/2026"]:
            with self.assertRaises(ValueError) as caught:
                normalize_period_label(raw)
            self.assertIn("month", str(caught.exception).lower(), raw)


class CreatePeriodTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"LOCALAPPDATA": self._tmp.name})
        self._env.start()
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm

        save_firm("Test firm")
        self.client = create_client("Acme Traders")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._env.stop()
        self._tmp.cleanup()

    def test_the_same_month_cannot_be_created_twice_under_a_different_spelling(self) -> None:
        from apps.engine.periods import create_period, list_periods

        create_period(self.client["id"], "Oct 2026")
        with self.assertRaises(ValueError) as caught:
            create_period(self.client["id"], "October-2026")
        self.assertIn("Oct 2026", str(caught.exception))
        self.assertEqual(len(list_periods(self.client["id"])), 1)

    def test_a_mistyped_month_is_refused(self) -> None:
        from apps.engine.periods import create_period, list_periods

        with self.assertRaises(ValueError):
            create_period(self.client["id"], "13 2026")
        self.assertEqual(list_periods(self.client["id"]), [])


class DeletePeriodTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"LOCALAPPDATA": self._tmp.name})
        self._env.start()
        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm

        save_firm("Test firm")
        self.client = create_client("Acme Traders")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._env.stop()
        self._tmp.cleanup()

    def test_deleting_one_month_leaves_the_others_and_the_client(self) -> None:
        from apps.engine.clients import list_clients
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.periods import create_period, delete_period, list_periods
        from make_test_dump import pdf_with_text

        keep = create_period(self.client["id"], "Sep 2026")
        drop = create_period(self.client["id"], "Oct 2026")
        inbox = Path(self._tmp.name)
        statement = inbox / "statement.pdf"
        statement.write_bytes(
            pdf_with_text(
                [
                    "HDFC Bank Statement",
                    "Opening Balance 1,000.00",
                    "01/07/2026 UPI 100.00 1,100.00",
                    "Closing Balance 1,100.00",
                ]
            )
        )
        job = start_job(drop["id"])
        ingest_paths(job["id"], [str(statement)])

        removed = delete_period(drop["id"])

        self.assertEqual(removed["period_id"], drop["id"])
        remaining = [period["id"] for period in list_periods(self.client["id"])]
        self.assertEqual(remaining, [keep["id"]])
        self.assertEqual(len(list_clients()), 1)

    def test_deleting_a_missing_month_is_refused(self) -> None:
        from apps.engine.periods import delete_period

        with self.assertRaises(ValueError):
            delete_period(9999)


if __name__ == "__main__":
    unittest.main()
