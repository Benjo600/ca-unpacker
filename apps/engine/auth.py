from __future__ import annotations

import base64
import hashlib
import json
import platform
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from apps.engine.auth_config import (
    APP_VERSION,
    CA_UNPACKER_AUTH_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
)
from apps.engine.license import STARTER_LIMIT, _QUOTA_MESSAGE
from apps.engine.settings import load_settings, save_settings

OFFLINE_GRACE_DAYS = 7

_BANNED_BODY_KEYS = frozenset(
    {
        "document",
        "documents",
        "pdf",
        "content",
        "payload",
        "invoice",
        "gstin",
        "rows",
        "file_path",
        "path",
        "data",
        "extracted",
        "transactions",
    }
)
_OFFLINE_EXPIRED = (
    "Connect to the internet to verify your plan before processing more files."
)
_SUSPENDED_MESSAGE = "Account suspended — contact support."
_HTTP_TIMEOUT = 12.0


def device_fingerprint() -> str:
    parts = [
        platform.node(),
        platform.system(),
        platform.machine(),
        platform.processor() or "",
        str(uuid.getnode()),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    data = load_settings()
    salt = data.get("auth_salt")
    if not salt:
        salt = secrets.token_hex(16)
        save_settings({"auth_salt": salt})
    digest = hashlib.sha256(f"{device_fingerprint()}:{salt}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_refresh_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def _decrypt_refresh_token(token_enc: str) -> str | None:
    if not token_enc:
        return None
    try:
        return _fernet().decrypt(token_enc.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def _email_from_jwt(access_token: str) -> str | None:
    try:
        payload = access_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        email = data.get("email")
        return str(email) if email else None
    except Exception:
        return None


def get_session() -> dict | None:
    data = load_settings()
    access = (data.get("auth_access_token") or "").strip()
    refresh_enc = (data.get("auth_refresh_token_enc") or "").strip()
    refresh = _decrypt_refresh_token(refresh_enc)
    if not access or not refresh:
        return None
    email = (data.get("auth_email") or "").strip() or _email_from_jwt(access)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "email": email,
    }


def _clear_session() -> None:
    save_settings(
        {
            "auth_access_token": "",
            "auth_refresh_token_enc": "",
            "auth_email": "",
        }
    )


def login_via_tokens(access_token: str, refresh_token: str) -> dict:
    access = (access_token or "").strip()
    refresh = (refresh_token or "").strip()
    if not access or not refresh:
        raise ValueError("Sign-in did not return a valid session.")
    email = _email_from_jwt(access) or ""
    save_settings(
        {
            "auth_access_token": access,
            "auth_refresh_token_enc": _encrypt_refresh_token(refresh),
            "auth_email": email,
        }
    )
    return get_auth_state()


def login_with_password(email: str, password: str) -> dict:
    cleaned_email = (email or "").strip()
    if not cleaned_email or not password:
        raise ValueError("Enter your email and password.")
    body = {"email": cleaned_email, "password": password}
    _reject_document_keys(body)
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=_auth_headers(),
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ValueError("Could not reach the account service.") from exc
    if response.status_code in (400, 401):
        raise ValueError("Invalid email or password.")
    if response.status_code >= 400:
        raise ValueError("Could not sign in. Try again.")
    payload = response.json() if response.content else {}
    if not isinstance(payload, dict):
        raise ValueError("Sign-in did not return a valid session.")
    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or "").strip()
    login_via_tokens(access, refresh)
    try:
        fetch_quota()
        send_heartbeat()
    except Exception:
        pass
    return get_auth_state()


def logout() -> None:
    session = get_session()
    if session and _network_available():
        try:
            _post_auth(
                "/auth/v1/logout",
                {"refresh_token": session["refresh_token"]},
                session=session,
            )
        except httpx.HTTPError:
            pass
    _clear_session()


def refresh_session() -> dict | None:
    session = get_session()
    if session is None:
        return None
    if not _network_available():
        return session
    try:
        payload = _post_auth(
            "/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": session["refresh_token"]},
        )
    except httpx.HTTPError:
        return session
    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or session["refresh_token"]).strip()
    if not access:
        return session
    email = _email_from_jwt(access) or session.get("email") or ""
    save_settings(
        {
            "auth_access_token": access,
            "auth_refresh_token_enc": _encrypt_refresh_token(refresh),
            "auth_email": email,
        }
    )
    return get_session()


def load_quota_cache() -> dict:
    data = load_settings()
    cache = data.get("auth_quota_cache")
    return dict(cache) if isinstance(cache, dict) else {}


def save_quota_cache(cache: dict) -> dict:
    payload = {
        "files_used": int(cache.get("files_used") or 0),
        "file_limit": cache.get("file_limit"),
        "plan": str(cache.get("plan") or "starter"),
        "synced_at": str(cache.get("synced_at") or datetime.now().isoformat(timespec="seconds")),
    }
    if payload["file_limit"] is not None:
        payload["file_limit"] = int(payload["file_limit"])
    save_settings({"auth_quota_cache": payload})
    return payload


