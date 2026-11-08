# Release Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let either founder prepare a Windows release as a draft and explicitly decide whether to publish or withdraw it globally, while signed-in clients can retrieve only the one currently applicable published release.

**Architecture:** Release metadata is stored in Supabase; installer binaries remain on approved HTTPS GitHub Release hosts. Founder Edge Functions own draft, publish, and withdrawal transitions and write audit rows transactionally. A separate user endpoint selects a published update using semantic-version rules and never exposes drafts. The admin React app requires an explicit second confirmation before publication.

**Tech Stack:** Supabase Postgres/Edge Functions (Deno + TypeScript), React 19, TypeScript, Vitest, GitHub Releases.

**Spec:** `docs/superpowers/specs/2026-09-11-founder-admin-billing-desktop-updates-design.md`

**Prerequisite:** Complete `docs/superpowers/plans/2026-09-11-founder-firm-administration.md` through the shared founder authorization and audit work.

**Global Constraints:** Only `published` releases reach users. Founders have equal publish authority, but publishing always requires a fresh explicit confirmation in the UI. Release URLs must be HTTPS and use the approved GitHub asset hosts. SHA-256 and exact byte size are mandatory. Never accept actor identity or publication timestamps from the browser.

## Task 1: Add the release state machine schema

**Files:**
- Create: `supabase/migrations/20260911110000_app_releases.sql`
- Modify: `apps/engine/tests/test_migrations.py`

- [ ] Add a failing migration contract test for release status enum, all `app_releases` fields, unique version, validation constraints, RLS, transition RPCs, and audit writes.
- [ ] Run the migration test and confirm failure.
- [ ] Create `release_status` enum (`draft`, `published`, `withdrawn`) and `app_releases` with: UUID id, unique version, title, release_notes, installer_url, 64-character lowercase SHA-256, positive installer_size, status default draft, mandatory default false, nullable minimum_supported_version, creator/publisher/withdrawer IDs and timestamps, created_at, and updated_at.
- [ ] Add checks for trimmed nonempty text and checksum format. Keep URL-host and SemVer validation in the Edge Function because Postgres URL parsing is not the policy boundary.
- [ ] Enable RLS without direct client policies; revoke table mutations from `anon` and `authenticated`.
- [ ] Create service-role-only transactional RPCs `admin_save_release`, `admin_publish_release`, and `admin_withdraw_release`. Each locks its row and writes one `admin_audit_log` entry. Only draft releases can be edited/published; only published releases can be withdrawn; a withdrawn version cannot return to draft.
- [ ] When publishing, atomically withdraw any other published release with the same or lower precedence only if needed to maintain one active global release, set server timestamps/actor, and audit both affected records. Prefer a partial unique index `where status = 'published'` if the product guarantees exactly one current release.
- [ ] Run `supabase db reset` and migration tests.
- [ ] Commit: `git add supabase/migrations/20260911110000_app_releases.sql apps/engine/tests/test_migrations.py && git commit -m "feat: add audited app release state machine"`.

## Task 2: Centralize release validation and selection

**Files:**
- Create: `supabase/functions/_shared/releases.ts`
- Create: `supabase/functions/_shared/releases_test.ts`

- [ ] Write failing tests for strict `major.minor.patch` SemVer parsing/comparison, optional `v` normalization only at input, HTTPS enforcement, approved hosts (`github.com`, `objects.githubusercontent.com`, `github-releases.githubusercontent.com`), redirect-target validation, lowercase checksum normalization, positive byte size, and update selection.
- [ ] Cover selection cases: same version => no update; newer published => update; older client than `minimum_supported_version` => mandatory; explicit mandatory => mandatory; newer client than release => no downgrade; draft/withdrawn => never selected.
- [ ] Implement `parseReleaseInput`, `compareVersions`, `isApprovedInstallerUrl`, and `selectLatestRelease` as pure functions. Reject prerelease/build suffixes for the first version unless the spec is amended.
- [ ] Run Deno tests and format checks.
- [ ] Commit: `git add supabase/functions/_shared/releases* && git commit -m "feat: validate global desktop releases"`.

## Task 3: Add founder release APIs

**Files:**
- Create: `supabase/functions/admin-list-releases/index.ts`
- Create: `supabase/functions/admin-save-release/index.ts`
- Create: `supabase/functions/admin-publish-release/index.ts`
- Create: `supabase/functions/admin-withdraw-release/index.ts`
- Create: `supabase/functions/_shared/release_requests_test.ts`

