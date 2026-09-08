# CA Unpacker — Admin Dashboard & Auth Design

Date: 2026-09-03

## Goal

Add a cloud control plane so the two product operators can manage CA firm accounts, enforce Starter/Pro plans, and observe usage — while the desktop app continues to process all client documents locally and never uploads financial data.

## Binding Product Rules

- Client document contents, extracted transactions, invoice data, PAN/GSTIN from documents, and client names parsed from files **never** leave the CA's PC.
- The server receives **metadata only**: firm identity, plan, subscription state, files-processed counters, client-count counters, device fingerprints (hashed), and app version.
- Authentication is email + password via Supabase Auth.
- New users get **instant Starter access** (100 files/month) on signup; operators upgrade to Pro manually until a payment gateway exists.
- Signup happens on a web page reached from first app launch (or download landing flow); new accounts appear on the admin dashboard immediately.
- Two operator accounts (the founders) have full admin access; CA firm users have no admin access.
- Offline grace: desktop app may continue with last-known quota for up to **7 days** without connectivity; after that, reconnect is required before ingest.
- Existing local-only test keys (`STARTER-TEST`, `PRO-TEST`) remain available in development builds only; production builds require Supabase auth.

## Commercial Path

| Phase | Scope |
|-------|-------|
| **Phase 1** (build first) | Supabase schema, signup/login web pages, desktop session auth, usage sync, basic admin dashboard |
| **Phase 2** | License key generation/redemption, device limits, CSV export, transactional emails |
| **Phase 3** | Razorpay payment, auto-upgrade on payment, invoice emails |

This spec covers Phase 1 in full and defines Phase 2/3 interfaces so they can be added without redesign.

## Architecture

```text
┌─────────────────────┐         ┌──────────────────────────┐
│  CA Unpacker        │  HTTPS  │  Supabase                │
│  (Desktop - Python) │ ──────► │  • Auth (email/password) │
│                     │         │  • Postgres              │
│  Local processing   │         │  • Edge Functions (API)  │
│  Client docs NEVER  │         └──────────┬───────────────┘
│  leave the PC       │                    │
└─────────────────────┘                    │
                                           │
┌─────────────────────┐                    │
│  Web (Netlify)      │ ◄──────────────────┘
│  • /signup          │
│  • /login           │
│  • /admin (private) │
└─────────────────────┘
```

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Supabase Auth** | Hosted | Email/password signup, login, JWT sessions, password reset |
| **Supabase Postgres** | Hosted | Organizations, users, devices, usage aggregates, license keys, admin allowlist |
| **Edge Functions** | `supabase/functions/` | Desktop-safe API: quota check, usage ping, heartbeat, session refresh helpers |
| **Signup/Login web** | `apps/web/` | Public auth pages; redirects back to desktop via `caunpacker://` deep link |
| **Admin dashboard** | `apps/web/admin/` | Private operator UI: user list, usage, plan changes, suspend, license keys (Phase 2) |
| **Desktop auth client** | `apps/engine/auth.py` | Session storage, token refresh, quota fetch, usage sync |
| **Desktop API bridge** | `apps/desktop/app.py` | Expose auth state and login/logout to pywebview UI |

### Hosting

- **Web apps:** Netlify (extends existing `designs/ca-unpacker-landing` deployment or sibling site under same domain).
- **Backend:** Supabase project (free tier sufficient for beta).
- **Secrets:** Supabase anon key in web apps; service role key only in Edge Functions and local operator `.env` (never in desktop installer).

## Data Model

### `organizations`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `name` | text | Firm name entered at signup |
| `plan` | enum | `starter`, `pro`, `suspended` |
| `license_key` | text nullable | Set when operator issues a key (Phase 2) |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

### `profiles`

Extends Supabase `auth.users` (one row per auth user).

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK FK → auth.users | |
| `org_id` | uuid FK → organizations | |
| `email` | text | Denormalized from auth for admin queries |
| `role` | enum | `owner`, `member` (v1: always `owner` at signup) |
| `created_at` | timestamptz | |
| `last_active_at` | timestamptz nullable | Updated on heartbeat |

### `devices`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `org_id` | uuid FK | |
| `user_id` | uuid FK | |
| `fingerprint_sha256` | text | Hash of machine id + salt; never raw hardware serial |
| `label` | text | e.g. `"DESKTOP-Rajesh"` |
| `app_version` | text | Last reported version |
| `first_seen_at` | timestamptz | |
| `last_seen_at` | timestamptz | |
| `active` | boolean | Operator can deactivate in Phase 2 |

Unique constraint: `(org_id, fingerprint_sha256)`.

