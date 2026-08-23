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
