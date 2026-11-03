"""Contract tests for the single desktop application version source.

The version must be written in exactly one place (``apps/version.py``) and flow
from there into the desktop API and the Inno Setup build, so a published
installer can never disagree with what the running app reports.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPEC_PATH = ROOT / "CAUnpacker.spec"
ISS_PATH = ROOT / "installer" / "ca-unpacker.iss"
BUILD_PATH = ROOT / "build_installer.bat"

STRICT_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class AppVersionSourceTests(unittest.TestCase):
    def test_app_version_is_strict_major_minor_patch(self) -> None:
        from apps.version import APP_VERSION

        self.assertIsInstance(APP_VERSION, str)
        self.assertRegex(APP_VERSION, STRICT_SEMVER)


class DesktopStateVersionTests(unittest.TestCase):
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

    def test_get_state_reports_app_version_without_a_window(self) -> None:
        from apps.desktop.app import DesktopApi
        from apps.version import APP_VERSION

        state = DesktopApi().get_state()

        self.assertEqual(state["app_version"], APP_VERSION)


class InstallerVersionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.iss = ISS_PATH.read_text(encoding="utf-8")

    def test_installer_has_no_hardcoded_version_define(self) -> None:
        self.assertIsNone(
            re.search(r'#define\s+\w*Version\s+"\d+\.\d+\.\d+"', self.iss),
            "installer/ca-unpacker.iss must not hardcode a version",
        )

    def test_installer_requires_version_from_command_line(self) -> None:
        self.assertIn("#ifndef AppVersion", self.iss)
        self.assertIn("#error", self.iss)
        self.assertIn("#endif", self.iss)
        self.assertIn("AppVersion={#AppVersion}", self.iss)


class BuildScriptVersionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.build = BUILD_PATH.read_text(encoding="utf-8")

    def test_build_reads_version_from_apps_version(self) -> None:
        self.assertIn("apps.version", self.build)
        self.assertIn("APP_VERSION", self.build)

    def test_build_passes_version_define_to_iscc(self) -> None:
        self.assertIn("/DAppVersion=", self.build)


class PyInstallerSpecVersionTests(unittest.TestCase):
    def test_spec_bundles_apps_version(self) -> None:
        spec = SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn("apps.version", spec)


if __name__ == "__main__":
    unittest.main()
