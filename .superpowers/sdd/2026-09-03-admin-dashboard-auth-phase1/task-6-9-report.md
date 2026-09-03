# Task 6–9 Report: Desktop Auth Integration

Date: 2026-09-03

## Summary

Implemented Supabase-backed desktop authentication across the engine, desktop API bridge, and UI. Production builds require sign-in; dev builds (`CA_UNPACKER_DEV=1`) retain test licence keys.

## Task 6: Desktop Auth Module

**Created**
- `apps/engine/auth_config.py` — `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `CA_UNPACKER_AUTH_URL` from env with local dev fallbacks
- `apps/engine/auth.py` — session storage, encrypted refresh token (Fernet), quota sync via httpx Edge Function calls, 7-day offline grace
- `apps/engine/tests/test_auth.py` — offline grace, fingerprint stability, encryption, delegation, defensive body rejection

**Modified**
- `requirements.txt` — added `httpx>=0.27`

**Key APIs**
| Function | Purpose |
|----------|---------|
| `device_fingerprint()` | Stable SHA-256 machine hash |
| `get_session()` | Local session dict or None |
| `login_via_tokens()` | Persist encrypted refresh + access tokens |
| `logout()` | Clear session, optional server sign-out |
| `refresh_session()` | Exchange refresh token via Supabase Auth |
| `fetch_quota()` | POST `check-quota` (file_count=0), update cache |
| `check_can_ingest()` | Online quota check or offline grace fallback |
| `record_usage()` | POST `record-usage`, update cache |
| `get_auth_state()` | UI-facing signed_in, email, plan, quota, offline |

## Task 7: License Delegation

**Modified**
- `apps/engine/license.py` — delegates `get_license_status`, `assert_can_ingest`, `record_ingested` to auth when session signed in; `STARTER-TEST` / `PRO-TEST` only when `CA_UNPACKER_DEV=1`; adds `auth_mode` field
- `apps/engine/tests/test_stage9_stage10_gate.py` — sets `CA_UNPACKER_DEV=1`, pins licence month for stable quota tests

## Task 8: Desktop API Bridge

**Modified**
- `apps/desktop/app.py` — `get_auth_state`, `open_signup`, `open_login`, `logout`, `handle_auth_callback`; startup `refresh_session()` + `fetch_quota()`

**Created**
- `apps/desktop/tests/test_auth_api_contract.py` — API shape, callback parsing, browser open, logout

## Task 9: Desktop UI Auth State

**Modified**
- `apps/ui/index.html` — auth gate overlay, quota banner, licence modal hidden behind `dev-only`
- `apps/ui/app.js` — auth gate on unsigned state, quota banner when signed in, signup/login/logout wiring
- `apps/ui/styles.css` — auth gate, quota banner, disabled drop zone styles

## Test Results

```
python -m pytest apps/engine/tests/test_auth.py apps/engine/tests/test_stage9_stage10_gate.py apps/desktop/tests/test_auth_api_contract.py -v
```

**22 passed** (2026-09-03)

## Notes

- Network calls live only in `auth.py`; `license.py` and `dump.py` remain free of httpx/requests imports (stage 9 gate verified).
- Deep-link protocol registration (Task 10) is not included in this commit.
- Manual smoke: run desktop with `CA_UNPACKER_DEV=0` and no session → auth gate visible; with `CA_UNPACKER_DEV=1` → licence modal available.
