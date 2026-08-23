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


if __name__ == "__main__":
    unittest.main()
