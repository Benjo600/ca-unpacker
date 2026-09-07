from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.desktop import protocol  # noqa: E402


def test_frozen_command_points_at_the_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\CA Unpacker\CAUnpacker.exe")

    command = protocol.handler_command()

    assert command == '"C:\\Program Files\\CA Unpacker\\CAUnpacker.exe" "%1"'


def test_source_command_prefers_the_windowed_interpreter(tmp_path, monkeypatch):
    """pythonw.exe avoids a console window flashing on every deep link."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    command = protocol.handler_command()

    assert "pythonw.exe" in command
    # Must carry the repo root, or the import cannot resolve from the arbitrary
    # working directory Windows launches a protocol handler in.
    assert str(ROOT) in command
    assert command.endswith('"%1"')


def test_source_command_falls_back_when_no_windowed_interpreter(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    command = protocol.handler_command()

    assert "python.exe" in command
    assert command.endswith('"%1"')


def test_registration_is_skipped_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert protocol.ensure_registered() is False


def test_registration_writes_expected_registry_values(monkeypatch):
    written: dict[str, str] = {}

    def fake_write(path: str, name: str, value: str) -> None:
        written[f"{path}::{name}"] = value

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(protocol, "_read_registered_command", lambda: None)
    monkeypatch.setattr(protocol, "_write_registry_string", fake_write)

    assert protocol.ensure_registered() is True

    assert written[r"Software\Classes\caunpacker::"] == "URL:CA Unpacker Protocol"
    assert r"Software\Classes\caunpacker::URL Protocol" in written
    assert written[r"Software\Classes\caunpacker\shell\open\command::"].endswith('"%1"')


def test_registration_is_skipped_when_already_correct(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(protocol, "_read_registered_command", protocol.handler_command)
    monkeypatch.setattr(
        protocol,
        "_write_registry_string",
        lambda *a: calls.append("written"),
    )

    assert protocol.ensure_registered() is False
    assert calls == [], "must not rewrite the registry when already correct"


def test_registration_rewrites_a_stale_command(monkeypatch):
    """A moved or reinstalled app must repoint the handler at itself."""
    calls: list[str] = []

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        protocol, "_read_registered_command", lambda: '"C:\\old\\gone.exe" "%1"'
    )
    monkeypatch.setattr(
        protocol, "_write_registry_string", lambda *a: calls.append("written")
    )

    assert protocol.ensure_registered() is True
    assert calls, "stale handler command should be rewritten"


def test_failure_to_register_never_raises(monkeypatch):
    """A locked-down registry must not stop the app from starting."""

    def boom(*args, **kwargs):
        raise OSError("access denied")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(protocol, "_read_registered_command", lambda: None)
    monkeypatch.setattr(protocol, "_write_registry_string", boom)

    assert protocol.ensure_registered() is False
