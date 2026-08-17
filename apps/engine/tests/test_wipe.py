from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class WipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_wipe_removes_clients_and_files(self) -> None:
        from apps.engine.clients import create_client, list_clients
        from apps.engine.firm import get_firm, save_firm
        from apps.engine.library import get_library_path, init_library
        from apps.engine.wipe import wipe_all

        save_firm("Temp firm")
        create_client("Temp client")
        marker = init_library() / "files" / "marker.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("x", encoding="utf-8")
        self.assertTrue(get_library_path().exists())
        self.assertEqual(len(list_clients()), 1)

        wipe_all()
        self.assertFalse(get_library_path().exists())
        self.assertIsNone(get_firm())
        self.assertEqual(list_clients(), [])


if __name__ == "__main__":
    unittest.main()
