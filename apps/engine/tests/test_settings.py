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

    def test_corrupt_settings_file_degrades_to_empty(self) -> None:
        """A damaged settings.json must read as {} and be replaced, not raise."""
        import json

        from apps.engine.settings import (
            load_settings,
            save_settings,
            settings_path,
        )

        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"output_root": "D:/x"}{"extra": "data"}', encoding="utf-8")

        self.assertEqual(load_settings(), {})
        saved = save_settings({"guide_dismissed": True})
        self.assertEqual(saved, {"guide_dismissed": True})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"guide_dismissed": True})

    def test_concurrent_saves_keep_every_key(self) -> None:
        """8 threads x 20 saves must leave valid JSON holding all 160 keys.

        Before the lock + atomic replace this reproduced as
        ``json.JSONDecodeError: Extra data`` (or a parseable file that had
        silently lost all but a handful of keys).
        """
        import json
        import threading

        from apps.engine.settings import load_settings, save_settings, settings_path

        threads = 8
        per_thread = 20
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                for round_no in range(per_thread):
                    save_settings({f"key_{index}_{round_no}": round_no})
            except BaseException as exc:  # pragma: no cover - reported below
                errors.append(exc)

        pool = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
        for thread in pool:
            thread.start()
        for thread in pool:
            thread.join()

        self.assertEqual(errors, [])
        raw = settings_path().read_text(encoding="utf-8")
        on_disk = json.loads(raw)  # would raise on "Extra data"
        expected = {
            f"key_{index}_{round_no}"
            for index in range(threads)
            for round_no in range(per_thread)
        }
        self.assertEqual(set(on_disk), expected)
        self.assertEqual(set(load_settings()), expected)


if __name__ == "__main__":
    unittest.main()