def fetch_quota() -> dict:
    session = get_session()
    if session is None:
        return load_quota_cache()
    if not _network_available():
        return load_quota_cache()
    try:
        result = _call_function("check-quota", {"file_count": 0}, session)
    except httpx.HTTPError:
        return load_quota_cache()
    except ValueError as exc:
        if "suspend" in str(exc).lower():
            cached = load_quota_cache()
            return save_quota_cache(
                {
                    "files_used": cached.get("files_used", 0),
                    "file_limit": 0,
                    "plan": "suspended",
                    "synced_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        return load_quota_cache()
    cache = save_quota_cache(
        {
            "files_used": result.get("files_used", 0),
            "file_limit": result.get("file_limit"),
            "plan": result.get("plan", "starter"),
            "synced_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return cache


def send_heartbeat() -> dict | None:
    session = get_session()
    if session is None or not _network_available():
        return None
    try:
        return _call_function(
            "heartbeat",
            {
                "app_version": APP_VERSION,
                "device_label": platform.node() or "Windows PC",
                "fingerprint_sha256": device_fingerprint(),
            },
            session,
        )
    except (httpx.HTTPError, ValueError):
        return None


def check_can_ingest_offline(file_count: int, today: date | None = None) -> None:
    count = int(file_count or 0)
    if count <= 0:
        return
    cache = load_quota_cache()
    synced_raw = str(cache.get("synced_at") or "").strip()
    if not synced_raw:
        raise ValueError(_OFFLINE_EXPIRED)
    try:
        synced_at = datetime.fromisoformat(synced_raw)
    except ValueError:
        raise ValueError(_OFFLINE_EXPIRED) from None
    when = today or date.today()
    if when - synced_at.date() > timedelta(days=OFFLINE_GRACE_DAYS):
        raise ValueError(_OFFLINE_EXPIRED)
    limit = cache.get("file_limit")
    used = int(cache.get("files_used") or 0)
    if limit is None:
        return
    if used + count > int(limit):
        raise ValueError(_QUOTA_MESSAGE)


def check_can_ingest(file_count: int, today: date | None = None) -> None:
    count = int(file_count or 0)
    if count <= 0:
        return
    session = get_session()
    if session and _network_available():
        try:
            result = _call_function("check-quota", {"file_count": count}, session)
        except httpx.HTTPError:
            check_can_ingest_offline(count, today=today)
            return
        save_quota_cache(
            {
                "files_used": result.get("files_used", 0),
                "file_limit": result.get("file_limit"),
                "plan": result.get("plan", "starter"),
                "synced_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if not result.get("allowed", False):
            raise ValueError(_QUOTA_MESSAGE)
        return
    check_can_ingest_offline(count, today=today)


def record_usage(file_count: int) -> dict:
    count = int(file_count or 0)
    if count <= 0:
        return load_quota_cache()
    session = get_session()
    if session and _network_available():
        try:
            result = _call_function(
                "record-usage",
                {"files_processed": count},
                session,
            )
            return save_quota_cache(
                {
                    "files_used": result.get("files_used", 0),
                    "file_limit": result.get("file_limit"),
                    "plan": result.get("plan", "starter"),
                    "synced_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        except httpx.HTTPError:
            pass
    cache = load_quota_cache()
    cache["files_used"] = int(cache.get("files_used") or 0) + count
    cache["synced_at"] = str(cache.get("synced_at") or datetime.now().isoformat(timespec="seconds"))
    return save_quota_cache(cache)


def get_auth_state() -> dict:
    session = get_session()
    cache = load_quota_cache()
    offline = session is not None and not _network_available()
    plan = str(cache.get("plan") or "starter")
    files_used = int(cache.get("files_used") or 0)
    file_limit = cache.get("file_limit")
    if file_limit is not None:
        file_limit = int(file_limit)
    elif plan == "starter" and not cache:
        file_limit = STARTER_LIMIT
    remaining = None if file_limit is None else max(0, int(file_limit) - files_used)
    return {
        "signed_in": session is not None,
        "email": session.get("email") if session else None,
        "plan": plan,
        "files_used": files_used,
        "file_limit": file_limit,
        "files_remaining": remaining,
        "offline": offline,
        "last_sync_at": cache.get("synced_at"),
        "auth_url": CA_UNPACKER_AUTH_URL,
        "dashboard_url": f"{CA_UNPACKER_AUTH_URL}/app",
    }


def _network_available() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.head(f"{SUPABASE_URL}/rest/v1/")
            return response.status_code < 500
    except httpx.HTTPError:
        return False


def _reject_document_keys(body: dict[str, Any]) -> None:
    for key in body:
        lowered = key.lower()
        if lowered in _BANNED_BODY_KEYS or any(
            banned in lowered for banned in ("document", "invoice", "gstin", "pdf")
        ):
            raise ValueError("Request must not include client document data.")


def _auth_headers(session: dict | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    if session and session.get("access_token"):
        headers["Authorization"] = f"Bearer {session['access_token']}"
    return headers


def _post_auth(path: str, body: dict[str, Any], session: dict | None = None) -> dict:
    _reject_document_keys(body)
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.post(
            f"{SUPABASE_URL}{path}",
            headers=_auth_headers(session),
            json=body,
        )
    if response.status_code == 403:
        raise ValueError(_SUSPENDED_MESSAGE)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _call_function(name: str, body: dict[str, Any], session: dict) -> dict:
    _reject_document_keys(body)
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.post(
            f"{SUPABASE_URL}/functions/v1/{name}",
            headers=_auth_headers(session),
            json=body,
        )
    if response.status_code == 403:
        detail = ""
        try:
            detail = str(response.json().get("error") or response.json().get("message") or "")
        except Exception:
            detail = response.text
        if "suspend" in detail.lower():
            raise ValueError(_SUSPENDED_MESSAGE)
        raise ValueError(_SUSPENDED_MESSAGE)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}
