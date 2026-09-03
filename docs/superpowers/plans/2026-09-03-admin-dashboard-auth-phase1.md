# Admin Dashboard & Auth — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Supabase-backed control plane with signup/login web pages, operator admin dashboard, and desktop session auth so new CA firms get instant Starter access while client documents never leave the PC.

**Architecture:** Supabase Auth + Postgres hold org/profile/usage metadata. Deno Edge Functions enforce quota and admin mutations server-side. A Vite/React app on Netlify handles signup, login, and admin UI. The Python desktop app stores an encrypted refresh token, calls Edge Functions for quota/usage, and opens the browser for auth when unsigned.

**Tech Stack:** Supabase (Auth, Postgres, Edge Functions/Deno), Vite + React + TypeScript, `@supabase/supabase-js`, Python 3.13, `httpx`, `cryptography`, pywebview, pytest, Inno Setup.

**Spec:** `docs/superpowers/specs/2026-09-03-admin-dashboard-auth-design.md`

## Global Constraints

- Client document contents, extracted transactions, invoice data, PAN/GSTIN from documents, and client names parsed from files **never** leave the CA's PC.
- Server receives **metadata only**: firm identity, plan, subscription state, files-processed counters, client-count counters, device fingerprints (hashed), and app version.
- Authentication is email + password via Supabase Auth.
- New users get **instant Starter access** (100 files/month) on signup.
- Offline grace: desktop app may continue with last-known quota for up to **7 days**; after that, reconnect is required before ingest.
- Test keys (`STARTER-TEST`, `PRO-TEST`) remain available in development builds only (`CA_UNPACKER_DEV=1`); production builds require Supabase auth.
- `license.py` and `dump.py` must not import network libraries directly (existing gate test); network calls live in `auth.py` only.
- Starter file limit is **100** per calendar month; Pro is unlimited (`null`); suspended is **0**.
- Styling tokens: desk `#2c3330`, paper `#f4efe3`, ink `#1b3028`, accent `#c45a2a` (from `designs/ca-unpacker-landing/DESIGN.md`).

## File Map

| Path | Responsibility |
|------|----------------|
| `supabase/config.toml` | Local Supabase CLI config |
| `supabase/migrations/20260903100000_auth_schema.sql` | Tables, enums, RLS, signup trigger |
| `supabase/functions/check-quota/index.ts` | Pre-ingest quota validation |
| `supabase/functions/record-usage/index.ts` | Post-ingest counter increment |
| `supabase/functions/heartbeat/index.ts` | Last-active + device upsert |
| `supabase/functions/admin-list-orgs/index.ts` | Operator org list |
| `supabase/functions/admin-update-plan/index.ts` | Operator plan change |
| `supabase/functions/_shared/auth.ts` | JWT verify, admin allowlist helper |
| `supabase/functions/_shared/plans.ts` | Plan limits (`starter`=100, `pro`=null) |
| `apps/web/package.json` | Vite/React web app |
| `apps/web/src/lib/supabase.ts` | Browser Supabase client |
| `apps/web/src/pages/Signup.tsx` | Email/password/firm signup + deep link |
| `apps/web/src/pages/Login.tsx` | Login + deep link |
| `apps/web/src/pages/admin/Overview.tsx` | Operator stats |
| `apps/web/src/pages/admin/Users.tsx` | Org table |
| `apps/web/src/pages/admin/UserDetail.tsx` | Plan change, suspend, devices |
| `apps/web/src/styles/tokens.css` | Landing palette |
| `apps/web/netlify.toml` | SPA routes for `/signup`, `/login`, `/admin/*` |
| `apps/engine/auth.py` | Session storage, quota sync, offline grace |
| `apps/engine/auth_config.py` | `SUPABASE_URL`, `SUPABASE_ANON_KEY` from env/build |
| `apps/engine/tests/test_auth.py` | Unit tests for auth offline logic |
| `apps/engine/license.py` | Delegate to `auth` when session present |
| `apps/desktop/app.py` | `get_auth_state`, `open_signup`, `open_login`, `logout`, deep-link handler |
| `apps/ui/index.html` | Auth buttons, quota banner |
| `apps/ui/app.js` | Wire auth UI to desktop API |
| `apps/ui/styles.css` | Auth banner styles |
| `installer/ca-unpacker.iss` | `caunpacker://` protocol registry |
| `.env.example` | Document required env vars |
| `requirements.txt` | Add `httpx>=0.27` |

