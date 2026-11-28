from __future__ import annotations

import base64
import hashlib
import json
import platform
import secrets
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from apps.engine.auth_config import (
    CA_UNPACKER_AUTH_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
)
from apps.engine.license import STARTER_LIMIT, _QUOTA_MESSAGE
from apps.engine.settings import load_settings, save_settings
from apps.version import APP_VERSION

# ``httpx`` and ``cryptography`` are imported inside the functions that talk to
# the network or open an encrypted token. A cold start on a signed-out machine
# never does either, and those two libraries are most of a second of import
# time, so the first paint must not pay for them.

OFFLINE_GRACE_DAYS = 7

# Settings keys that belong to the login, not to client data. The wipe/Reset
# flow snapshots these so "Delete everything" clears the library without
# signing the user out.
_AUTH_SETTING_KEYS = (
    "auth_salt",
    "auth_access_token",
    "auth_access_token_enc",
    "auth_refresh_token_enc",
    "auth_email",
    "auth_quota_cache",
)

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
_INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."
_EMAIL_TAKEN_MESSAGE = "An account with this email already exists. Log in instead."
_WEAK_PASSWORD_MESSAGE = "Password must be at least 6 characters."
_RATE_LIMITED_MESSAGE = "Too many attempts. Wait a minute and try again."
_NO_CONNECTION_MESSAGE = "Could not reach the server. Check your internet connection."
_HTTP_TIMEOUT = 12.0
_EXISTING_USER_HINTS = ("already registered", "already exists", "user_already_exists")
_WEAK_PASSWORD_HINTS = ("weak_password", "should be at least", "password is too short")


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
    from cryptography.fernet import Fernet

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
    return _decrypt_token(token_enc)


def _encrypt_access_token(token: str) -> str:
    return _encrypt_refresh_token(token)


def _decrypt_token(token_enc: str) -> str | None:
    if not token_enc:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token_enc.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None


def _read_access_token(data: dict) -> str:
    """The access token, encrypted at rest. Older builds stored it in the clear.

    A plaintext value found on disk is re-encrypted in place, so an existing
    install upgrades itself on first read instead of staying exposed.
    """
    encrypted = str(data.get("auth_access_token_enc") or "").strip()
    if encrypted:
        return (_decrypt_token(encrypted) or "").strip()
    legacy = str(data.get("auth_access_token") or "").strip()
    if legacy:
        save_settings(
            {
                "auth_access_token": "",
                "auth_access_token_enc": _encrypt_access_token(legacy),
            }
        )
    return legacy


def _email_from_jwt(access_token: str) -> str | None:
    try:
        payload = access_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        email = data.get("email")
        return str(email) if email else None
    except Exception:
        return None


def _jwt_exp(access_token: str) -> float | None:
    try:
        payload = access_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        exp = data.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def _access_expired(access_token: str, leeway_seconds: int = 60) -> bool:
    exp = _jwt_exp(access_token)
    if exp is None:
        return True
    return datetime.now(timezone.utc).timestamp() >= exp - leeway_seconds


def get_session() -> dict | None:
    data = load_settings()
    access = _read_access_token(data)
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
            "auth_access_token_enc": "",
            "auth_refresh_token_enc": "",
            "auth_email": "",
        }
    )


def snapshot_auth_settings() -> dict:
    """Copy the login-related settings before the library folder is wiped."""
    data = load_settings()
    return {key: data[key] for key in _AUTH_SETTING_KEYS if key in data}


def restore_auth_settings(snapshot: dict) -> None:
    """Put the login back after a wipe, so Delete does not sign the user out."""
    if not isinstance(snapshot, dict):
        return
    payload = {
        key: value for key, value in snapshot.items() if key in _AUTH_SETTING_KEYS
    }
    if payload:
        save_settings(payload)


def login_via_tokens(access_token: str, refresh_token: str) -> dict:
    access = (access_token or "").strip()
    refresh = (refresh_token or "").strip()
    if not access or not refresh:
        raise ValueError("Sign-in did not return a valid session.")
    email = _email_from_jwt(access) or ""
    save_settings(
        {
            "auth_access_token": "",
            "auth_access_token_enc": _encrypt_access_token(access),
            "auth_refresh_token_enc": _encrypt_refresh_token(refresh),
            "auth_email": email,
        }
    )
    return get_auth_state()


def sign_in_with_password(email: str, password: str) -> dict:
    address = (email or "").strip()
    secret = password or ""
    if not address or not secret:
        raise ValueError(_INVALID_CREDENTIALS_MESSAGE)
    payload = _post_password_auth(
        "/auth/v1/token?grant_type=password",
        {"email": address, "password": secret},
    )
    tokens = _session_tokens(payload)
    if tokens is None:
        raise ValueError(_INVALID_CREDENTIALS_MESSAGE)
    return login_via_tokens(tokens[0], tokens[1])


