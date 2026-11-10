"""Small external helper that installs a verified update after the app closes.

The app copies this helper into the version-specific update folder and starts
it with the current process id, the verified installer, and the installed app
path. The helper waits for the app to exit, re-checks the installer's size and
SHA-256 immediately before running it, installs silently, and reopens the app.

Nothing here talks to the network, and the helper refuses to run any installer
outside `%LOCALAPPDATA%\\CAUnpacker\\updates`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

UPDATE_FLAGS = (
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
)
OK_EXIT_CODES = frozenset({0, 3010})
DEFAULT_PARENT_TIMEOUT = 180.0
_CHUNK = 1024 * 1024


class UpdaterError(RuntimeError):
    pass


def update_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return (Path(base) / "CAUnpacker" / "updates").resolve()


def validate_installer_path(raw_path: str, expected_version: str = "") -> Path:
    """The installer must live under the update root and match the version."""
    path = Path(str(raw_path)).resolve()
    root = update_root()
    if path != root and root not in path.parents:
        raise UpdaterError("The installer is outside the update folder.")
    if path.suffix.lower() != ".exe":
        raise UpdaterError("The installer must be an .exe file.")
    if not path.is_file():
        raise UpdaterError("The installer file is missing.")
    if expected_version and expected_version not in path.name:
        raise UpdaterError("The installer does not match the expected version.")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_installer(
    path: Path, expected_size: int, expected_sha256: str
) -> None:
    if not path.is_file():
        raise UpdaterError("The installer file is missing.")
    size = path.stat().st_size
    if int(expected_size) <= 0 or size != int(expected_size):
        raise UpdaterError(
            f"The installer size is {size} bytes, expected {int(expected_size)}."
        )
    digest = sha256_file(path)
    if digest.lower() != str(expected_sha256 or "").strip().lower():
        raise UpdaterError("The installer fingerprint does not match.")
    if not digest.isalnum() or len(digest) != 64:
        raise UpdaterError("The installer fingerprint is malformed.")


def installer_command(installer: Path) -> list[str]:
    return [str(installer), *UPDATE_FLAGS]


def wait_for_parent(pid: int, timeout_seconds: float = DEFAULT_PARENT_TIMEOUT) -> None:
    """Wait until the desktop process with *pid* has exited."""
    if int(pid) <= 0:
        raise UpdaterError("The parent process id is missing.")
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, int(pid))
        if handle:
            try:
                remaining = max(0, int((deadline - time.monotonic()) * 1000))
                ctypes.windll.kernel32.WaitForSingleObject(handle, remaining)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            return
    while time.monotonic() < deadline:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return
        time.sleep(0.25)
    raise UpdaterError("The app did not close in time; the update was not installed.")


def run_installer(installer: Path, runner=subprocess.run) -> int:
    completed = runner(
        installer_command(installer),
        check=False,
        capture_output=True,
        text=True,
    )
    code = int(getattr(completed, "returncode", 1))
    if code not in OK_EXIT_CODES:
        raise UpdaterError(f"The installer stopped with code {code}.")
    return code


def launch_app(app_exe: Path) -> None:
    if not app_exe.is_file():
        raise UpdaterError("The installed app was not found after the update.")
    subprocess.Popen([str(app_exe)], cwd=str(app_exe.parent))


def write_log(folder: Path, message: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "updater.log"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")
    return log


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install a verified CA Unpacker update.")
    parser.add_argument("--installer", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--app-exe", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-size", required=True, type=int)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--parent-timeout", type=float, default=DEFAULT_PARENT_TIMEOUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        installer = validate_installer_path(args.installer, args.expected_version)
        verify_installer(installer, args.expected_size, args.expected_sha256)
    except UpdaterError as exc:
        write_log(update_root() / args.expected_version, f"refused: {exc}")
        return 3

    log_folder = installer.parent
    write_log(log_folder, f"starting update to {args.expected_version}")
    try:
        wait_for_parent(args.parent_pid, args.parent_timeout)
        run_installer(installer)
    except UpdaterError as exc:
        write_log(log_folder, f"update failed: {exc}")
        return 2
    except OSError as exc:
        write_log(log_folder, f"update failed: {exc}")
        return 2

    write_log(log_folder, "installer finished; reopening the app")
    try:
        launch_app(Path(args.app_exe).resolve())
    except (OSError, UpdaterError) as exc:
        write_log(log_folder, f"could not reopen the app: {exc}")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