---

### Task 1: Supabase Project Scaffold and Database Schema

**Files:**
- Create: `supabase/config.toml`
- Create: `supabase/migrations/20260903100000_auth_schema.sql`
- Create: `.env.example`
- Modify: `.gitignore` (ignore `.env`, `supabase/.branches`)

**Interfaces:**
- Produces: Postgres tables `organizations`, `profiles`, `devices`, `usage_monthly`, `admin_users`, `license_keys`; enum `plan_type`; RLS policies; trigger `handle_new_user` on `auth.users` insert.

- [ ] **Step 1: Init Supabase folder**

Run from repo root:

```bash
npx supabase init
```

- [ ] **Step 2: Write migration SQL**

Create `supabase/migrations/20260903100000_auth_schema.sql`:

```sql
create type plan_type as enum ('starter', 'pro', 'suspended');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan plan_type not null default 'starter',
  license_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  org_id uuid not null references public.organizations(id) on delete cascade,
  email text not null,
  role text not null default 'owner' check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  last_active_at timestamptz
);

create table public.devices (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  fingerprint_sha256 text not null,
  label text not null default '',
  app_version text not null default '',
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  active boolean not null default true,
  unique (org_id, fingerprint_sha256)
);

create table public.usage_monthly (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  month text not null,
  files_processed integer not null default 0,
  clients_created integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (org_id, month)
);

create table public.admin_users (
  email text primary key
);

create table public.license_keys (
  id uuid primary key default gen_random_uuid(),
  key_hash text not null unique,
  plan plan_type not null default 'pro',
  org_id uuid references public.organizations(id),
  created_at timestamptz not null default now(),
  redeemed_at timestamptz,
  revoked_at timestamptz
);

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  new_org_id uuid;
  firm_name text;
begin
  firm_name := coalesce(new.raw_user_meta_data->>'firm_name', 'My firm');
  insert into public.organizations (name, plan) values (firm_name, 'starter')
    returning id into new_org_id;
  insert into public.profiles (id, org_id, email, role)
    values (new.id, new_org_id, new.email, 'owner');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.devices enable row level security;
alter table public.usage_monthly enable row level security;
alter table public.admin_users enable row level security;
alter table public.license_keys enable row level security;

create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);
create policy "orgs_select_own" on public.organizations
  for select using (
    id in (select org_id from public.profiles where id = auth.uid())
  );
create policy "usage_select_own" on public.usage_monthly
  for select using (
    org_id in (select org_id from public.profiles where id = auth.uid())
  );
create policy "devices_upsert_own" on public.devices
  for all using (
    user_id = auth.uid()
  ) with check (user_id = auth.uid());
```

- [ ] **Step 3: Add `.env.example`**

```env
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
ADMIN_ALLOWED_EMAILS=you@example.com,friend@example.com
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
CA_UNPACKER_AUTH_URL=https://your-domain.netlify.app
```

- [ ] **Step 4: Apply migration locally**

```bash
npx supabase start
npx supabase db reset
```

Expected: migration applies without error; `\dt public.*` shows all six tables.

- [ ] **Step 5: Seed admin allowlist**

In Supabase SQL editor (or local):

```sql
insert into public.admin_users (email) values
  ('you@example.com'),
  ('friend@example.com');
```

Replace with real founder emails.

- [ ] **Step 6: Commit**

```bash
git add supabase/ .env.example .gitignore
git commit -m "feat: add Supabase auth schema and migrations"
```

---

### Task 2: Shared Edge Function Helpers and Quota Functions

**Files:**
- Create: `supabase/functions/_shared/auth.ts`
- Create: `supabase/functions/_shared/plans.ts`
- Create: `supabase/functions/check-quota/index.ts`
- Create: `supabase/functions/record-usage/index.ts`
- Create: `supabase/functions/heartbeat/index.ts`

