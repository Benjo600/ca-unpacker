from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_PY = ROOT / "apps" / "desktop" / "app.py"
FROZEN_ENTRY = ROOT / "apps" / "desktop" / "frozen_entry.py"
SPEC = ROOT / "CAUnpacker.spec"


class DesktopImportTests(unittest.TestCase):
    def test_app_py_parses(self) -> None:
        source = APP_PY.read_text(encoding="utf-8")
        ast.parse(source, filename=str(APP_PY))

    def test_desktop_app_imports(self) -> None:
        from apps.desktop.app import DesktopApi, main

        self.assertTrue(callable(main))
        self.assertTrue(hasattr(DesktopApi, "start_dump"))
        self.assertTrue(hasattr(DesktopApi, "pick_folder"))
        self.assertTrue(hasattr(DesktopApi, "take_drop_paths"))
        self.assertTrue(hasattr(DesktopApi, "set_guide_dismissed"))

    def test_app_icon_files_exist(self) -> None:
        from apps.desktop.app import app_icon_path

        ico = ROOT / "apps" / "ui" / "app-icon.ico"
        png = ROOT / "apps" / "ui" / "app-icon.png"
        self.assertTrue(ico.is_file(), ico)
        self.assertTrue(png.is_file(), png)
        self.assertGreater(ico.stat().st_size, 1024)
        resolved = app_icon_path()
        self.assertIsNotNone(resolved)
        self.assertTrue(Path(resolved).is_file())

    def test_frozen_entry_calls_desktop_main(self) -> None:
        self.assertTrue(FROZEN_ENTRY.is_file(), FROZEN_ENTRY)
        source = FROZEN_ENTRY.read_text(encoding="utf-8")
        ast.parse(source, filename=str(FROZEN_ENTRY))
        self.assertIn("from apps.desktop.app import main", source)
        self.assertIn("main()", source)

    def test_landing_test_files_zip_has_scenarios(self) -> None:
        import zipfile

        from apps.engine.tests.dump_paths import LANDING_ZIP, ensure_sample_dump

        ensure_sample_dump()
        self.assertTrue(LANDING_ZIP.is_file(), LANDING_ZIP)
        with zipfile.ZipFile(LANDING_ZIP) as archive:
            names = archive.namelist()
        blob = " ".join(names)
        self.assertIn("01-banks-digital", blob)
        self.assertIn("07-mixed-client-month", blob)
        self.assertIn("README.md", blob)

    def test_spec_does_not_freeze_package_main(self) -> None:
        spec = SPEC.read_text(encoding="utf-8")
        self.assertIn("frozen_entry.py", spec)
        self.assertNotIn("__main__.py", spec)
        self.assertIn("apps.desktop.app", spec)
        self.assertIn("did not collect required modules", spec)
