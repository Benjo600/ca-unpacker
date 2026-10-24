from __future__ import annotations

import os
import tempfile
import unittest


class DesktopPracticeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def test_dashboard_workspace_and_reports_are_real_empty_states(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        dashboard = api.get_dashboard()
        self.assertTrue(dashboard["ok"])
        self.assertEqual(dashboard["totals"]["documents"], 0)
        self.assertIn("latest_reconciliation", dashboard)
        self.assertFalse(dashboard["latest_reconciliation"]["available"])

        workspace = api.get_reconciliation_workspace()
        self.assertTrue(workspace["ok"])
        self.assertEqual(workspace["periods"], [])
        self.assertGreaterEqual(len(workspace["workflows"]), 3)

        reports = api.get_reports()
        self.assertTrue(reports["ok"])
        self.assertEqual(reports["packs"], [])

    def test_unknown_reconciliation_workflow_is_rejected(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        result = api.run_reconciliation(1, "not-a-workflow")
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])

    def test_missing_extracted_record_is_reported(self) -> None:
        from apps.desktop.app import DesktopApi

        api = DesktopApi()
        result = api.get_extracted_record(99999)
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"])

    def test_production_ui_has_practice_navigation_and_panes(self) -> None:
        from pathlib import Path

        html = (
            Path(__file__).resolve().parents[3] / "apps" / "ui" / "index.html"
        ).read_text(encoding="utf-8")
        for element_id in (
            "nav-dashboard",
            "nav-recon",
            "nav-reports",
            "pane-dashboard",
            "pane-recon",
            "pane-reports",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('src="practice-summary.js"', html)
        self.assertIn('id="dashboard-error"', html)
        self.assertIn('id="recon-page-error"', html)
        self.assertIn('id="reports-error"', html)


if __name__ == "__main__":
    unittest.main()