**Interfaces:**
- Consumes: Task 1 schema (`organizations.plan`, `usage_monthly`)
- Produces:
  - `check-quota` POST body `{ file_count: number }` → `{ allowed: boolean, files_used: number, file_limit: number | null, plan: string }`
  - `record-usage` POST body `{ files_processed: number }` → `{ files_used: number, file_limit: number | null, plan: string }`
  - `heartbeat` POST body `{ app_version: string, device_label: string, fingerprint_sha256: string }` → `{ ok: true }`

- [ ] **Step 1: Write `plans.ts`**

```typescript
export const PLAN_LIMITS: Record<string, number | null> = {
  starter: 100,
  pro: null,
  suspended: 0,
};

export function currentMonth(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
```

- [ ] **Step 2: Write `auth.ts`**

```typescript
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

export function userClient(req: Request) {
  const auth = req.headers.get("Authorization") ?? "";
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: auth } } },
  );
}

export function serviceClient() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

export async function requireUser(req: Request) {
  const supabase = userClient(req);
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new Response("Unauthorized", { status: 401 });
  return { supabase, user: data.user };
}

export async function requireAdmin(req: Request) {
  const { user } = await requireUser(req);
  const allowed = (Deno.env.get("ADMIN_ALLOWED_EMAILS") ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  if (!allowed.includes((user.email ?? "").toLowerCase())) {
    throw new Response("Forbidden", { status: 403 });
  }
  return user;
}
```

- [ ] **Step 3: Implement `check-quota/index.ts`**

Logic:
1. Parse `{ file_count }`; reject if `file_count < 0` or body contains keys other than `file_count`.
2. Load user's `profiles.org_id` → `organizations.plan`.
3. Load or default `usage_monthly` for `currentMonth()`.
4. Compute `limit = PLAN_LIMITS[plan]`; `allowed = limit === null || files_used + file_count <= limit`.
5. Return JSON `{ allowed, files_used, file_limit: limit, plan }`; 403 if plan is `suspended`.

- [ ] **Step 4: Implement `record-usage/index.ts`**

Logic:
1. Parse `{ files_processed }` (positive int only).
2. Upsert `usage_monthly` with `files_processed = files_processed + EXCLUDED.files_processed` via RPC or read-modify-write in transaction.
3. Return updated quota snapshot.

- [ ] **Step 5: Implement `heartbeat/index.ts`**

Logic:
1. Parse `{ app_version, device_label, fingerprint_sha256 }`.
2. Upsert `devices` on `(org_id, fingerprint_sha256)`.
3. Set `profiles.last_active_at = now()`.

- [ ] **Step 6: Deploy and smoke-test**

```bash
npx supabase functions serve
```

Manual curl with a test user JWT:

```bash
curl -X POST http://127.0.0.1:54321/functions/v1/check-quota \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"file_count": 5}'
```

Expected: `{ "allowed": true, "files_used": 0, "file_limit": 100, "plan": "starter" }`.

- [ ] **Step 7: Commit**

```bash
git add supabase/functions/
git commit -m "feat: add quota, usage, and heartbeat edge functions"
```

---

### Task 3: Admin Edge Functions

**Files:**
- Create: `supabase/functions/admin-list-orgs/index.ts`
- Create: `supabase/functions/admin-update-plan/index.ts`

**Interfaces:**
- Consumes: `requireAdmin` from `_shared/auth.ts`
- Produces:
  - `admin-list-orgs` GET → `{ orgs: Array<{ id, name, plan, email, files_used, file_limit, last_active_at, device_count, created_at }> }`
  - `admin-update-plan` POST `{ org_id: string, plan: 'starter'|'pro'|'suspended' }` → `{ ok: true, plan }`

- [ ] **Step 1: Implement `admin-list-orgs`**

Use `serviceClient()` after `requireAdmin`. Join `organizations` ← `profiles` ← `usage_monthly` (current month) ← device count subquery.

- [ ] **Step 2: Implement `admin-update-plan`**