def sign_up_with_password(email: str, password: str) -> dict:
    address = (email or "").strip()
    secret = password or ""
    if not address:
        raise ValueError(_INVALID_CREDENTIALS_MESSAGE)
    if len(secret) < 6:
        raise ValueError(_WEAK_PASSWORD_MESSAGE)
    payload = _post_password_auth(
        "/auth/v1/signup",
        {"email": address, "password": secret},
        signup=True,
    )
    tokens = _session_tokens(payload)
    if tokens is None:
        return {
            "signed_in": False,
            "confirmation_required": True,
            "email": address,
        }
    state = login_via_tokens(tokens[0], tokens[1])
    state["confirmation_required"] = False
    return state


def send_password_reset(email: str) -> None:
    import httpx

    address = (email or "").strip()
    if not address:
        return None
    try:
        _post_auth("/auth/v1/recover", {"email": address})
    except (httpx.HTTPError, ValueError):
        # Never reveal whether the address is registered.
        return None
    return None


def _session_tokens(payload: dict) -> tuple[str, str] | None:
    source: dict[str, Any] = payload
    nested = payload.get("session")
    if not payload.get("access_token") and isinstance(nested, dict):
        source = nested
    access = str(source.get("access_token") or "").strip()
    refresh = str(source.get("refresh_token") or "").strip()
    if not access or not refresh:
        return None
    return access, refresh


def _auth_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text or ""
    if not isinstance(payload, dict):
        return str(payload)
    fields = (
        "error_code",
        "error",
        "error_description",
        "code",
        "msg",
        "message",
    )
    parts = [str(payload.get(field)) for field in fields if payload.get(field)]
    return " ".join(parts)


def _password_auth_error(exc: httpx.HTTPStatusError, signup: bool) -> ValueError:
    status = exc.response.status_code
    detail = _auth_error_detail(exc.response).lower()
    if status == 429 or "rate limit" in detail or "over_email_send_rate" in detail:
        return ValueError(_RATE_LIMITED_MESSAGE)
    if any(hint in detail for hint in _EXISTING_USER_HINTS):
        return ValueError(_EMAIL_TAKEN_MESSAGE)
    if any(hint in detail for hint in _WEAK_PASSWORD_HINTS):
        return ValueError(_WEAK_PASSWORD_MESSAGE)
    if status == 422:
        return ValueError(_WEAK_PASSWORD_MESSAGE)
    if status == 400:
        if signup:
            return ValueError(_EMAIL_TAKEN_MESSAGE)
        return ValueError(_INVALID_CREDENTIALS_MESSAGE)
    return ValueError(_NO_CONNECTION_MESSAGE)


def _post_password_auth(path: str, body: dict[str, Any], signup: bool = False) -> dict:
    import httpx

    try:
        return _post_auth(path, body)
    except httpx.HTTPStatusError as exc:
        raise _password_auth_error(exc, signup) from None
    except httpx.RequestError:
        raise ValueError(_NO_CONNECTION_MESSAGE) from None


def login_with_password(email: str, password: str) -> dict:
    """Compatibility API used by the current desktop UI."""
    state = sign_in_with_password(email, password)
    try:
        fetch_quota()
        send_heartbeat()
    except Exception:
        pass
    return state | get_auth_state()


def logout() -> None:
    session = get_session()
    if session and _network_available():
        try:
            _post_auth(
                "/auth/v1/logout",
                {"refresh_token": session["refresh_token"]},
                session=session,
            )
        except Exception:
            # Revoking server-side is best effort. A rejected or expired token
            # (403 raises ValueError, not HTTPError) must never strand the user
            # signed in locally, so the session is cleared either way.
            pass
    _clear_session()


def refresh_session() -> dict | None:
    """Refresh the stored session only when the access token is expiring.

    A failed refresh must almost never destroy the saved login: a dropped
    connection or a server hiccup is not proof the account is invalid, and
    logging the CA out on every hiccup is exactly what they complain about.
    The session is cleared only when the server explicitly rejects the
    refresh token (revoked / reused / invalid), or when the user logs out.
    """
    import httpx

    session = get_session()
    if session is None:
        return None
    if not _access_expired(session["access_token"]):
        return session
    if not _network_available():
        # Processing already runs on the offline grace timer until the next
        # successful refresh; signing out here would be a false positive.
        return session
    try:
        payload = _post_auth(
            "/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": session["refresh_token"]},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 401):
            # Supabase answers an invalid / revoked / reused refresh token
            # with 400 invalid_grant. Only then is signing out correct.
            _clear_session()
            return None
        # 429 and 5xx are server trouble — keep the session and let quota
        # callers fall back to the offline grace path.
        return session
    except httpx.HTTPError:
        # Network broke mid-refresh. The rotation may or may not have landed
        # server-side; keeping the local session is the safer answer, and
        # Supabase's refresh-token reuse window covers the retry.
        return session
    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or session["refresh_token"]).strip()
    if not access:
        _clear_session()
        return None
    email = _email_from_jwt(access) or session.get("email") or ""
    save_settings(
        {
            "auth_access_token": "",
            "auth_access_token_enc": _encrypt_access_token(access),
            "auth_refresh_token_enc": _encrypt_refresh_token(refresh),
            "auth_email": email,
        }
    )
    return get_session()


