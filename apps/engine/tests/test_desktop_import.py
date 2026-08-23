from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP_PY = ROOT / "apps" / "desktop" / "app.py"


class DesktopImportTests(unittest.TestCase):
    def test_app_py_parses(self) -> None:
        source = APP_PY.read_text(encoding="utf-8")
        ast.parse(source, filename=str(APP_PY))

    def test_desktop_app_imports(self) -> None:
        from apps.desktop.app import DesktopApi, main

        self.assertTrue(callable(main))
        self.assertTrue(hasattr(DesktopApi, "start_dump"))
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
