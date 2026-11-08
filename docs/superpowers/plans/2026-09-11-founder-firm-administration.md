# Founder and Firm Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Give the two approved founders separate Supabase logins and a secure dashboard for viewing firms, users, devices, usage, plans, payment state, suspension state, and an immutable audit trail.

**Architecture:** Supabase Auth proves identity; an active row in `admin_users` grants founder access. Edge Functions use the service-role client only after `requireAdmin` succeeds. Every organization mutation is performed by one database RPC that updates the organization and writes its audit record in the same transaction. The React dashboard consumes only the Edge Functions and never receives a service-role key.

**Tech Stack:** Supabase Auth/Postgres/Edge Functions (Deno + TypeScript), React 19, React Router 7, TypeScript 5.7, Vite 6, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-11-founder-admin-billing-desktop-updates-design.md`

**Global Constraints:** Never upload or expose client names, document names, paths, GST/PAN values, extracted rows, or document contents. Firm display name is the only business-data field synced from desktop. Both founders have equal permissions. Never trust a browser-supplied admin identity, audit actor, or timestamp. Preserve unrelated worktree changes.

## Task 1: Add founder, billing, suspension, and audit schema

**Files:**
- Create: `supabase/migrations/20260911100000_founder_firm_admin.sql`
- Modify: `apps/engine/tests/test_migrations.py`

- [ ] Add a failing migration contract test that reads all Supabase migrations and asserts the new schema contains `payment_status`, `paid_through`, `admin_notes`, `suspended_at`, `suspended_by`, the hardened `admin_users` columns, `admin_audit_log`, RLS enablement, and the transactional `admin_update_organization` function.
- [ ] Run `python -m pytest apps/engine/tests/test_migrations.py -q` and confirm the new test fails.
- [ ] Create enum `payment_status` with `trial`, `paid`, `overdue`, `cancelled`, and `refunded`. Add organization columns with defaults: `payment_status = 'trial'`, nullable `paid_through`, `admin_notes = ''`, nullable `suspended_at`, and nullable `suspended_by references auth.users(id)`.
- [ ] Extend `admin_users` with nullable unique `user_id references auth.users(id) on delete cascade`, `active boolean not null default true`, and `created_at timestamptz not null default now()`. Backfill `user_id` by case-insensitive email match against `auth.users`; keep `email` unique for bootstrap and recovery.
- [ ] Create `admin_audit_log(id uuid primary key default gen_random_uuid(), admin_user_id uuid, admin_email text not null, action text not null, target_type text not null, target_id text not null, before_state jsonb, after_state jsonb, created_at timestamptz not null default now())` plus indexes on `(created_at desc)` and `(target_type, target_id, created_at desc)`.
- [ ] Enable RLS on `admin_users` and `admin_audit_log` without client policies. Revoke direct table writes from `anon` and `authenticated`; Edge Functions use the service role.
- [ ] Add `admin_update_organization(p_actor_id uuid, p_actor_email text, p_org_id uuid, p_plan plan_type, p_payment_status payment_status, p_paid_through date, p_admin_notes text, p_suspended boolean)` as `security definer`, with a fixed `search_path`. It must lock the target row, build `before_state`, apply all fields, set/clear suspension metadata, insert one audit row, and return the updated organization. Revoke execution from public roles and grant only `service_role`.
- [ ] Run the migration test and `supabase db reset` against the local Supabase stack. Verify both pass.
- [ ] Commit: `git add supabase/migrations/20260911100000_founder_firm_admin.sql apps/engine/tests/test_migrations.py && git commit -m "feat: add founder administration schema"`.

## Task 2: Authorize founders from `admin_users`

**Files:**
- Modify: `supabase/functions/_shared/auth.ts`
- Create: `supabase/functions/_shared/auth_test.ts`

- [ ] Extract and test a pure `isActiveAdmin(user, rows)` decision: reject missing/anonymous users, unverified emails, inactive rows, and nonmatching identity; accept an active row matching `user_id`, or matching normalized email when `user_id` is still null.
- [ ] Run `deno test supabase/functions/_shared/auth_test.ts` and confirm failure before implementation.
- [ ] Change `requireAdmin(req)` to call `requireUser(req)`, query `admin_users` with the service client, apply `isActiveAdmin`, and return `{ user, admin }`. Keep `ADMIN_ALLOWED_EMAILS` only as an explicitly documented emergency bootstrap fallback when the table query itself is unavailable; do not let it override an inactive row.
- [ ] Return a uniform 403 response without disclosing whether an email exists in the allowlist.
- [ ] Run `deno fmt --check supabase/functions` and `deno test supabase/functions/_shared/auth_test.ts`.
- [ ] Commit: `git add supabase/functions/_shared/auth.ts supabase/functions/_shared/auth_test.ts && git commit -m "feat: authorize active founder accounts"`.

## Task 3: Build read-only organization and audit APIs

**Files:**
- Modify: `supabase/functions/admin-list-orgs/index.ts`
- Create: `supabase/functions/admin-get-org/index.ts`
- Create: `supabase/functions/admin-list-audit/index.ts`
- Create: `supabase/functions/_shared/admin_orgs.ts`
- Create: `supabase/functions/_shared/admin_orgs_test.ts`

- [ ] Write failing pure transformation tests for an organization summary and detail response. Required summary fields: organization id/name, primary email, plan, payment status, paid-through date, suspended state, current-month files, lifetime files, device count, latest app version, last active time, and created time. Detail additionally returns all profiles, all devices (label/version/last seen), 12 months of usage, and admin notes.
- [ ] Run `deno test supabase/functions/_shared/admin_orgs_test.ts` and confirm failure.
- [ ] Implement typed mappers in `_shared/admin_orgs.ts`; missing related rows must map to zero/null instead of dropping the organization.
- [ ] Extend `admin-list-orgs` with validated `search`, `limit` (1–100), and `offset` query parameters and return `{ orgs, total }`. Search only normalized firm name and user email.
- [ ] Implement `admin-get-org` as `GET ?org_id=<uuid>`, returning 400 for malformed IDs and 404 for absent organizations.
- [ ] Implement `admin-list-audit` as `GET` with validated `org_id`, `limit`, and `offset`, ordered newest first. Return actor email, action, before/after state, and server timestamp.
- [ ] Ensure all three endpoints call `requireAdmin` before creating or using the service client for business queries.
- [ ] Run Deno tests and formatting.
- [ ] Commit: `git add supabase/functions/admin-list-orgs supabase/functions/admin-get-org supabase/functions/admin-list-audit supabase/functions/_shared/admin_orgs* && git commit -m "feat: expose founder organization insights"`.

## Task 4: Build the audited organization mutation API

**Files:**
- Create: `supabase/functions/admin-update-org/index.ts`
- Create: `supabase/functions/_shared/admin_updates.ts`
- Create: `supabase/functions/_shared/admin_updates_test.ts`
- Delete: `supabase/functions/admin-update-plan/index.ts`

- [ ] Write failing validation tests for the exact request shape `{ org_id, plan, payment_status, paid_through, admin_notes, suspended }`. Reject extra keys, invalid UUIDs/enums/dates, notes over 2,000 characters, and contradictory suspended state.
- [ ] Run the new Deno test and confirm failure.
- [ ] Implement parsing with `rejectExtraKeys` and explicit enum/date validators. Treat an empty paid-through string as null and trim notes.
- [ ] Implement `admin-update-org`: require founder, call only the `admin_update_organization` RPC, pass the authenticated founder id/email as actor values, and return the RPC row. Do not perform a separate client-side audit insert.
- [ ] Remove the unaudited `admin-update-plan` endpoint and update `supabase/config.toml` only if function-specific configuration exists there.
- [ ] Test that a failed update produces no audit row and a successful update produces exactly one row by adding a local integration SQL assertion or Edge Function integration test.
- [ ] Run Deno tests, formatting, and `supabase db reset`.
- [ ] Commit: `git add -A supabase/functions/admin-update-org supabase/functions/admin-update-plan supabase/functions/_shared/admin_updates* supabase/config.toml && git commit -m "feat: audit founder account changes"`.

## Task 5: Sync the local firm display name safely

**Files:**
- Create: `supabase/functions/sync-firm/index.ts`
- Modify: `apps/engine/auth.py`
- Modify: `apps/desktop/app.py`
- Modify: `apps/engine/tests/test_auth.py`
- Modify: `apps/desktop/tests/test_auth_api_contract.py`

- [ ] Add failing tests that `auth.sync_firm(" Rao & Co ")` calls only `sync-firm` with `{ "firm_name": "Rao & Co" }`, rejects blank or over-160-character names, and never sends local client/document fields.
- [ ] Add a failing desktop contract test that `DesktopApi.save_firm` still succeeds locally when remote sync is offline, and attempts sync only after the local save succeeds.
- [ ] Implement `sync-firm` Edge Function: require user, validate the sole `firm_name` field, load the caller's organization, and update only `organizations.name`.
- [ ] Add public `auth.call_function(name, body)` or a narrowly scoped `sync_firm(name)` wrapper over `_call_function`; do not expose tokens to the UI.
- [ ] Update `DesktopApi.save_firm` to save locally first, then best-effort sync in a daemon thread. Include `firm_sync_pending` in its response when the remote call cannot complete so a later startup/profile refresh can retry.
- [ ] Run `python -m pytest apps/engine/tests/test_auth.py apps/desktop/tests/test_auth_api_contract.py -q` and the Deno validation test.
- [ ] Commit: `git add supabase/functions/sync-firm apps/engine/auth.py apps/desktop/app.py apps/engine/tests/test_auth.py apps/desktop/tests/test_auth_api_contract.py && git commit -m "feat: sync firm display names"`.

## Task 6: Add a tested admin web API client

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/src/test/setup.ts`
- Modify: `apps/web/src/lib/admin.ts`
- Create: `apps/web/src/lib/admin.test.ts`

