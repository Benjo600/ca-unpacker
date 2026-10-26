from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class OutputFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_period_output_under_chosen_folder(self) -> None:
        from apps.engine.settings import period_output_dir, set_output_root

        chosen = Path(self._tmp.name) / "My CA Outputs"
        set_output_root(str(chosen))
        dest = period_output_dir("Mehta Trading Co", "Jul 2026")
        self.assertTrue(str(dest).startswith(str(chosen)))
        self.assertTrue(dest.exists())
        self.assertEqual(dest.name, "Jul 2026")

    def test_output_root_recreated_when_folder_disappears(self) -> None:
        """A recorded folder that vanished must come back, not re-ask setup."""
        import shutil

        from apps.engine.settings import get_output_root, set_output_root

        chosen = Path(self._tmp.name) / "Bills Output"
        set_output_root(str(chosen))
        self.assertTrue(chosen.exists())

        shutil.rmtree(chosen)
        self.assertEqual(get_output_root(), chosen)
        self.assertTrue(chosen.exists())

    def test_guide_dismissed_persists(self) -> None:
        from apps.engine.settings import is_guide_dismissed, set_guide_dismissed

        self.assertFalse(is_guide_dismissed())
        set_guide_dismissed(True)
        self.assertTrue(is_guide_dismissed())
        set_guide_dismissed(False)
        self.assertFalse(is_guide_dismissed())


if __name__ == "__main__":
    unittest.main()