### `usage_monthly`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `org_id` | uuid FK | |
| `month` | text | `YYYY-MM` |
| `files_processed` | integer | Running total for calendar month |
| `clients_created` | integer | Optional counter |
| `updated_at` | timestamptz | |

Unique constraint: `(org_id, month)`.

### `admin_users`

| Column | Type | Notes |
|--------|------|-------|
| `email` | text PK | Operator allowlist (two founder emails) |

### `license_keys` (Phase 2 schema, created in Phase 1 migration stub)

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `key_hash` | text | SHA-256 of key; plaintext shown once at generation |
| `plan` | enum | `pro` |
| `org_id` | uuid nullable FK | Null until redeemed |
| `created_at` | timestamptz | |
| `redeemed_at` | timestamptz nullable | |
| `revoked_at` | timestamptz nullable | |

### Plan limits

| Plan | File limit / month | Price (INR) | Notes |
|------|-------------------|-------------|-------|
| `starter` | 100 | 999 | Default on signup |
| `pro` | unlimited (`null`) | 2,500 | Operator-assigned or key-redeemed |
| `suspended` | 0 | — | Blocks ingest |

## Row-Level Security

- **CA users:** can read/update only their own `profiles`, `organizations` (name only), and `usage_monthly` for their org.
- **CA users:** can insert/update their own `devices` row.
- **CA users:** cannot read other orgs or admin tables.
- **Operators:** admin dashboard uses Supabase service role via a server-side Edge Function **or** dedicated `admin` Postgres role checked against `admin_users` — prefer Edge Function proxy for admin mutations to avoid exposing service role in the browser.
- **Desktop app:** uses user JWT + Edge Functions for quota check and usage increment (server-side validation prevents client tampering).

## User Flows

### 1. First launch → signup

1. User installs CA Unpacker and opens the app.
2. App checks local session (`settings.json` → `auth_refresh_token` encrypted).
3. No session → app opens system browser to `https://<domain>/signup?redirect=desktop`.
4. User enters: email, password, firm name.
5. Supabase creates auth user; trigger creates `organizations` + `profiles` with `plan = starter`.
6. Web page receives session; redirects to `caunpacker://auth/callback#access_token=...&refresh_token=...`.
7. Desktop registers `caunpacker://` protocol handler (Windows registry via installer).
8. App stores refresh token in local settings (encrypted with machine-bound key).
9. App shows main UI with quota banner.

### 2. Return visit → login

1. App validates stored refresh token against Supabase.
2. If expired or missing → open `https://<domain>/login?redirect=desktop` (same deep-link callback).
3. On success, fetch quota and proceed.

### 3. File ingest with quota

1. Before `ingest_paths`, desktop calls Edge Function `check-quota` with `{ file_count: N }`.
2. Server returns `{ allowed: true/false, files_used, file_limit, plan }`.
3. If allowed, ingest proceeds locally as today.
4. After successful ingest, desktop calls `record-usage` with `{ files_processed: N }` (metadata only).
5. Server atomically increments `usage_monthly.files_processed`.
6. Local `license.py` counters remain as offline cache synced from server.

### 4. Heartbeat

Every 24 hours (and on app start), desktop calls `heartbeat` with `{ app_version, device_label }`.
Server updates `profiles.last_active_at`, `devices.last_seen_at`, `devices.app_version`.

### 5. Operator views dashboard

1. Operator logs in at `/admin` with allowlisted email.
2. Dashboard lists all organizations: email, firm name, plan, files used/limit, last active, device count.
3. Operator can change plan (`starter` ↔ `pro` ↔ `suspended`).
4. Changes take effect on next quota check (immediate for online users).

## Admin Dashboard Pages (Phase 1)

### Overview

- Total registered firms
- Active in last 7 days
- Total files processed this month (all firms)
- Starter vs Pro breakdown

### Users table

Columns: email, firm name, plan, files used / limit, last active, devices, created date.
Actions per row: view detail, change plan, suspend.

### User detail

- Usage history by month
- Device list with last seen
- Plan change form
- Suspend / unsuspend toggle

### Export (Phase 2)

CSV download of users + current-month usage.

## Desktop App Changes

### New module: `apps/engine/auth.py`

- `get_session()` → local session or None
- `login_via_tokens(access, refresh)` → persist encrypted
- `logout()` → clear local session, optional server sign-out
- `refresh_session()` → exchange refresh token
- `fetch_quota()` → call Edge Function, update local cache
- `check_can_ingest(file_count)` → server check with offline fallback
- `record_usage(file_count)` → post-ingest sync
- `device_fingerprint()` → stable hashed machine id

### Changes to `apps/engine/license.py`

- `get_license_status()` reads from auth quota cache when online session exists.
- `assert_can_ingest()` delegates to `auth.check_can_ingest()`.
- `record_ingested()` delegates to `auth.record_usage()` then updates local cache.
- `activate_key()` retained for dev builds; production uses web signup instead.