- [ ] Add Vitest, jsdom, Testing Library React, Testing Library DOM, and jest-dom dev dependencies plus `test` and `test:run` scripts.
- [ ] Write failing client tests for authorization headers, list pagination/search encoding, detail retrieval, update payloads, audit retrieval, 401/403 mapping, and non-auth server errors.
- [ ] Replace the legacy `PlanType` containing `suspended` with independent `PlanType = "starter" | "pro"` and `PaymentStatus`. Define `AdminOrgSummary`, `AdminOrgDetail`, `AdminAuditEntry`, and `AdminOrgUpdate` matching Edge Function JSON exactly.
- [ ] Implement `fetchAdminOrgs`, `fetchAdminOrg`, `updateAdminOrg`, and `fetchAdminAudit` through one authenticated `invokeAdminFunction` helper. Retire `updateOrgPlan`.
- [ ] Run `npm --prefix apps/web run test:run` and `npm --prefix apps/web run build`.
- [ ] Commit: `git add apps/web/package*.json apps/web/vitest.config.ts apps/web/src/test apps/web/src/lib/admin* && git commit -m "test: cover founder dashboard API client"`.

## Task 7: Harden the admin session guard

**Files:**
- Modify: `apps/web/src/components/AdminGuard.tsx`
- Create: `apps/web/src/components/AdminGuard.test.tsx`

