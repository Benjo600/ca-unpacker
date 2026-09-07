from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ENV_KEYS = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "CA_UNPACKER_AUTH_URL")


def _clear_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _reload(monkeypatch, bundle_root: Path):
    """Reimport auth_config with its bundle root pointed at a temp dir."""
    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: bundle_root)
    return importlib.reload(auth_config)


def _write_config(directory: Path, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text(json.dumps(payload), encoding="utf-8")


def test_env_vars_win_over_bundled_config(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _write_config(tmp_path, {"supabase_url": "https://bundled.supabase.co"})
    monkeypatch.setenv("SUPABASE_URL", "https://from-env.supabase.co")

    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: tmp_path)
    assert auth_config.resolve_setting(
        "SUPABASE_URL", "supabase_url", "https://fallback.supabase.co"
    ) == "https://from-env.supabase.co"


def test_bundled_config_used_when_env_absent(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _write_config(tmp_path, {"supabase_url": "https://bundled.supabase.co"})

    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: tmp_path)
    auth_config.load_bundled_config.cache_clear()
    assert auth_config.resolve_setting(
        "SUPABASE_URL", "supabase_url", "https://fallback.supabase.co"
    ) == "https://bundled.supabase.co"


def test_falls_back_to_default_without_env_or_config(tmp_path, monkeypatch):
    _clear_env(monkeypatch)

    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: tmp_path)
    auth_config.load_bundled_config.cache_clear()
    assert auth_config.resolve_setting(
        "SUPABASE_URL", "supabase_url", "https://fallback.supabase.co"
    ) == "https://fallback.supabase.co"


def test_malformed_config_does_not_crash(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.json").write_text("{not valid json", encoding="utf-8")

    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: tmp_path)
    auth_config.load_bundled_config.cache_clear()
    assert auth_config.load_bundled_config() == {}
    assert auth_config.resolve_setting(
        "SUPABASE_URL", "supabase_url", "https://fallback.supabase.co"
    ) == "https://fallback.supabase.co"


def test_trailing_slashes_are_stripped(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://trailing.supabase.co/")

    from apps.engine import auth_config

    monkeypatch.setattr(auth_config, "_bundle_root", lambda: tmp_path)
    assert not auth_config.resolve_setting(
        "SUPABASE_URL", "supabase_url", "https://fallback.supabase.co"
    ).endswith("/")


def test_shipped_config_points_at_hosted_project():
    """The committed config.json must not ship localhost defaults to users."""
    config_path = ROOT / "apps" / "config.json"
    assert config_path.is_file(), "apps/config.json must exist for production builds"
    data = json.loads(config_path.read_text(encoding="utf-8"))

    url = str(data.get("supabase_url") or "")
    assert url.startswith("https://"), "hosted project must be https"
    assert "127.0.0.1" not in url and "localhost" not in url

    key = str(data.get("supabase_anon_key") or "")
    assert key, "anon key required so the app can reach the project"
    # Guard against ever shipping the service-role key, which bypasses RLS.
    assert "service_role" not in key


def test_module_constants_are_built_by_the_resolver(monkeypatch):
    """The exported constants must flow through resolve_setting, not bypass it."""
    from apps.engine import auth_config

    monkeypatch.setenv("SUPABASE_URL", "https://reloaded.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "reloaded-key")
    monkeypatch.setenv("CA_UNPACKER_AUTH_URL", "https://reloaded.netlify.app")
    try:
        reloaded = importlib.reload(auth_config)
        assert reloaded.SUPABASE_URL == "https://reloaded.supabase.co"
        assert reloaded.SUPABASE_ANON_KEY == "reloaded-key"
        assert reloaded.CA_UNPACKER_AUTH_URL == "https://reloaded.netlify.app"
    finally:
        # Restore the real module for any test importing it afterwards.
        monkeypatch.undo()
        auth_config.load_bundled_config.cache_clear()
        importlib.reload(auth_config)


def test_default_module_constants_use_the_shipped_config():
    """With no env override, the app must reach the hosted project, not localhost."""
    from apps.engine import auth_config

    for key in _ENV_KEYS:
        if os.environ.get(key):
            pytest.skip(f"{key} is set in this environment; default resolution untested")

    assert auth_config.SUPABASE_URL.startswith("https://")
    assert "127.0.0.1" not in auth_config.SUPABASE_URL
