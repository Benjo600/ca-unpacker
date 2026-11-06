from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class UiLocationTests(unittest.TestCase):
    """The desk must come back to the screen the user left."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_location_round_trips(self) -> None:
        from apps.engine.settings import get_ui_location, save_ui_location

        entry = {"pane": "dump", "clientId": 3, "periodId": 7}
        save_ui_location(entry)

        self.assertEqual(get_ui_location(), entry)

    def test_location_can_be_cleared(self) -> None:
        from apps.engine.settings import get_ui_location, save_ui_location

        save_ui_location({"pane": "periods", "clientId": 1})
        save_ui_location(None)

        self.assertIsNone(get_ui_location())

    def test_junk_location_is_ignored(self) -> None:
        from apps.engine.settings import get_ui_location, save_ui_location

        save_ui_location("not-an-entry")

        self.assertIsNone(get_ui_location())

    def test_get_state_exposes_the_saved_location(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine.settings import save_ui_location

        save_ui_location({"pane": "periods", "clientId": 2})

        state = DesktopApi().get_state()

        self.assertEqual(state["ui_last_nav"], {"pane": "periods", "clientId": 2})

    def test_saving_through_the_bridge_stores_the_entry(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine.settings import get_ui_location

        result = DesktopApi().save_ui_location({"pane": "dump", "periodId": 9})

        self.assertTrue(result["ok"])
        self.assertEqual(get_ui_location(), {"pane": "dump", "periodId": 9})

    def test_bridge_rejects_non_object_payloads(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.engine.settings import get_ui_location, save_ui_location

        save_ui_location({"pane": "dump", "periodId": 4})
        DesktopApi().save_ui_location("garbage")

        self.assertIsNone(get_ui_location())


if __name__ == "__main__":
    unittest.main()