Validate `plan` enum; `update organizations set plan = $1, updated_at = now() where id = $2`.

- [ ] **Step 3: Smoke-test with admin JWT**

```bash
curl http://127.0.0.1:54321/functions/v1/admin-list-orgs \
  -H "Authorization: Bearer <admin-jwt>"
```

Expected: JSON array including test signup org.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/admin-list-orgs supabase/functions/admin-update-plan
git commit -m "feat: add admin list and plan-update edge functions"
```

---

### Task 4: Web App Scaffold (Signup + Login)

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/lib/supabase.ts`
- Create: `apps/web/src/pages/Signup.tsx`
- Create: `apps/web/src/pages/Login.tsx`
- Create: `apps/web/src/styles/tokens.css`
- Create: `apps/web/netlify.toml`

**Interfaces:**
- Produces: `/signup` form (email, password, firm name) → Supabase `signUp({ email, password, options: { data: { firm_name } } })`
- On success with `?redirect=desktop`: `window.location.href = 'caunpacker://auth/callback#' + hash from session`
- `/login` same deep-link redirect pattern

- [ ] **Step 1: Scaffold Vite app**

```bash
cd apps/web
npm create vite@latest . -- --template react-ts
npm install @supabase/supabase-js react-router-dom
```

- [ ] **Step 2: Add routes in `App.tsx`**

Routes: `/signup`, `/login`, `/admin/*` (placeholder), `/` redirects to landing or signup.

- [ ] **Step 3: Implement `Signup.tsx`**

```tsx
// On submit:
const { data, error } = await supabase.auth.signUp({
  email,
  password,
  options: { data: { firm_name: firmName } },
});
if (error) { setError(error.message); return; }
if (searchParams.get("redirect") === "desktop" && data.session) {
  const { access_token, refresh_token } = data.session;
  window.location.href =
    `caunpacker://auth/callback#access_token=${access_token}&refresh_token=${refresh_token}`;
}
```

- [ ] **Step 4: Implement `Login.tsx`** (same redirect after `signInWithPassword`)

- [ ] **Step 5: Style with tokens.css** matching landing palette

- [ ] **Step 6: Add `netlify.toml`**

```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

- [ ] **Step 7: Local verify**

```bash
npm run dev
```

Open `http://localhost:5173/signup?redirect=desktop`; confirm Supabase user + org row created.

- [ ] **Step 8: Commit**

```bash
git add apps/web/
git commit -m "feat: add signup and login web pages with desktop redirect"
```

---

### Task 5: Admin Dashboard Web UI

**Files:**
- Create: `apps/web/src/pages/admin/Overview.tsx`
- Create: `apps/web/src/pages/admin/Users.tsx`
- Create: `apps/web/src/pages/admin/UserDetail.tsx`
- Create: `apps/web/src/components/AdminGuard.tsx`
- Modify: `apps/web/src/App.tsx`

**Interfaces:**
- Consumes: `admin-list-orgs`, `admin-update-plan` Edge Functions
- Produces: Protected `/admin`, `/admin/users`, `/admin/users/:id` pages

- [ ] **Step 1: Write `AdminGuard.tsx`**

On mount: `supabase.auth.getSession()`; if no session → redirect `/login?next=/admin`. After session, call `admin-list-orgs`; 403 → show "Not an admin".

- [ ] **Step 2: Implement `Overview.tsx`**

Compute from org list: total firms, active in 7 days (`last_active_at`), files this month sum, starter vs pro counts.

- [ ] **Step 3: Implement `Users.tsx`**

Table columns per spec; row click → detail; inline plan dropdown calls `admin-update-plan`.

- [ ] **Step 4: Implement `UserDetail.tsx`**

Show usage history (`usage_monthly` via service function or extend `admin-list-orgs` with history param), device list, suspend toggle (= `plan: suspended`).

- [ ] **Step 5: Manual verify**