- [ ] Write failing tests for initial session hydration, login/logout auth events, verified non-admin 403, expired session redirect, and a retriable network/server error that must not be mislabeled as forbidden.
- [ ] Implement one `getSession()` hydration plus `onAuthStateChange` subscription with cleanup. Probe founder access through `fetchAdminOrgs({ limit: 1 })`.
- [ ] Render distinct loading, access-denied, and temporary-error states; temporary errors include a Retry button and preserve the session.
- [ ] Run the component test and web build.
- [ ] Commit: `git add apps/web/src/components/AdminGuard* && git commit -m "fix: harden founder dashboard session guard"`.

## Task 8: Build the founder dashboard screens

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/AdminLayout.tsx`
- Modify: `apps/web/src/pages/admin/Overview.tsx`
- Modify: `apps/web/src/pages/admin/Users.tsx`
- Modify: `apps/web/src/pages/admin/UserDetail.tsx`
- Create: `apps/web/src/pages/admin/AuditLog.tsx`
- Create: `apps/web/src/pages/admin/Users.test.tsx`
- Create: `apps/web/src/pages/admin/UserDetail.test.tsx`
- Modify: `apps/web/src/styles/global.css`

- [ ] Write failing UI tests for search/loading/empty/error states, plan and payment badges, usage/device/version display, detail history, audited edit submission, suspend/restore confirmation, and actor/action rendering in the audit log.
- [ ] Change navigation labels to Overview, Firms, Releases (added by the next plan), and Audit. Route `/admin/users` may remain for compatibility but display “Firms”.
- [ ] Update Overview cards to show total firms, active firms, files this month, paid accounts, overdue accounts, and version distribution from the summary API.
- [ ] Rebuild Users as a searchable firm table with pagination and no inline mutation control. Clicking a row opens detail.
- [ ] Rebuild UserDetail from `admin-get-org`; show profiles, 12-month usage, devices, current app versions, plan/payment metadata, and notes. One edit form controls plan, payment status, paid-through, notes, and suspended state. Require a browser confirmation before suspension or restoration.
- [ ] Add AuditLog with pagination and optional organization filtering.
- [ ] Add responsive styles without changing public signup/login layout.
- [ ] Run web tests and build.
- [ ] Commit: `git add apps/web/src && git commit -m "feat: build founder firm administration dashboard"`.

## Task 9: Provision, deploy, and smoke-test the two founders

**Files:**
- Modify: `docs/superpowers/specs/2026-09-11-founder-admin-billing-desktop-updates-design.md` only if deployment reveals an approved design correction.

- [ ] Apply migrations to staging, then upsert exactly the two founder emails/user IDs into `admin_users` with `active = true`. Do not put passwords or tokens in source control.
- [ ] Deploy `admin-list-orgs`, `admin-get-org`, `admin-update-org`, `admin-list-audit`, and `sync-firm` with JWT verification enabled.
- [ ] Deploy the web app and sign in separately as each founder. Verify both have equal access; verify a normal user receives 403.
- [ ] Change a staging firm's plan/payment/note/suspension state and verify exactly one audit row with the correct founder identity and before/after JSON for each mutation.
- [ ] Sign into desktop as the staging user, save a firm name, and verify only that display name appears in Supabase.
- [ ] Run `python -m pytest apps/engine/tests/test_auth.py apps/desktop/tests/test_auth_api_contract.py apps/engine/tests/test_migrations.py -q`, Deno tests, web tests, and web build.
- [ ] Commit any deployment-only configuration changes with `git commit -m "chore: configure founder administration deployment"`; skip the commit if no tracked files changed.

## Final Verification

- [ ] Confirm the service-role key is absent from `apps/web`, `apps/desktop`, Git history for this branch, and built frontend assets.
- [ ] Confirm non-founders cannot enumerate organizations or audit entries.
- [ ] Confirm suspended accounts cannot ingest but can still sign out and preserve local files.
- [ ] Confirm the API never returns or accepts client/document data.
- [ ] Confirm `git status --short` contains only intentional files and pre-existing unrelated user changes.
