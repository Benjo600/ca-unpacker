from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_offline_grace_allows_within_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    auth.save_quota_cache(
        {
            "files_used": 10,
            "file_limit": 100,
            "plan": "starter",
            "synced_at": "2026-09-01T10:00:00",
        }
    )
    auth.check_can_ingest_offline(5, today=date(2026, 9, 7))


def test_offline_grace_blocks_after_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    auth.save_quota_cache(
        {
            "files_used": 10,
            "file_limit": 100,
            "plan": "starter",
            "synced_at": "2026-08-25T10:00:00",
        }
    )
    with pytest.raises(ValueError, match="Connect to the internet"):
        auth.check_can_ingest_offline(1, today=date(2026, 9, 3))


def test_fingerprint_is_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import device_fingerprint

    assert device_fingerprint() == device_fingerprint()
    assert len(device_fingerprint()) == 64


def test_license_delegates_when_session_present(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("CA_UNPACKER_DEV", "1")
    monkeypatch.setattr(
        "apps.engine.auth.get_auth_state",
        lambda: {
            "signed_in": True,
            "plan": "pro",
            "files_used": 0,
            "file_limit": None,
            "email": "owner@example.com",
            "offline": False,
            "last_sync_at": "2026-09-01T10:00:00",
        },
    )
    from apps.engine.license import get_license_status

    status = get_license_status()
    assert status["plan"] == "pro"
    assert status["auth_mode"] == "supabase"


def test_refresh_token_is_encrypted_in_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import get_session, login_via_tokens
    from apps.engine.settings import load_settings

    login_via_tokens("header.payload.sig", "refresh-token-plain")
    stored = load_settings()
    assert stored.get("auth_refresh_token_enc")
    assert stored.get("auth_refresh_token_enc") != "refresh-token-plain"
    session = get_session()
    assert session is not None
    assert session["refresh_token"] == "refresh-token-plain"


def test_rejects_document_keys_in_request_body(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import _reject_document_keys

    with pytest.raises(ValueError, match="document"):
        _reject_document_keys({"file_count": 1, "invoice_rows": []})


def test_login_with_password_requires_email_and_password(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import login_with_password

    with pytest.raises(ValueError, match="Enter your email"):
        login_with_password("", "secret")
    with pytest.raises(ValueError, match="Enter your email"):
        login_with_password("office@firm.in", "")


def test_sign_up_validates_name_email_and_password(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import sign_up

    with pytest.raises(ValueError, match="full name"):
        sign_up("", "office@firm.in", "password1", "password1")
    with pytest.raises(ValueError, match="valid email"):
        sign_up("Darshan Shah", "not-an-email", "password1", "password1")
    with pytest.raises(ValueError, match="do not match"):
        sign_up("Darshan Shah", "office@firm.in", "password1", "password2")
    with pytest.raises(ValueError, match="8 characters"):
        sign_up("Darshan Shah", "office@firm.in", "short", "short")


def test_request_password_reset_requires_valid_email(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import request_password_reset

    with pytest.raises(ValueError, match="valid email"):
        request_password_reset("not-an-email")


def test_recovery_tokens_mark_password_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("apps.engine.auth._network_available", lambda: False)
    from apps.engine.auth import get_auth_state, login_via_tokens

    login_via_tokens("header.payload.sig", "refresh-token-plain", recovery=True)
    assert get_auth_state()["password_recovery"] is True
