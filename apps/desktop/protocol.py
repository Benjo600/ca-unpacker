"""Windows registration for the ``caunpacker://`` deep link.

The Inno Setup installer registers this scheme, but anyone running from source
-- or from a copied build -- has no handler, so the browser sign-in never gets
back to the app. Registering at startup makes the handoff work regardless of
how the app was installed. It is a per-user (HKCU) write, so no admin rights
are needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCHEME = "caunpacker"
_ROOT_KEY = rf"Software\Classes\{SCHEME}"
_COMMAND_KEY = rf"{_ROOT_KEY}\shell\open\command"
_DESCRIPTION = "URL:CA Unpacker Protocol"

# Path to the repo root when running from source: apps/desktop/protocol.py -> up 3.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _windowed_interpreter() -> str:
    """Prefer pythonw.exe so opening a deep link does not flash a console."""
    executable = Path(sys.executable)
    windowed = executable.with_name("pythonw.exe")
    return str(windowed if windowed.is_file() else executable)


def handler_command() -> str:
    """The command Windows should run for a caunpacker:// URL."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    # Windows launches protocol handlers from an arbitrary working directory,
    # so the repo root has to be injected for `-m apps.desktop` to import.
    return (
        f'"{_windowed_interpreter()}" -c '
        f'"import sys; sys.path.insert(0, r\'{_REPO_ROOT}\'); '
        f'from apps.desktop.app import main; main()" "%1"'
    )


def _write_registry_string(path: str, name: str, value: str) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _read_registered_command() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _COMMAND_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "")
    except OSError:
        return None
    return str(value) if value else None


def ensure_registered() -> bool:
    """Register the scheme if missing or stale. Returns True when it wrote.

    Never raises: a failure here must not stop the app from starting, since the
    in-app sign-in form still works without the browser handoff.
    """
    if sys.platform != "win32":
        return False
    try:
        desired = handler_command()
        if _read_registered_command() == desired:
            return False
        _write_registry_string(_ROOT_KEY, "", _DESCRIPTION)
        _write_registry_string(_ROOT_KEY, "URL Protocol", "")
        _write_registry_string(_COMMAND_KEY, "", desired)
        return True
    except Exception:
        return False
