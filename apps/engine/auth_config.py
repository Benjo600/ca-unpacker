from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

# Local Supabase CLI defaults; used only when no env var and no bundled config
# supply a value. Shipped builds carry apps/config.json, so end users reach the
# hosted Supabase project for direct email/password auth (no separate web signup site).
_DEFAULT_SUPABASE_URL = "http://127.0.0.1:54321"
_DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)
# Legacy: only used for old web redirect flow (now removed in favor of in-app Supabase auth).
_DEFAULT_AUTH_URL = "http://127.0.0.1:5173"

_CONFIG_FILENAME = "config.json"


def _bundle_root() -> Path:
    """Where bundled data lives: the PyInstaller temp dir when frozen, else apps/."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_bundled_config() -> dict:
    """Read the shipped config.json. Never raises — a bad file falls back to defaults."""
    try:
        path = _bundle_root() / _CONFIG_FILENAME
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_setting(env_name: str, config_key: str, default: str) -> str:
    """Resolve in order: environment variable, bundled config.json, built-in default."""
    value = os.environ.get(env_name)
    if not value:
        value = load_bundled_config().get(config_key)
    if not value:
        value = default
    return str(value).rstrip("/")


SUPABASE_URL = resolve_setting("SUPABASE_URL", "supabase_url", _DEFAULT_SUPABASE_URL)
SUPABASE_ANON_KEY = resolve_setting(
    "SUPABASE_ANON_KEY", "supabase_anon_key", _DEFAULT_SUPABASE_ANON_KEY
)
# Legacy web auth site (no longer used — auth is direct Supabase email/password + DB trigger)
CA_UNPACKER_AUTH_URL = resolve_setting(
    "CA_UNPACKER_AUTH_URL", "auth_url", _DEFAULT_AUTH_URL
)
