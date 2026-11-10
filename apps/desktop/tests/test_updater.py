from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

VERSION = "0.11.0"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.desktop import updater

        self.updater = updater
        self.root = updater.update_root()
        self.folder = self.root / VERSION
        self.folder.mkdir(parents=True)
        self.payload = b"verified installer bytes"
        self.installer = self.folder / f"CAUnpacker-Setup-{VERSION}.exe"
        self.installer.write_bytes(self.payload)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        if self._original is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original

    def test_update_root_lives_under_local_app_data(self) -> None:
        self.assertEqual(self.root.name, "updates")
        self.assertIn("CAUnpacker", str(self.root))
        self.assertTrue(str(self.root).startswith(str(Path(self._tmp.name).resolve())))

    def test_installer_path_must_stay_inside_the_update_root(self) -> None:
        outside = Path(self._tmp.name) / "elsewhere.exe"
        outside.write_bytes(b"x")
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.validate_installer_path(str(outside), VERSION)

        wrong_name = self.folder / "something-else.exe"
        wrong_name.write_bytes(b"x")
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.validate_installer_path(str(wrong_name), VERSION)

        self.assertEqual(
            self.updater.validate_installer_path(str(self.installer), VERSION),
            self.installer.resolve(),
        )

    def test_missing_installer_is_refused(self) -> None:
        missing = self.folder / f"CAUnpacker-Setup-{VERSION}.exe"
        missing.unlink()
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.validate_installer_path(str(missing), VERSION)

    def test_verify_accepts_matching_size_and_fingerprint(self) -> None:
        self.updater.verify_installer(self.installer, len(self.payload), _sha(self.payload))

    def test_verify_rejects_wrong_size_or_fingerprint(self) -> None:
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.verify_installer(self.installer, len(self.payload) + 1, _sha(self.payload))
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.verify_installer(self.installer, len(self.payload), "0" * 64)

    def test_installer_command_uses_silent_flags(self) -> None:
        command = self.updater.installer_command(self.installer)
        self.assertEqual(command[0], str(self.installer))
        for flag in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"):
            self.assertIn(flag, command)

    def test_run_installer_accepts_zero_and_rejects_failure(self) -> None:
        class Completed:
            def __init__(self, code: int) -> None:
                self.returncode = code

        self.assertEqual(
            self.updater.run_installer(self.installer, runner=lambda *a, **k: Completed(0)), 0
        )
        self.assertEqual(
            self.updater.run_installer(self.installer, runner=lambda *a, **k: Completed(3010)), 3010
        )
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.run_installer(self.installer, runner=lambda *a, **k: Completed(1))

    def test_wait_for_parent_returns_when_the_process_exits(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows process handle path")
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
        try:
            self.updater.wait_for_parent(child.pid, timeout_seconds=10)
        finally:
            child.wait(timeout=10)

    def test_wait_for_parent_rejects_a_missing_id(self) -> None:
        with self.assertRaises(self.updater.UpdaterError):
            self.updater.wait_for_parent(0, timeout_seconds=1)

    def test_main_installs_and_reopens_after_verification(self) -> None:
        app_exe = Path(self._tmp.name) / "CAUnpacker.exe"
        app_exe.write_bytes(b"app")
        args = [
            "--installer",
            str(self.installer),
            "--parent-pid",
            "1234",
            "--app-exe",
            str(app_exe),
            "--expected-version",
            VERSION,
            "--expected-size",
            str(len(self.payload)),
            "--expected-sha256",
            _sha(self.payload),
        ]
        with patch.object(self.updater, "wait_for_parent") as waiter, patch.object(
            self.updater, "run_installer", return_value=0
        ) as runner, patch.object(self.updater, "launch_app") as launcher:
            code = self.updater.main(args)

        self.assertEqual(code, 0)
        waiter.assert_called_once()
        runner.assert_called_once()
        launcher.assert_called_once()
        log = self.folder / "updater.log"
        self.assertTrue(log.is_file())
        self.assertNotIn("token", log.read_text(encoding="utf-8").lower())

    def test_main_refuses_a_bad_fingerprint_before_running_anything(self) -> None:
        args = [
            "--installer",
            str(self.installer),
            "--parent-pid",
            "1234",
            "--app-exe",
            str(Path(self._tmp.name) / "CAUnpacker.exe"),
            "--expected-version",
            VERSION,
            "--expected-size",
            str(len(self.payload)),
            "--expected-sha256",
            "f" * 64,
        ]
        with patch.object(self.updater, "run_installer") as runner, patch.object(
            self.updater, "wait_for_parent"
        ) as waiter:
            code = self.updater.main(args)

        self.assertEqual(code, 3)
        runner.assert_not_called()
        waiter.assert_not_called()

    def test_main_keeps_the_installer_when_the_installer_fails(self) -> None:
        app_exe = Path(self._tmp.name) / "CAUnpacker.exe"
        app_exe.write_bytes(b"app")
        args = [
            "--installer",
            str(self.installer),
            "--parent-pid",
            "1234",
            "--app-exe",
            str(app_exe),
            "--expected-version",
            VERSION,
            "--expected-size",
            str(len(self.payload)),
            "--expected-sha256",
            _sha(self.payload),
        ]
        with patch.object(self.updater, "wait_for_parent"), patch.object(
            self.updater, "run_installer", side_effect=self.updater.UpdaterError("boom")
        ), patch.object(self.updater, "launch_app") as launcher:
            code = self.updater.main(args)

        self.assertEqual(code, 2)
        self.assertTrue(self.installer.is_file())
        launcher.assert_not_called()
        self.assertIn("update failed", (self.folder / "updater.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