- [ ] Write failing request-contract tests: list accepts only validated pagination; save accepts the complete draft fields and optional id; publish/withdraw accept only `release_id`; all reject extra keys and malformed UUIDs.
- [ ] Implement `admin-list-releases` newest-version/newest-created first with creator/publisher/withdrawer emails resolved for display.
- [ ] Implement save through `admin_save_release`, passing authenticated founder identity and fully validated metadata. Creation and edit both remain draft.
- [ ] Implement publish and withdraw through their RPCs. Re-fetch and revalidate the stored URL/checksum/size/version inside the publish request before changing state.
- [ ] Map transition conflicts to HTTP 409, validation to 400, missing releases to 404, and authorization to 403.
- [ ] Run all Deno tests and format checks.
- [ ] Commit: `git add supabase/functions/admin-*-release* supabase/functions/_shared/release_requests_test.ts && git commit -m "feat: add founder release controls"`.

## Task 4: Expose the signed-in user's latest applicable release

**Files:**
- Create: `supabase/functions/latest-release/index.ts`
- Create: `supabase/functions/_shared/latest_release_test.ts`

- [ ] Write failing tests for the exact request `{ current_version, platform: "windows", arch }`, unknown/extra fields, unauthenticated calls, no release, optional release, minimum-version mandatory override, and withdrawn release.
- [ ] Implement `latest-release`: require a normal user, validate platform/version, load only the current published release with the service client, call `selectLatestRelease`, and return `{ update_available: false }` or `{ update_available: true, release: { version, title, release_notes, installer_url, installer_sha256, installer_size, mandatory, published_at } }`.
- [ ] Do not return creator identities, drafts, internal IDs, audit data, or withdrawal history.
- [ ] Return no update for unsupported platforms in this phase.
- [ ] Run Deno tests and formatting.
- [ ] Commit: `git add supabase/functions/latest-release supabase/functions/_shared/latest_release_test.ts && git commit -m "feat: serve published desktop update metadata"`.

## Task 5: Build the founder Releases UI

**Files:**
- Modify: `apps/web/src/lib/admin.ts`
- Modify: `apps/web/src/lib/admin.test.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/AdminLayout.tsx`
- Create: `apps/web/src/pages/admin/Releases.tsx`
- Create: `apps/web/src/pages/admin/ReleaseEditor.tsx`
- Create: `apps/web/src/pages/admin/Releases.test.tsx`
- Modify: `apps/web/src/styles/global.css`

- [ ] Add failing API-client tests for list/save/publish/withdraw calls and typed 409 transition errors.
- [ ] Add `AppRelease` and `ReleaseDraft` types and `fetchReleases`, `saveReleaseDraft`, `publishRelease`, and `withdrawRelease` helpers.
- [ ] Add failing component tests for draft creation/edit, client-side validation, immutable published fields, publication confirmation, withdrawal confirmation, and visible actor/timestamp/status badges.
- [ ] Route `/admin/releases` and `/admin/releases/new`; optionally use `/admin/releases/:id` for edit. Add Releases navigation.
- [ ] Build a release table with version, status, mandatory flag, creator, publication time, checksum prefix, byte size, and actions allowed by state.
- [ ] Build the editor with version, title, notes, installer URL, SHA-256, bytes, mandatory, and minimum supported version. Show an exact preview of what users will see.
- [ ] Publication must use a second modal containing version, mandatory/optional status, host, checksum prefix, and “Publish to all users” wording. Enable the final button only after the founder checks an acknowledgement box. The backend remains authoritative if the page is stale.
- [ ] Withdrawal must require confirmation and explain that installed copies are unaffected but new checks stop receiving the release.
- [ ] Run web tests and build.
- [ ] Commit: `git add apps/web/src && git commit -m "feat: add founder release publishing dashboard"`.

## Task 6: Deploy and validate the control plane

**Files:** No source file required unless deployment configuration changes.

- [ ] Apply migrations to staging and deploy all four founder release functions plus `latest-release`, with JWT verification enabled.
- [ ] Create a draft pointing to a harmless staging GitHub Release asset with known size/checksum. Verify normal users receive no update.
- [ ] Publish after the second confirmation. Verify both founders can see the actor and timestamp, and a signed-in normal user on an older version receives the release.
- [ ] Verify a user on the same/newer version receives `update_available: false` and cannot query drafts.
- [ ] Withdraw the release and verify future user checks receive no update. Confirm audit entries for create, publish, and withdraw.
- [ ] Try invalid host, checksum, byte size, SemVer, double publish, editing after publish, and non-founder access; verify safe 4xx responses and no partial transitions.
- [ ] Commit tracked deployment configuration, if any, with `git commit -m "chore: deploy release control plane"`.

## Final Verification

- [ ] Confirm no API or UI action automatically publishes after draft save.
- [ ] Confirm there is at most one active published global release.
- [ ] Confirm `latest-release` exposes only published, safe metadata.
- [ ] Confirm every state change has the authenticated founder and server timestamp in the audit log.
- [ ] Confirm web tests/build, Deno tests, migration tests, and `git status --short` are clean apart from known unrelated user changes.