Log in as allowlisted email → see test users → change plan to `pro` → confirm DB update.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/admin apps/web/src/components/AdminGuard.tsx
git commit -m "feat: add operator admin dashboard"
```

---

### Task 6: Desktop Auth Module

**Files:**
- Create: `apps/engine/auth_config.py`
- Create: `apps/engine/auth.py`
- Create: `apps/engine/tests/test_auth.py`
- Modify: `requirements.txt` (add `httpx>=0.27`)

**Interfaces:**
- Produces:
  - `device_fingerprint() -> str` (sha256 hex)
  - `get_session() -> dict | None`
  - `login_via_tokens(access_token: str, refresh_token: str) -> dict`
  - `logout() -> None`
  - `refresh_session() -> dict | None`
  - `fetch_quota() -> dict`
  - `check_can_ingest(file_count: int) -> None` (raises ValueError like license)
  - `record_usage(file_count: int) -> dict`
  - `get_auth_state() -> dict` (signed_in, email, plan, files_used, file_limit, offline, last_sync_at)

- [ ] **Step 1: Write failing tests**

Create `apps/engine/tests/test_auth.py`:

```python
def test_offline_grace_allows_within_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    auth.save_quota_cache({
        "files_used": 10,
        "file_limit": 100,
        "plan": "starter",
        "synced_at": "2026-09-01T10:00:00",
    })
    auth.check_can_ingest_offline(5, today=date(2026, 9, 7))  # 6 days later

def test_offline_grace_blocks_after_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine import auth

    auth.save_quota_cache({
        "files_used": 10,
        "file_limit": 100,
        "plan": "starter",
        "synced_at": "2026-08-25T10:00:00",
    })
    with pytest.raises(ValueError, match="Connect to the internet"):
        auth.check_can_ingest_offline(1, today=date(2026, 9, 3))

def test_fingerprint_is_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from apps.engine.auth import device_fingerprint

    assert device_fingerprint() == device_fingerprint()
    assert len(device_fingerprint()) == 64
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python -m pytest apps/engine/tests/test_auth.py -v
```

- [ ] **Step 3: Implement `auth.py`**

Key implementation notes:
- Encrypt refresh token with `cryptography.fernet.Fernet` keyed from machine id + salt in `settings.json` under `auth_refresh_token_enc`.
- Store quota cache under `auth_quota_cache` in settings.
- `OFFLINE_GRACE_DAYS = 7`.
- `check_can_ingest`: if session + network → POST `check-quota`; else `check_can_ingest_offline`.
- `record_usage`: POST `record-usage` then update local cache.
- Reject request bodies that include document-related keys (defensive).

- [ ] **Step 4: Run tests — expect PASS**

```bash
python -m pytest apps/engine/tests/test_auth.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/engine/auth.py apps/engine/auth_config.py apps/engine/tests/test_auth.py requirements.txt
git commit -m "feat: add desktop auth module with offline grace"
```

---

### Task 7: License Delegation and Dev-Mode Gate

**Files:**
- Modify: `apps/engine/license.py`
- Modify: `apps/engine/tests/test_stage9_stage10_gate.py`

**Interfaces:**
- Consumes: `auth.get_auth_state()`, `auth.check_can_ingest()`, `auth.record_usage()`
- Produces: `get_license_status()` includes `auth_mode: 'supabase'|'dev'`; test keys only when `CA_UNPACKER_DEV=1`

- [ ] **Step 1: Write failing test**

Add to `test_auth.py` or stage9 gate:

```python
def test_license_delegates_when_session_present(monkeypatch):
    monkeypatch.setenv("CA_UNPACKER_DEV", "1")
    monkeypatch.setattr("apps.engine.auth.get_auth_state", lambda: {
        "signed_in": True, "plan": "pro", "files_used": 0, "file_limit": None,
    })
    from apps.engine.license import get_license_status
    status = get_license_status()
    assert status["plan"] == "pro"
    assert status["auth_mode"] == "supabase"
```

- [ ] **Step 2: Update `license.py`**

```python
def _use_supabase() -> bool:
    from apps.engine.auth import get_auth_state
    return bool(get_auth_state().get("signed_in"))

def get_license_status(today=None):
    if _use_supabase():
        from apps.engine.auth import get_auth_state
        state = get_auth_state()
        # map to existing status shape + auth_mode
        ...
    # existing local/test-key path only if os.environ.get("CA_UNPACKER_DEV") == "1"
    ...
