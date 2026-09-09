"""Temporary local diagnostic. Do not commit. Prints no secrets."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "http://127.0.0.1:54321"
DEFAULT_AUTH = "http://127.0.0.1:5173"
DEFAULT_ANON_ISS = "supabase-demo"


def classify_host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"127.0.0.1", "localhost"}:
        return "localhost"
    if host.endswith(".supabase.co"):
        return "production-supabase"
    if host.endswith("netlify.app"):
        return "production-netlify"
    return f"other:{host or 'missing'}"


def jwt_meta(token: str) -> dict:
    token = (token or "").strip()
    if token.count(".") != 2:
        return {"shape": "not-jwt", "role": None, "iss": None, "ref": None}
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return {
            "shape": "jwt",
            "role": data.get("role"),
            "iss": data.get("iss"),
            "ref": data.get("ref"),
        }
    except Exception:
        return {"shape": "jwt-unreadable", "role": None, "iss": None, "ref": None}


def inspect_dotenv() -> dict:
    path = ROOT / ".env"
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    names = []
    lengths = {}
    has_crlf = b"\r\n" in raw
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            names.append({"raw_has_equals": False, "len_name": len(line)})
            continue
        key, value = line.split("=", 1)
        names.append(key)
        lengths[key] = len(value)
    return {
        "exists": True,
        "bom": bom,
        "crlf": has_crlf,
        "size_bytes": len(raw),
        "keys": names,
        "value_lengths": lengths,
    }


def report_resolved(label: str) -> dict:
    # Import after env is already set by the parent process.
    from apps.engine import auth_config

    url = auth_config.SUPABASE_URL
    auth_url = auth_config.CA_UNPACKER_AUTH_URL
    key = auth_config.SUPABASE_ANON_KEY or ""
    env_url = os.environ.get("SUPABASE_URL")
    env_auth = os.environ.get("CA_UNPACKER_AUTH_URL")
    env_key = os.environ.get("SUPABASE_ANON_KEY")
    meta = jwt_meta(key)
    return {
        "label": label,
        "resolved_supabase_class": classify_host(url),
        "resolved_auth_class": classify_host(auth_url),
        "resolved_url_is_default_local": url.rstrip("/") == DEFAULT_URL,
        "resolved_auth_is_default_local": auth_url.rstrip("/") == DEFAULT_AUTH,
        "anon_key": "PRESENT" if key else "MISSING",
        "anon_from_process_env": "PRESENT" if env_key else "MISSING",
        "url_from_process_env": "PRESENT" if env_url else "MISSING",
        "auth_url_from_process_env": "PRESENT" if env_auth else "MISSING",
        "anon_jwt_role": meta.get("role"),
        "anon_jwt_iss": meta.get("iss"),
        "anon_jwt_ref_present": bool(meta.get("ref")),
        "anon_is_local_demo_issuer": meta.get("iss") == DEFAULT_ANON_ISS,
        "env_url_has_cr": bool(env_url and "\r" in env_url),
        "env_key_has_cr": bool(env_key and "\r" in env_key),
        "env_key_len": len(env_key) if env_key else 0,
    }


def probe(url: str) -> dict:
    import httpx

    out = {"target_class": classify_host(url), "head_rest": None, "password_grant": None}
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.head(f"{url.rstrip('/')}/rest/v1/")
            out["head_rest"] = {
                "status": r.status_code,
                "error_type": None,
            }
    except Exception as exc:
        out["head_rest"] = {
            "status": None,
            "error_type": type(exc).__name__,
        }
    try:
        from apps.engine import auth_config

        headers = {
            "apikey": auth_config.SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=12.0) as client:
            r = client.post(
                f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
                headers=headers,
                json={
                    "email": "diagnostic-invalid@example.invalid",
                    "password": "not-a-real-password",
                },
            )
        body = {}
        try:
            parsed = r.json()
            if isinstance(parsed, dict):
                body = {
                    k: parsed.get(k)
                    for k in ("error", "error_code", "msg", "message", "error_description")
                    if k in parsed
                }
        except Exception:
            body = {"parse": "non-json"}
        out["password_grant"] = {
            "status": r.status_code,
            "sanitized_error_fields": body,
            "has_access_token": bool(
                isinstance(r.json(), dict) and r.json().get("access_token")
            )
            if r.headers.get("content-type", "").startswith("application/json")
            else False,
        }
    except Exception as exc:
        out["password_grant"] = {
            "status": None,
            "error_type": type(exc).__name__,
            "sanitized_error_fields": {},
        }
    return out


def main() -> None:
    info = inspect_dotenv()
    resolved = report_resolved(sys.argv[1] if len(sys.argv) > 1 else "current-process")
    from apps.engine import auth_config

    probe_result = probe(auth_config.SUPABASE_URL)
    print(json.dumps({"dotenv": info, "resolved": resolved, "probe": probe_result}, indent=2))


if __name__ == "__main__":
    main()