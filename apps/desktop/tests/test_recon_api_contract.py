from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class ReconApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original

    def test_control_centre_workbench_and_rules_are_real_empty_states(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        centre = api.get_recon_control_centre({})
        self.assertTrue(centre["ok"])
        self.assertEqual(centre["metrics"]["total_runs"], 0)
        self.assertEqual(centre["metrics"]["records_processed"], 0)
        self.assertEqual(centre["recent_runs"], [])
        self.assertIn("workflows", centre["filters"])
        self.assertGreaterEqual(len(centre["filters"]["workflows"]), 7)

        workspace = api.get_recon_workspace()
        self.assertTrue(workspace["ok"])
        self.assertEqual(workspace["periods"], [])
        self.assertGreaterEqual(len(workspace["workflows"]), 7)

        rules = api.get_recon_rules("")
        self.assertTrue(rules["ok"])
        self.assertEqual(rules["rulesets"], [])
        self.assertIn("amount_tolerance", rules["defaults"])

        history = api.list_recon_runs({})
        self.assertTrue(history["ok"])
        self.assertEqual(history["total"], 0)

        exceptions = api.get_recon_exceptions({"status": "outstanding"})
        self.assertTrue(exceptions["ok"])
        self.assertEqual(exceptions["total"], 0)

    def test_missing_run_and_exception_are_reported(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        self.assertFalse(api.get_recon_run(9999)["ok"])
        self.assertFalse(api.get_recon_run_rows(9999, {})["ok"])
        self.assertFalse(api.get_recon_match(9999)["ok"])
        self.assertFalse(api.get_recon_exception(9999)["ok"])
        self.assertFalse(api.cancel_recon_run(9999)["ok"])

    def test_start_requires_a_real_period(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        self.assertFalse(api.start_recon_run(9999, "gst_2b_purchase_register")["ok"])
        self.assertFalse(api.start_recon_run(1, "not-a-workflow")["ok"])

    def test_production_ui_contains_control_centre_shell(self) -> None:
        root = Path(__file__).resolve().parents[3]
        html = (root / "apps" / "ui" / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "pane-recon",
            "recon-page-error",
            "recon-tabs",
            "recon-centre",
            "recon-run-button",
            "recon-export-button",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('src="recon-centre.js"', html)
        self.assertIn('href="recon-centre.css"', html)
        script = (root / "apps" / "ui" / "recon-centre.js").read_text(encoding="utf-8")
        for needle in (
            "get_recon_control_centre",
            "get_recon_run_rows",
            "get_recon_exceptions",
            "get_recon_rules",
            "recon_decide",
            "manual_match",
            "export_recon_run",
        ):
            self.assertIn(needle, script)
        self.assertNotIn("hardcoded demo", script.lower())


if __name__ == "__main__":
    unittest.main()