```

- [ ] **Step 3: Run full engine tests**

```bash
python -m pytest apps/engine/tests/ -v
```

Expected: all pass; `license.py` still has no `httpx` import.

- [ ] **Step 4: Commit**

```bash
git add apps/engine/license.py apps/engine/tests/
git commit -m "feat: delegate license quota to supabase auth session"
```

---

### Task 8: Desktop API Bridge and Deep-Link Handler

**Files:**
- Modify: `apps/desktop/app.py`
- Create: `apps/desktop/tests/test_auth_api_contract.py`

**Interfaces:**
- Produces API methods exposed to pywebview:
  - `get_auth_state() -> dict`
  - `open_signup() -> dict` (opens browser)
  - `open_login() -> dict`
  - `logout() -> dict`
  - `handle_auth_callback(url: str) -> dict` (parses `caunpacker://auth/callback#...`)

- [ ] **Step 1: Write contract test**

```python
def test_get_auth_state_shape():
    from apps.desktop.app import DesktopApi
    api = DesktopApi()
    state = api.get_auth_state()
    assert set(state.keys()) >= {
        "signed_in", "email", "plan", "files_used", "file_limit", "offline"
    }
```

- [ ] **Step 2: Implement API methods**

- `open_signup` / `open_login`: `webbrowser.open(f"{AUTH_URL}/signup?redirect=desktop")`
- Startup hook: `auth.refresh_session()` then `auth.fetch_quota()`
- Register protocol handler listener if pywebview supports second-instance args (or poll registry on Windows)

- [ ] **Step 3: Implement `handle_auth_callback`**

Parse fragment `access_token` and `refresh_token`; call `auth.login_via_tokens`; return `get_auth_state()`.

- [ ] **Step 4: Run contract test**

```bash
python -m pytest apps/desktop/tests/test_auth_api_contract.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/
git commit -m "feat: expose auth API and deep-link callback to desktop UI"
```

---

### Task 9: Desktop UI Auth State

**Files:**
- Modify: `apps/ui/index.html`
- Modify: `apps/ui/app.js`
- Modify: `apps/ui/styles.css`

**Interfaces:**
- Consumes: `get_auth_state`, `open_signup`, `open_login`, `logout`
- Produces: Signed-out gate with Sign up / Log in; signed-in quota banner

- [ ] **Step 1: Add auth panel to `index.html`**

Replace licence-key modal primary flow with:

```html
<div id="auth-gate" class="hidden">
  <p>Sign in to use CA Unpacker.</p>
  <button id="auth-signup">Sign up</button>
  <button id="auth-login">Log in</button>
</div>
<div id="quota-banner" class="hidden">
  <span id="quota-text"></span>
  <span class="privacy">Financial data transmitted: NONE</span>
</div>
```

Keep licence modal behind dev flag or remove from production build.

- [ ] **Step 2: Wire `app.js`**

On `get_state()` / startup:
- If `!auth.signed_in` → show `#auth-gate`, disable drop zone
- Else → show quota banner, enable app
- Buttons call `open_signup()` / `open_login()` / `logout()`

- [ ] **Step 3: Manual smoke**

Run desktop app with `CA_UNPACKER_DEV=0` and no session → auth gate visible.

- [ ] **Step 4: Commit**

```bash
git add apps/ui/
git commit -m "feat: add auth gate and quota banner to desktop UI"
```

---

### Task 10: Installer URL Protocol Registration

**Files:**
- Modify: `installer/ca-unpacker.iss`

**Interfaces:**
- Produces: Windows registry keys so `caunpacker://auth/callback` launches `CAUnpacker.exe` with URL arg

- [ ] **Step 1: Add Inno Setup registry section**

```iss
[Registry]
Root: hkcu; Subkey: "Software\Classes\caunpacker"; ValueType: string; ValueName: ""; ValueData: "URL:CA Unpacker Protocol"; Flags: uninsdeletekey
Root: hkcu; Subkey: "Software\Classes\caunpacker"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletevalue
Root: hkcu; Subkey: "Software\Classes\caunpacker\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey
```

