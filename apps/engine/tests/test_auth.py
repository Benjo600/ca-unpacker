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


def _fake_access_token(email: str = "owner@example.com") -> str:
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps({"email": email}).encode("utf-8"))
    return "header." + payload.decode("ascii").rstrip("=") + ".sig"


def _http_status_error(status_code: int, payload: dict):
    import httpx

    request = httpx.Request("POST", "https://example.supabase.co/auth/v1/token")
    response = httpx.Response(status_code, json=payload, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_password_body_is_not_rejected_as_document_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import _reject_document_keys

    _reject_document_keys({"email": "owner@example.com", "password": "hunter22"})


def test_sign_in_with_password_stores_encrypted_refresh_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth
    from apps.engine.settings import load_settings

    calls: list[tuple[str, dict]] = []

    def fake_post(path, body, session=None):
        calls.append((path, body))
        return {
            "access_token": _fake_access_token("owner@example.com"),
            "refresh_token": "refresh-token-plain",
        }

    monkeypatch.setattr(auth, "_post_auth", fake_post)
    monkeypatch.setattr(auth, "_network_available", lambda: True)

    state = auth.sign_in_with_password("owner@example.com", "hunter22")

    assert state["signed_in"] is True
    assert state["email"] == "owner@example.com"
    assert calls[0][0] == "/auth/v1/token?grant_type=password"
    assert calls[0][1] == {"email": "owner@example.com", "password": "hunter22"}
    stored = load_settings()
    assert stored.get("auth_refresh_token_enc")
    assert stored.get("auth_refresh_token_enc") != "refresh-token-plain"


def test_sign_in_with_wrong_password_raises_plain_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise _http_status_error(
            400,
            {"error": "invalid_grant", "error_description": "Invalid login credentials"},
        )

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="Email or password is incorrect."):
        auth.sign_in_with_password("owner@example.com", "wrong")


def test_sign_in_rate_limited_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise _http_status_error(429, {"message": "Request rate limit reached"})

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="Too many attempts"):
        auth.sign_in_with_password("owner@example.com", "hunter22")


def test_sign_in_network_error_surfaces_connection_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import httpx

    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="Could not reach the server"):
        auth.sign_in_with_password("owner@example.com", "hunter22")


def test_sign_up_without_tokens_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        assert path == "/auth/v1/signup"
        return {"user": {"id": "abc", "email": "new@example.com"}, "session": None}

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    result = auth.sign_up_with_password("new@example.com", "hunter22")

    assert result["confirmation_required"] is True
    assert result["signed_in"] is False
    assert result["email"] == "new@example.com"
    assert auth.get_session() is None


def test_sign_up_with_tokens_signs_in(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        return {
            "access_token": _fake_access_token("new@example.com"),
            "refresh_token": "refresh-token-plain",
        }

    monkeypatch.setattr(auth, "_post_auth", fake_post)
    monkeypatch.setattr(auth, "_network_available", lambda: True)

    result = auth.sign_up_with_password("new@example.com", "hunter22")

    assert result["signed_in"] is True
    assert result.get("confirmation_required") is not True
    assert result["email"] == "new@example.com"


def test_sign_up_existing_user_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise _http_status_error(400, {"msg": "User already registered"})

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="already exists"):
        auth.sign_up_with_password("owner@example.com", "hunter22")


def test_sign_up_weak_password_message(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise _http_status_error(
            422, {"msg": "Password should be at least 6 characters"}
        )

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="at least 6 characters"):
        auth.sign_up_with_password("owner@example.com", "abc")


def test_send_password_reset_is_silent_for_unknown_email(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    calls: list[tuple[str, dict]] = []

    def fake_post(path, body, session=None):
        calls.append((path, body))
        raise _http_status_error(400, {"msg": "User not found"})

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    assert auth.send_password_reset("nobody@example.com") is None
    assert calls[0][0] == "/auth/v1/recover"
    assert calls[0][1] == {"email": "nobody@example.com"}


def test_send_password_reset_swallows_network_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import httpx

    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    assert auth.send_password_reset("nobody@example.com") is None


def test_suspended_account_message_passes_through(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    def fake_post(path, body, session=None):
        raise ValueError(auth._SUSPENDED_MESSAGE)

    monkeypatch.setattr(auth, "_post_auth", fake_post)

    with pytest.raises(ValueError, match="suspended"):
        auth.sign_in_with_password("owner@example.com", "hunter22")


def test_logout_clears_session_even_when_server_rejects_token(tmp_path, monkeypatch):
    """A 403 from the server must not strand the user in a signed-in state."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    auth.login_via_tokens("a.b.c", "refresh-token")
    assert auth.get_auth_state()["signed_in"] is True

    def _reject(*args, **kwargs):
        raise ValueError("Account suspended — contact support.")

    monkeypatch.setattr(auth, "_network_available", lambda: True)
    monkeypatch.setattr(auth, "_post_auth", _reject)

    auth.logout()
    assert auth.get_auth_state()["signed_in"] is False


def test_logout_clears_session_when_network_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    import httpx

    from apps.engine import auth

    auth.login_via_tokens("a.b.c", "refresh-token")

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(auth, "_network_available", lambda: True)
    monkeypatch.setattr(auth, "_post_auth", _boom)

    auth.logout()
    assert auth.get_auth_state()["signed_in"] is False