def call_authenticated_function(name: str, body: dict[str, Any]) -> dict:
    """Call a Supabase Edge Function as the signed-in user.

    An expired access token is refreshed once and the call retried. Tokens are
    never logged. Document keys are still rejected by ``_call_function``.
    """

    session = get_session()
    if session is None:
        raise ValueError("Sign in to check for updates.")
    import httpx

    try:
        return _call_function(name, body, session)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
    refreshed = refresh_session()
    if refreshed is None:
        raise ValueError("Sign in again to check for updates.") from None
    try:
        return _call_function(name, body, refreshed)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise ValueError("Sign in again to check for updates.") from None
        raise


def load_quota_cache() -> dict:
    data = load_settings()
    cache = data.get("auth_quota_cache")
    return dict(cache) if isinstance(cache, dict) else {}


def save_quota_cache(cache: dict) -> dict:
    payload = {
        "files_used": int(cache.get("files_used") or 0),
        "file_limit": cache.get("file_limit"),
        "plan": str(cache.get("plan") or "starter"),
        "synced_at": str(cache.get("synced_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
    }
    if payload["file_limit"] is not None:
        payload["file_limit"] = int(payload["file_limit"])
    save_settings({"auth_quota_cache": payload})
    return payload


def fetch_quota() -> dict:
    import httpx

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
                    "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
        return load_quota_cache()
    cache = save_quota_cache(
        {
            "files_used": result.get("files_used", 0),
            "file_limit": result.get("file_limit"),
            "plan": result.get("plan", "starter"),
            "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    return cache


def send_heartbeat() -> dict | None:
    import httpx

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
    import httpx

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
                "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        if not result.get("allowed", False):
            raise ValueError(_QUOTA_MESSAGE)
        return
    check_can_ingest_offline(count, today=today)


def record_usage(file_count: int) -> dict:
    import httpx

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
                    "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
        except httpx.HTTPError:
            pass
    cache = load_quota_cache()
    cache["files_used"] = int(cache.get("files_used") or 0) + count
    cache["synced_at"] = str(cache.get("synced_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return save_quota_cache(cache)


def get_auth_state() -> dict:
    session = get_session()
    cache = load_quota_cache()
    # This runs on the first paint, so it must never wait on a network round
    # trip: it reads the last recorded probe result instead of probing. With
    # nothing recorded yet the desk is treated as online; the startup auth sync,
    # a quota call or a heartbeat records the truth moments later.
    offline = session is not None and _network_available_cached() is False
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


# How long a recorded probe answer is trusted. Short enough that a CA who was
# offline five minutes ago is not still described as offline, long enough that
# the desk never re-probes on its own.
_NETWORK_CACHE_MAX_AGE = 300.0
_NETWORK_CACHE_LOCK = threading.Lock()
#: ``(available, recorded_at)`` from the last real probe, or None.
_network_cache: tuple[bool, float] | None = None


def _record_network_available(available: bool) -> bool:
    """Remember a probe result so the next state read does not probe again."""
    global _network_cache
    with _NETWORK_CACHE_LOCK:
        _network_cache = (bool(available), time.monotonic())
    return bool(available)


def _network_available_cached(
    max_age: float = _NETWORK_CACHE_MAX_AGE,
) -> bool | None:
    """The last recorded answer, without touching the network.

    ``None`` means nothing recent is known. Callers on the boot path treat that
    as "assume online" and let the background sync correct it, rather than make
    the window wait for a request that may take seconds to time out.
    """
    with _NETWORK_CACHE_LOCK:
        cached = _network_cache
    if cached is None:
        return None
    available, recorded_at = cached
    if time.monotonic() - recorded_at > max_age:
        return None
    return available


def _probe_network() -> bool:
    """One live request. Never called from the state read."""
    import httpx

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.head(f"{SUPABASE_URL}/rest/v1/")
            return response.status_code < 500
    except httpx.HTTPError:
        return False


def _network_available() -> bool:
    """Probe the network and remember the answer for the non-blocking readers."""
    return _record_network_available(_probe_network())


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
    import httpx

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


def _post_function(name: str, body: dict[str, Any], session: dict | None) -> dict:
    import httpx

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.post(
            f"{SUPABASE_URL}/functions/v1/{name}",
            headers=_auth_headers(session),
            json=body,
        )
    if response.status_code == 403:
        raise ValueError(_SUSPENDED_MESSAGE)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _call_function(name: str, body: dict[str, Any], session: dict) -> dict:
    import httpx

    _reject_document_keys(body)
    try:
        return _post_function(name, body, session)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        # The access token aged out mid-session. Refresh once and retry;
        # if the refresh token itself was revoked, refresh_session clears
        # the session and the original 401 still travels to the caller,
        # which falls back to the offline grace path.
        refreshed = refresh_session()
        if refreshed is None:
            raise
        return _post_function(name, body, refreshed)
