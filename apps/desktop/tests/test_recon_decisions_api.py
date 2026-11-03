from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class ReconDecisionApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Contract firm")
        client = create_client("Acme")
        self.period = create_period(client["id"], "Jul 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def test_api_exposes_the_two_decision_methods(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        self.assertTrue(callable(getattr(api, "set_recon_decision", None)))
        self.assertTrue(callable(getattr(api, "clear_recon_decision", None)))

    def test_unknown_decision_returns_ok_false_without_raising(self) -> None:
        from apps.desktop.app import DesktopApi

        result = DesktopApi().set_recon_decision(
            self.period["id"], "29ABCDE1234F1Z5|INV-1", "maybe"
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])

    def test_unknown_period_returns_ok_false_without_raising(self) -> None:
        from apps.desktop.app import DesktopApi

        result = DesktopApi().set_recon_decision(999999, "any|row", "accepted")

        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])

    def test_saving_and_clearing_a_decision_round_trips(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine import decisions
        from apps.engine.db import get_session

        api = DesktopApi()
        key = "29ABCDE1234F1Z5|INV-1"

        saved = api.set_recon_decision(
            self.period["id"],
            key,
            "accepted",
            reason_code="rate_difference",
            note="Agreed with the supplier.",
        )
        self.assertTrue(saved["ok"], saved)
        self.assertEqual(saved["decision"]["decision"], "accepted")
        self.assertEqual(saved["decision"]["reason_label"], "Rate difference")
        self.assertEqual(saved["decision"]["decided_by"], "Contract firm")

        cleared = api.clear_recon_decision(self.period["id"], key)
        self.assertTrue(cleared["ok"], cleared)
        self.assertEqual(cleared["decision"]["decision"], "")

        session = get_session()
        try:
            self.assertEqual(decisions.load(session, self.period["id"])[key]["decision"], "")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
