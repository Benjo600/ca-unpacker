from __future__ import annotations

import os
import tempfile
import unittest


class ToleranceApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Tolerance firm")
        self.client = create_client("Tolerance client")
        self.period = create_period(self.client["id"], "Aug 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original

    def test_client_allowance_saves_and_reads_back(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine.clients import get_client

        result = DesktopApi().set_client_tolerances(self.client["id"], "7", "2.50")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["client"]["tolerance_days"], 7)
        self.assertEqual(result["client"]["tolerance_amount"], 2.5)
        stored = get_client(self.client["id"])
        self.assertEqual(stored["tolerance_days"], 7)
        self.assertEqual(stored["tolerance_amount"], 2.5)

    def test_month_override_wins_until_cleared(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine.periods import effective_tolerances

        api = DesktopApi()
        api.set_client_tolerances(self.client["id"], 2, 1.5)
        self.assertEqual(effective_tolerances(self.period["id"]), (2, 1.5))

        saved = api.set_period_tolerances(self.period["id"], 7, 5)
        self.assertTrue(saved["ok"], saved)
        self.assertEqual(effective_tolerances(self.period["id"]), (7, 5.0))

        cleared = api.set_period_tolerances(self.period["id"], None, None)
        self.assertTrue(cleared["ok"], cleared)
        self.assertEqual(effective_tolerances(self.period["id"]), (2, 1.5))

    def test_bad_allowance_returns_ok_false(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        for days, amount in ((31, 1), (-1, 1), (0, -5), (0, 1001), ("many", 1), (0, "lots")):
            result = api.set_client_tolerances(self.client["id"], days, amount)
            self.assertFalse(result["ok"], (days, amount, result))
            self.assertTrue(result["error"])

    def test_unknown_client_or_period_is_friendly(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        self.assertFalse(api.set_client_tolerances(999999, 0, 1)["ok"])
        self.assertFalse(api.set_period_tolerances(999999, 0, 1)["ok"])


if __name__ == "__main__":
    unittest.main()