- [ ] **Step 2: Update `apps/desktop/__main__.py` or `app.py`** to read `sys.argv[1]` when it starts with `caunpacker://` and call `handle_auth_callback`.

- [ ] **Step 3: Document manual test**

Build installer → install → browser redirect `caunpacker://auth/callback#...` → app receives tokens.

- [ ] **Step 4: Commit**

```bash
git add installer/ca-unpacker.iss apps/desktop/
git commit -m "feat: register caunpacker deep-link protocol in installer"
```

---

### Task 11: Netlify Deployment and Environment Wiring

**Files:**
- Modify: root `netlify.toml` OR deploy `apps/web` as separate Netlify site
- Modify: `apps/engine/auth_config.py` (read `CA_UNPACKER_AUTH_URL`)

- [ ] **Step 1: Configure Netlify site** for `apps/web` with env vars `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

- [ ] **Step 2: Deploy Edge Functions** to Supabase production:

```bash
npx supabase functions deploy check-quota
npx supabase functions deploy record-usage
npx supabase functions deploy heartbeat
npx supabase functions deploy admin-list-orgs
npx supabase functions deploy admin-update-plan
```

Set secrets: `SUPABASE_SERVICE_ROLE_KEY`, `ADMIN_ALLOWED_EMAILS`.

- [ ] **Step 3: Set desktop build env** `CA_UNPACKER_AUTH_URL` to deployed Netlify URL; `SUPABASE_URL` + `SUPABASE_ANON_KEY` in PyInstaller spec or `auth_config.py`.

- [ ] **Step 4: Commit deployment docs** in plan or README snippet (not a new markdown file unless requested).

- [ ] **Step 5: Commit config changes**

```bash
git add netlify.toml apps/engine/auth_config.py
git commit -m "chore: wire auth URLs and Netlify deployment config"
```

---

### Task 12: End-to-End Verification (Manual Gate)

**Files:** none (verification only)

- [ ] **Step 1: Signup flow**

Install app → Sign up → confirm org appears in `/admin/users` within 60s.

- [ ] **Step 2: Usage sync**

Ingest 5 files → dashboard shows `files_used: 5`.

- [ ] **Step 3: Plan upgrade**

Set user to Pro in admin → desktop refresh shows unlimited quota.

- [ ] **Step 4: Suspend**

Suspend user → ingest blocked with clear message.

- [ ] **Step 5: Privacy check**

Run Fiddler/Wireshark during ingest → confirm no PDF/invoice bytes to Supabase; only JSON metadata to Edge Functions.

- [ ] **Step 6: Offline grace**

Disconnect network → ingest works with cached quota; advance clock 8 days → ingest blocked.

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|------------------|------|
| Supabase schema + RLS | Task 1 |
| Signup trigger creates org/profile | Task 1 |
| Edge Functions (quota, usage, heartbeat, admin) | Tasks 2–3 |
| Signup/login web + deep link | Task 4 |
| Admin dashboard (overview, users, detail) | Task 5 |
| Desktop `auth.py` module | Task 6 |
| `license.py` delegation | Task 7 |
| Desktop API bridge | Task 8 |
| UI auth gate + quota banner | Task 9 |
| Installer protocol handler | Task 10 |
| Netlify + env wiring | Task 11 |
| Success criteria 1–6 | Task 12 |
| Offline 7-day grace | Task 6 |
| Dev-only test keys | Task 7 |
| Phase 2 out of scope (CSV, Razorpay, license UI) | Not in plan |

## Placeholder Scan

No TBD/TODO/implement-later entries. Each task names exact files and function signatures.

## Type Consistency

- Plan enum values: `starter`, `pro`, `suspended` — consistent across SQL, Edge Functions, Python, and UI.
- Quota response shape `{ allowed, files_used, file_limit, plan }` used in Edge Functions, `auth.py`, and `get_license_status()`.
- Deep link format: `caunpacker://auth/callback#access_token=...&refresh_token=...` — consistent in web pages, installer, and desktop handler.
