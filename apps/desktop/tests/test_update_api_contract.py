"""Contract tests for the desktop update bridge and the mandatory update gate.

Everything here is offline: the update service seam (``apps.engine.updates``)
is monkeypatched, and the app data folder is a throwaway ``LOCALAPPDATA``.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

VERSION = "9.9.9"
PAYLOAD = b"verified installer bytes for the contract tests"
UPDATE_KEYS = {
    "status",
    "version",
    "title",
    "notes",
    "mandatory",
    "progress",
    "error",
    "available",
}
MANDATORY_MESSAGE = (
    "A required CA Unpacker update must be installed before processing more files."
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_dict(**overrides) -> dict:
    data = {
        "version": VERSION,
        "title": "CA Unpacker 9.9.9",
        "release_notes": "Faster parsing and a clearer bank preview.",
        "installer_url": (
            "https://github.com/caunpacker/releases/download/"
            f"v{VERSION}/CAUnpacker-Setup-{VERSION}.exe"
        ),
        "installer_sha256": _sha(PAYLOAD),
        "installer_size": len(PAYLOAD),
        "mandatory": False,
        "published_at": "2026-10-30T09:00:00",
    }
    data.update(overrides)
    return data


def _available_state(mandatory: bool = False):
    from apps.engine import updates

    return updates.UpdateState(
        status="available",
        version=VERSION,
        title="CA Unpacker 9.9.9",
        notes="Faster parsing and a clearer bank preview.",
        mandatory=mandatory,
        installer_sha256=_sha(PAYLOAD),
        installer_size=len(PAYLOAD),
    )


class FakeWindow:
    def __init__(self) -> None:
        self.destroyed = 0

    def destroy(self) -> None:
        self.destroyed += 1


class UpdateApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        os.environ.pop("CA_UNPACKER_DEV", None)

        from apps.engine.db import reset_engine

        reset_engine()

        import apps.desktop.app as app_module

        self.app = app_module
        self._original_window = app_module._WINDOW
        app_module._WINDOW = None
        self._reset_controller()
        self.api = app_module.DesktopApi()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self.app._WINDOW = self._original_window
        self._reset_controller()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    # -- helpers ---------------------------------------------------------

    def _reset_controller(self) -> None:
        self.app._UPDATE_CONTROLLER = None

    def _controller(self):
        return self.app.update_controller()

    def _assert_safe_payload(self, result: dict) -> dict:
        self.assertIn("ok", result)
        self.assertNotIn("path", result)
        self.assertNotIn("downloaded_path", result)
        update = result["update"]
        self.assertEqual(set(update), UPDATE_KEYS)
        blob = repr(result).lower()
        for banned in (
            "localappdata",
            "appdata",
            "c:\\",
            "token",
            "sha256",
            ".exe",
            "manifest",
        ):
            self.assertNotIn(banned, blob)
        self.assertIsInstance(update["available"], bool)
        self.assertIsInstance(update["mandatory"], bool)
        self.assertIsInstance(update["progress"], float)
        return update

    def _become_available(self, mandatory: bool = False):
        from apps.engine import updates

        with patch.object(
            updates, "check_for_update", return_value=_available_state(mandatory)
        ), patch.object(
            updates,
            "load_update_cache",
            return_value={"manifest": _manifest_dict(mandatory=mandatory)},
        ):
            self.api.get_update_state(force_check=True)
            self.assertTrue(self._controller().wait_idle())
        state = self.api.get_update_state()
        self.assertEqual(state["update"]["status"], "available")
        return state

    def _fake_download(self, manifest, progress_callback=None, cancel_event=None, *, client=None):
        """Stand-in for updates.download_update that writes a verified-looking file."""

        folder = Path(self._tmp.name) / "CAUnpacker" / "updates" / manifest.version
        folder.mkdir(parents=True, exist_ok=True)
        final = folder / f"CAUnpacker-Setup-{manifest.version}.exe"
        for step in (0.2, 0.6, 1.0):
            if cancel_event is not None and cancel_event.is_set():
                from apps.engine import updates

                raise updates.UpdateCancelled("Update download cancelled.")
            if progress_callback is not None:
                progress_callback(step)
            time.sleep(0.01)
        final.write_bytes(PAYLOAD)
        return final

    def _become_ready(self):
        from apps.engine import updates

        self._become_available()
        with patch.object(updates, "download_update", side_effect=self._fake_download):
            result = self.api.download_update()
            self.assertTrue(result["ok"])
            self.assertEqual(result["update"]["status"], "downloading")
            self.assertTrue(self._controller().wait_idle())
        state = self.api.get_update_state()
        self.assertEqual(state["update"]["status"], "ready")
        self.assertEqual(state["update"]["progress"], 1.0)
        return state

    def _write_release_cache(self, mandatory: bool) -> None:
        from apps.engine import updates
        from apps.version import APP_VERSION

        updates.save_update_cache(
            {
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "current_version": APP_VERSION,
                "manifest": _manifest_dict(mandatory=mandatory),
            }
        )

    def _job_count(self) -> int:
        from sqlalchemy import text

        from apps.engine.db import get_engine

        with get_engine().connect() as connection:
            return int(connection.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one())

    # -- state shape -----------------------------------------------------

    def test_idle_state_is_safe_and_shaped(self) -> None:
        result = self.api.get_update_state()
        update = self._assert_safe_payload(result)
        self.assertTrue(result["ok"])
        self.assertEqual(update["status"], "idle")
        self.assertFalse(update["available"])
        self.assertEqual(update["error"], "")

    def test_available_state_is_safe_and_shaped(self) -> None:
        result = self._become_available()
        update = self._assert_safe_payload(result)
        self.assertTrue(result["ok"])
        self.assertTrue(update["available"])
        self.assertEqual(update["version"], VERSION)
        self.assertFalse(update["mandatory"])

    def test_error_state_is_safe_and_reported(self) -> None:
        from apps.engine import updates

        with patch.object(
            updates,
            "check_for_update",
            side_effect=RuntimeError("boom"),
        ):
            self.api.get_update_state(force_check=True)
            self.assertTrue(self._controller().wait_idle())
        result = self.api.get_update_state()
        update = self._assert_safe_payload(result)
        self.assertFalse(result["ok"])
        self.assertEqual(update["status"], "error")
        self.assertFalse(update["available"])
        self.assertIn("internet connection", update["error"])
        self.assertEqual(result["error"], update["error"])

    # -- one worker at a time --------------------------------------------

    def test_second_check_while_busy_does_not_start_another_worker(self) -> None:
        from apps.engine import updates

        started = threading.Event()
        release = threading.Event()
        calls: list[bool] = []

        def slow_check(force: bool = False):
            calls.append(force)
            started.set()
            release.wait(5)
            return updates.UpdateState()

        with patch.object(updates, "check_for_update", side_effect=slow_check):
            first = self.api.get_update_state(force_check=True)
            self.assertTrue(started.wait(5))
            second = self.api.get_update_state(force_check=True)
            self.assertTrue(second["ok"])
            self.assertEqual(second["update"]["status"], "checking")
            release.set()
            self.assertTrue(self._controller().wait_idle())

        self.assertEqual(first["update"]["status"], "checking")
        self.assertEqual(len(calls), 1)

    # -- download --------------------------------------------------------

    def test_download_reaches_ready_with_progress(self) -> None:
        from apps.engine import updates

        seen: list[float] = []

        def tracking_download(manifest, progress_callback=None, cancel_event=None, *, client=None):
            original = self._fake_download

            def report(step: float) -> None:
                seen.append(step)
                if progress_callback is not None:
                    progress_callback(step)

            return original(manifest, report, cancel_event, client=client)

        self._become_available()
        with patch.object(updates, "download_update", side_effect=tracking_download):
            result = self.api.download_update()
            self.assertTrue(result["ok"])
            self.assertEqual(result["update"]["status"], "downloading")
            self.assertTrue(self._controller().wait_idle())

        state = self.api.get_update_state()
        self._assert_safe_payload(state)
        self.assertEqual(state["update"]["status"], "ready")
        self.assertEqual(state["update"]["progress"], 1.0)
        self.assertTrue(state["update"]["available"])
        self.assertGreaterEqual(len(seen), 2)
        self.assertTrue(seen[-1] <= 1.0)
        final = (
            Path(self._tmp.name)
            / "CAUnpacker"
            / "updates"
            / VERSION
            / f"CAUnpacker-Setup-{VERSION}.exe"
        )
        self.assertTrue(final.is_file())

    def test_cancel_returns_to_available_without_a_file(self) -> None:
        from apps.engine import updates

        def waiting_download(manifest, progress_callback=None, cancel_event=None, *, client=None):
            if progress_callback is not None:
                progress_callback(0.05)
            if cancel_event is not None and cancel_event.wait(5):
                raise updates.UpdateCancelled("Update download cancelled.")
            return Path(self._tmp.name) / "should-not-exist.exe"

        self._become_available()
        with patch.object(updates, "download_update", side_effect=waiting_download):
            result = self.api.download_update()
            self.assertEqual(result["update"]["status"], "downloading")
            cancelled = self.api.cancel_update_download()
            self.assertTrue(cancelled["ok"])
            self.assertTrue(self._controller().wait_idle())

        state = self.api.get_update_state()
        self._assert_safe_payload(state)
        self.assertEqual(state["update"]["status"], "available")
        self.assertTrue(state["update"]["available"])
        self.assertEqual(state["update"]["error"], "Update download cancelled.")
        self.assertEqual(state["update"]["progress"], 0.0)
        folder = Path(self._tmp.name) / "CAUnpacker" / "updates" / VERSION
        leftovers = list(folder.glob("*.exe")) if folder.exists() else []
        self.assertEqual(leftovers, [])

    def test_cancel_without_a_download_is_refused(self) -> None:
        result = self.api.cancel_update_download()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "No update download is running.")

    # -- install ---------------------------------------------------------

    def test_install_before_ready_is_refused(self) -> None:
        result = self.api.install_update()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "The update has not been downloaded yet.")
        self._assert_safe_payload(result)

    def test_install_in_source_mode_explains_it_cannot(self) -> None:
        window = FakeWindow()
        self.app._WINDOW = window
        self._become_ready()
        result = self.api.install_update()
        self.assertFalse(result["ok"])
        self.assertIn("packaged CA Unpacker app", result["error"])
        self.assertEqual(window.destroyed, 0)
        self.assertEqual(self.api.get_update_state()["update"]["status"], "ready")

    def test_install_in_frozen_mode_copies_helper_and_launches_it(self) -> None:
        app_dir = Path(self._tmp.name) / "installed"
        app_dir.mkdir()
        app_exe = app_dir / "CAUnpacker.exe"
        app_exe.write_bytes(b"app")
        helper = app_dir / "CAUnpackerUpdater.exe"
        helper.write_bytes(b"helper")

        window = FakeWindow()
        self.app._WINDOW = window
        self._become_ready()

        installer = (
            Path(self._tmp.name)
            / "CAUnpacker"
            / "updates"
            / VERSION
            / f"CAUnpacker-Setup-{VERSION}.exe"
        )
        copied_helper = installer.parent / "CAUnpackerUpdater.exe"

        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", str(app_exe)
        ), patch("apps.desktop.app.subprocess.Popen") as popen:
            result = self.api.install_update()

        self.assertTrue(result["ok"])
        self.assertEqual(result["update"]["status"], "installing")
        self.assertTrue(result["update"]["available"])
        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(
            command,
            [
                str(copied_helper),
                "--installer",
                str(installer),
                "--parent-pid",
                str(os.getpid()),
                "--app-exe",
                str(app_exe),
                "--expected-version",
                VERSION,
                "--expected-size",
                str(len(PAYLOAD)),
                "--expected-sha256",
                _sha(PAYLOAD),
            ],
        )
        self.assertTrue(copied_helper.is_file())
        self.assertEqual(copied_helper.read_bytes(), b"helper")
        self.assertEqual(window.destroyed, 1)

    def test_install_keeps_the_window_when_the_helper_cannot_start(self) -> None:
        app_dir = Path(self._tmp.name) / "installed"
        app_dir.mkdir()
        app_exe = app_dir / "CAUnpacker.exe"
        app_exe.write_bytes(b"app")
        (app_dir / "CAUnpackerUpdater.exe").write_bytes(b"helper")

        window = FakeWindow()
        self.app._WINDOW = window
        self._become_ready()

        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", str(app_exe)
        ), patch(
            "apps.desktop.app.subprocess.Popen", side_effect=OSError("no access")
        ):
            result = self.api.install_update()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Could not start the update helper. CA Unpacker is still open.")
        self.assertEqual(window.destroyed, 0)
        self.assertIs(self.app._WINDOW, window)

    def test_install_refuses_a_damaged_installer(self) -> None:
        app_dir = Path(self._tmp.name) / "installed"
        app_dir.mkdir()
        app_exe = app_dir / "CAUnpacker.exe"
        app_exe.write_bytes(b"app")
        (app_dir / "CAUnpackerUpdater.exe").write_bytes(b"helper")

        self._become_ready()
        installer = (
            Path(self._tmp.name)
            / "CAUnpacker"
            / "updates"
            / VERSION
            / f"CAUnpacker-Setup-{VERSION}.exe"
        )
        installer.write_bytes(b"tampered")

        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", str(app_exe)
        ), patch("apps.desktop.app.subprocess.Popen") as popen:
            result = self.api.install_update()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "The downloaded update is damaged. Download it again.")
        popen.assert_not_called()
        self.assertEqual(self.api.get_update_state()["update"]["status"], "available")

    # -- mandatory gate --------------------------------------------------

    def test_mandatory_update_blocks_start_dump_and_reparse(self) -> None:
        self._write_release_cache(mandatory=True)
        self.assertEqual(self._job_count(), 0)

        with patch.object(self.app, "preflight_paths") as preflight, patch.object(
            self.app, "assert_can_ingest"
        ) as quota, patch.object(self.app, "start_job") as start_job:
            blocked = self.api.start_dump(1, [str(Path(self._tmp.name) / "a.pdf")])
            reparsed = self.api.reparse_period(1)

        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["error"], MANDATORY_MESSAGE)
        self.assertFalse(reparsed["ok"])
        self.assertEqual(reparsed["error"], MANDATORY_MESSAGE)
        preflight.assert_not_called()
        quota.assert_not_called()
        start_job.assert_not_called()
        self.assertEqual(self._job_count(), 0)

    def test_optional_update_does_not_block_start_dump(self) -> None:
        self._write_release_cache(mandatory=False)
        sample = Path(self._tmp.name) / "bill.txt"
        sample.write_text("x", encoding="utf-8")

        with patch.object(self.app, "assert_can_ingest"), patch.object(
            self.app, "start_job", return_value={"id": 7}
        ) as start_job, patch.object(self.app, "_run_job_thread"):
            result = self.api.start_dump(1, [str(sample)])

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], 7)
        start_job.assert_called_once_with(1)

    def test_no_known_update_does_not_block_start_dump(self) -> None:
        sample = Path(self._tmp.name) / "bill.txt"
        sample.write_text("x", encoding="utf-8")

        with patch.object(self.app, "assert_can_ingest"), patch.object(
            self.app, "start_job", return_value={"id": 3}
        ), patch.object(self.app, "_run_job_thread"):
            result = self.api.start_dump(1, [str(sample)])

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], 3)

    def test_existing_pack_access_survives_a_pending_mandatory_update(self) -> None:
        self._write_release_cache(mandatory=True)
        with patch.object(
            self.app, "open_pack_folder", return_value=str(Path(self._tmp.name) / "pack")
        ) as opener, patch.object(self.app, "_open_path"):
            result = self.api.open_pack_folder(1)
        self.assertTrue(result["ok"])
        opener.assert_called_once_with(1)

    def test_mandatory_update_still_allows_licence_and_logout(self) -> None:
        self._write_release_cache(mandatory=True)
        status = self.api.get_state()
        self.assertIn("license", status)
        with patch("apps.engine.auth._network_available", return_value=False):
            logged_out = self.api.logout()
        self.assertTrue(logged_out["ok"])

    # -- signed out ------------------------------------------------------

    def test_signed_out_check_reports_instead_of_raising(self) -> None:
        from apps.engine import updates

        with patch.object(
            updates,
            "check_for_update",
            side_effect=ValueError("Sign in to check for updates."),
        ):
            self.api.get_update_state(force_check=True)
            self.assertTrue(self._controller().wait_idle())

        result = self.api.get_update_state()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Sign in to check for updates.")
        self.assertEqual(result["update"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