### Changes to `apps/desktop/app.py`

- New API methods: `get_auth_state()`, `open_signup()`, `open_login()`, `logout()`.
- Startup: attempt `refresh_session()` before `get_license_status()`.

### Changes to `apps/ui/`

- Replace licence-key modal with signed-out state: "Sign up" / "Log in" buttons.
- Show quota banner: `Files processed this month: X / 100` (or `unlimited` for Pro).
- Show privacy line: `Financial data transmitted: NONE`.

### Installer

- Register `caunpacker://` URL protocol on Windows (Inno Setup registry keys).
- Bundle Supabase project URL and anon key as build-time constants (not service role).

## Edge Functions (Phase 1)

| Function | Auth | Purpose |
|----------|------|---------|
| `check-quota` | User JWT | Validate plan, return allowance for N files |
| `record-usage` | User JWT | Increment monthly counter atomically |
| `heartbeat` | User JWT | Update last active + device row |
| `admin-list-orgs` | Admin JWT + allowlist | Return paginated org list for dashboard |
| `admin-update-plan` | Admin JWT + allowlist | Change org plan |

All functions reject requests that include document payloads; request bodies are schema-validated to metadata fields only.

## Web App Structure

```text
apps/web/
├── package.json
├── src/
│   ├── lib/supabase.ts      # shared client
│   ├── pages/
│   │   ├── signup.tsx
│   │   ├── login.tsx
│   │   └── admin/
│   │       ├── index.tsx    # overview
│   │       ├── users.tsx
│   │       └── user/[id].tsx
│   └── components/          # reuse landing palette tokens
└── netlify.toml             # routes /signup, /login, /admin/*
```

Styling reuses tokens from `designs/ca-unpacker-landing/DESIGN.md` (desk `#2c3330`, paper `#f4efe3`, ink `#1b3028`, accent `#c45a2a`).

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No internet at startup | Use cached quota; show "Offline — quota from last sync" |
| Offline > 7 days | Block ingest; prompt to connect |
| Suspended account | Server returns 403; app shows "Account suspended — contact support" |
| Quota exceeded | Same user-facing message as today’s Starter limit copy |
| Invalid/expired session | Redirect to login |
| Signup email already exists | Web form shows Supabase error; suggest login |

## Security

- Refresh tokens stored encrypted in `settings.json` using OS-backed entropy where available.
- Admin routes check `admin_users` allowlist on every request.
- Rate limiting on Edge Functions (Supabase built-in + per-org usage caps).
- CORS restricted to production domain and `caunpacker://` callback.
- No PII from client documents in logs or Postgres.

## Testing Strategy

### Unit (Python)

- `auth.py`: offline grace logic, quota cache merge, fingerprint stability.
- `license.py`: delegation to auth when session present.

### Integration

- Edge Function tests with Supabase local CLI (`supabase start`).
- Contract tests: desktop API `get_auth_state` shape.

### Manual

- Clean Windows VM: install → signup → ingest 5 files → verify dashboard count.
- Suspend user in admin → verify ingest blocked on desktop.
- Offline 8 days simulation → verify ingest blocked.

## Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `SUPABASE_URL` | web, desktop build, Edge Functions | Project URL |
| `SUPABASE_ANON_KEY` | web, desktop build | Public client key |
| `SUPABASE_SERVICE_ROLE_KEY` | Edge Functions only, local admin scripts | Bypass RLS for admin ops |
| `ADMIN_ALLOWED_EMAILS` | Edge Functions | Comma-separated operator emails |

## Out of Scope (Phase 1)

- Razorpay or automated billing
- License key UI (schema stub only)
- Team members / multi-user per firm
- Email notifications
- CSV export
- Device limit enforcement (track count only in Phase 1)

## Success Criteria

Phase 1 is complete when:

1. A new user can download the app, sign up on the web, and appear on the admin dashboard within 60 seconds.
2. File ingest increments the server-side monthly counter; dashboard reflects it.
3. Operator can upgrade a user to Pro and the desktop app shows unlimited quota on next check.
4. Operator can suspend a user and ingest is blocked.
5. No client document bytes or extracted financial rows are sent to Supabase (verified by network inspection).
6. App functions offline for up to 7 days with last-known quota.

## References

- Product vision auth section: `PRODUCT-VISION-CHAT-SUMMARY-2026-08-17.md` (lines 452–485)
- Existing local license stub: `apps/engine/license.py`
- Landing design tokens: `designs/ca-unpacker-landing/DESIGN.md`
- Parent product spec: `docs/superpowers/specs/2026-08-17-ca-unpacker-full-product-design.md`
