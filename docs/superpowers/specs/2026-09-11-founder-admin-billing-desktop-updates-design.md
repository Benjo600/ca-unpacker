# CA Unpacker — Founder Admin, Billing Controls, and Desktop Updates

Date: 2026-09-11
Status: Approved design

## Goal

Extend the existing Supabase control plane so the two founders can independently sign in to a private admin dashboard, inspect firm/account usage, manage plans and manual payment state, and explicitly publish desktop application updates. Signed-in desktop users must see published updates in the profile/settings area and be able to install them with an automatic app restart.

The desktop application continues to process all accounting documents locally. The cloud receives account, firm, subscription, aggregate usage, device, application-version, and release metadata only.

## Scope

This design covers four connected capabilities:

1. Equal, separate founder accounts with server-enforced admin authorization.
2. Firm, user, device, usage, plan, and manual payment administration.
3. A draft/publish/withdraw lifecycle for application releases.
4. A secure Windows desktop update flow that downloads, verifies, installs, and restarts the application.

Automated payment-gateway integration, staged rollouts, per-user release targeting, delta patches, and automatic rollback are outside this version.

## Binding Privacy and Product Rules

- Client documents, extracted transactions, invoices, GST return contents, PAN/GSTIN values from documents, client names, and local filesystem paths never leave the user's PC.
- The cloud may store the firm's own display name because the user enters it during setup and explicitly uses it as account metadata.
- Each founder uses a separate Supabase Auth identity. Both founders have equal permissions.
- Knowing an admin URL is never sufficient for access; authorization is checked on every protected server request.
- Uploading or preparing release metadata never publishes an update automatically.
- An admin must explicitly release an update before desktop users can see it.
- Withdrawing a release stops new offers but does not undo completed installations.
- The application never executes an installer whose URL, size, or SHA-256 digest does not match the published release record.
- Existing application sessions, local databases, firm settings, and local documents survive an update.

## Existing Foundation

The repository already contains:

- Supabase Auth integration for desktop and web clients.
- `organizations`, `profiles`, `devices`, `usage_monthly`, `admin_users`, and `license_keys` tables.
- Edge Functions for quota checks, usage recording, heartbeats, organization listing, and plan changes.
- A React admin interface with overview, organization list, and organization detail routes.
- A desktop profile panel, encrypted refresh-token persistence, and local settings storage.
- A GitHub Release and Inno Setup distribution pipeline.

The implementation must evolve these components rather than create a second authentication, billing, or release system.

## Architecture

```text
Founder Supabase session
        |
        v
Private admin dashboard on Netlify
        |
        v
Admin Edge Functions --service role--> Supabase tables
        |                                  |
        |                                  +-- organizations / profiles
        |                                  +-- usage_monthly / devices
        |                                  +-- payment state / audit log
        |                                  +-- app_releases
        |
        +-- explicit release/withdraw actions

Signed-in desktop app --user JWT--> latest-release Edge Function
        |
        +-- profile/settings update badge
        +-- GitHub Release installer download
        +-- size + SHA-256 verification
        +-- updater process -> silent install -> app restart
```

GitHub continues to host Windows installer binaries. Supabase stores the release manifest and decides whether a release is visible. This avoids placing approximately 250 MB installers in Supabase Storage while keeping publication under founder control.

## Authorization Model

### Founder identities

The two founder accounts live in Supabase Auth and are allowlisted in `public.admin_users`. Admin email comparison is trimmed and case-normalized. The JWT email must be verified.

Both founders can:

- View all registered organizations and aggregate usage.
- Change a firm's plan and account status.
- Change manual payment state and paid-through date.
- Add internal administrative notes.
- Create, edit, publish, mark mandatory, and withdraw releases.
- View the audit log.

Founder accounts cannot impersonate customers or access customer document content because that content never reaches Supabase.

### Enforcement

- React route guards improve navigation but are not a security boundary.
- Every admin Edge Function calls one shared `requireAdmin` implementation.
- `requireAdmin` validates the bearer JWT and checks `admin_users` on each request.
- Service-role credentials are available only inside Edge Functions.
- Ordinary user JWTs may access only their own firm/quota endpoints and the currently published update manifest.
- Admin mutations use service-role access after authorization and write an audit record in the same logical operation.

The existing admin-session hydration fix from `cursor/ignore-netlify-cli-state` should be ported selectively. The old branch must not be merged wholesale because it diverges substantially from current `main`.

## Data Model

### `organizations` additions

| Column | Type | Default | Purpose |
|---|---|---|---|
| `payment_status` | enum | `trial` | Manual commercial state: `trial`, `paid`, `overdue`, `cancelled`, or `refunded` |
| `paid_through` | date nullable | null | Last covered subscription date |
| `admin_notes` | text | empty | Internal founder notes; never shown to the firm |
| `suspended_at` | timestamptz nullable | null | Records when processing access was suspended |
| `suspended_by` | uuid nullable | null | Founder Auth user responsible for suspension |

Plan and payment state remain separate. Changing `payment_status` does not silently change `plan`; founders explicitly make both decisions.

### `admin_users` hardening

Keep the existing email allowlist for compatibility. Add the resolved Supabase Auth user ID when available so audit records remain stable if an email changes. Each row has an active flag and created timestamp. There are exactly two active founder rows at launch, but the schema does not hard-code that number.

### `admin_audit_log`

| Column | Type | Purpose |
|---|---|---|
| `id` | uuid | Primary key |
| `admin_user_id` | uuid | Founder Auth identity |
| `admin_email` | text | Human-readable snapshot |
| `action` | text | Stable action name such as `organization.plan_changed` or `release.published` |
| `target_type` | text | `organization` or `release` |
| `target_id` | uuid | Changed record |
| `before_value` | jsonb nullable | Previous controlled values |
| `after_value` | jsonb nullable | New controlled values |
| `created_at` | timestamptz | Server timestamp |

The audit log is append-only. Browser clients receive read access through an admin Edge Function but no direct insert, update, or delete access.

### `app_releases`

| Column | Type | Purpose |
|---|---|---|
| `id` | uuid | Primary key |
| `version` | text unique | Semantic version such as `0.11.0` |
| `title` | text | Short user-facing release title |
| `release_notes` | text | User-facing update summary |
| `installer_url` | text | HTTPS GitHub Release asset URL |
| `installer_sha256` | text | Lowercase 64-character SHA-256 digest |
| `installer_size` | bigint | Expected byte length |
| `status` | enum | `draft`, `published`, or `withdrawn` |
| `mandatory` | boolean | Whether older versions may continue processing |
| `minimum_supported_version` | text nullable | Optional lower bound for mandatory enforcement |
| `created_by` | uuid | Founder who created the draft |
| `created_at` | timestamptz | Server timestamp |
| `published_by` | uuid nullable | Founder who explicitly released it |
| `published_at` | timestamptz nullable | Release time |
| `withdrawn_by` | uuid nullable | Founder who withdrew it |
| `withdrawn_at` | timestamptz nullable | Withdrawal time |

Only one published release is treated as the current update. Publishing a newer release supersedes the previous offer without deleting its history.

## Firm and Usage Synchronization

After a signed-in user completes local firm setup, the desktop app sends only the firm display name to a user-authorized Edge Function. That function updates only the caller's organization.

On startup and at the normal heartbeat interval, the desktop sends:

- Current application version.
- Hashed device fingerprint.
- User-visible device label.
- Activity timestamp generated by the server.

Successful local file ingestion continues to increment `usage_monthly.files_processed` through the existing server-side counter. The dashboard never derives billing usage from untrusted browser input.

## Admin Dashboard

### Login and routing

- `/admin/login` signs founders in with Supabase email/password.
- Auth hydration completes before route decisions, preventing valid sessions from being bounced to login.
- Ordinary users receive a clear “not authorized” state.
- API/network errors are shown separately from authorization denial.

### Overview

Display:

- Total registered firms.
- New firms in the selected period.
- Active firms in the last seven days.
- Files processed in the current month.
- Starter/Pro/suspended counts.
- Trial/paid/overdue/cancelled/refunded counts.
- Installed application-version distribution from active devices.

### Firms

The table includes email, firm name, signup date, last active time, current plan, payment status, current-month file usage, device count, and latest reported app version. It supports server-side search and pagination.

### Firm detail

Show:

- Organization and owner identity metadata.
- Monthly aggregate usage history.
- Registered devices and their application versions.
- Plan, payment status, paid-through date, and internal notes.
- Suspend and restore actions.
- Audit history for that firm.

### Releases

An admin can create a draft with version, title, notes, GitHub installer URL, expected size, checksum, and optional/mandatory mode. Draft creation has no customer-visible effect.

Explicit actions are:

- **Release update:** validates the manifest and publishes it to all signed-in desktop users.
- **Withdraw update:** removes it from the desktop manifest without deleting history.
- **Mark mandatory:** allowed before publication or as an audited change after publication.

The dashboard does not upload the installer binary in this version. The normal build/release pipeline uploads it to GitHub first; the dashboard controls when its verified manifest becomes visible.

### Audit log

Display founder, action, target, before/after summary, and timestamp. Both founders can view the same history.

## Admin Edge Functions

The implementation adds or extends these server boundaries:

| Function | Caller | Purpose |
|---|---|---|
| `admin-list-orgs` | Admin | Paginated firm, owner, usage, payment, device, and version summaries |
| `admin-get-org` | Admin | One firm's detail and history |
| `admin-update-org` | Admin | Plan, payment, paid-through, notes, suspension |
| `admin-list-audit` | Admin | Paginated immutable audit events |
| `admin-list-releases` | Admin | Draft, published, and withdrawn releases |
| `admin-save-release` | Admin | Create or edit a draft manifest |
| `admin-publish-release` | Admin | Explicitly publish a validated draft |
| `admin-withdraw-release` | Admin | Withdraw a published release |
| `sync-firm` | User | Update only the caller's organization display name |
| `latest-release` | User | Return only the current published manifest applicable to the caller's version |

All payloads are allowlisted field by field. Admin functions reject document-like keys using the existing privacy guard pattern.

## Desktop Update Experience

### Checking

The signed-in desktop app checks `latest-release`:

- After successful startup authentication.
- Whenever the user opens profile/settings.
- Every six hours while running.

The request contains the current app version and no document data. A cached result may be shown while offline, but a withdrawn release must not begin a new download after an online withdrawal check succeeds.

### Profile/settings UI

For a newer optional release, display an “Update available” badge, version, title, release notes, approximate download size, **Install update**, and **Later**.

For a mandatory release, keep profile, update, and logout controls available but block new ingestion until installation succeeds. Existing local data remains readable and unchanged.

### Download and verification

The desktop updater:

1. Creates a dedicated temporary update directory.
2. Downloads to a partial filename while reporting progress.
3. Enforces HTTPS and an approved GitHub release hostname.
4. Rejects redirects to unapproved hosts.
5. Verifies exact byte length and SHA-256.
6. Renames the verified partial file to its final installer filename atomically.
7. Never executes an incomplete or mismatched file.

Authenticode verification should be added when a Windows code-signing certificate is available. Until then, HTTPS, hostname allowlisting, and a server-published SHA-256 digest are mandatory controls.

### Install and restart

Because a running executable cannot safely replace itself, the desktop app starts a small updater process and then exits. The updater waits for the desktop process to terminate, runs the Inno Setup installer silently, records the installer exit code, and restarts CA Unpacker only after success.

The installer updates program files under the existing installation directory. It does not remove `%LOCALAPPDATA%\CAUnpacker`, so encrypted auth tokens, the database, firm configuration, and client documents remain intact.

If installation fails:

- Optional update: restart the current app and show a retryable error.
- Mandatory update: restart into the update-required screen with retry and logout available.
- Preserve a human-readable updater log that contains no tokens or document paths.

## Release Lifecycle

```text
draft --admin releases--> published --admin withdraws--> withdrawn
  |                              |
  +-- editable                   +-- visible to signed-in desktop apps
```

- Saving a draft never notifies users.
- Publishing requires a second explicit confirmation in the dashboard.
- The server sets publisher and publication timestamps; the browser cannot supply them.
- A withdrawn version cannot be republished by editing it. Create a new release record or an explicitly audited replacement.
- Desktop comparison follows semantic-version ordering, not string ordering.

## Error Handling

| Scenario | Required behavior |
|---|---|
| Admin session still hydrating | Show loading state; do not redirect |
| Ordinary user opens admin route | Show not-authorized state |
| Admin API unavailable | Show retryable service error, not “not authorized” |
| Invalid plan/payment transition | Reject without partial mutation or audit entry |
| Duplicate release version | Reject draft save |
| Invalid/non-GitHub installer URL | Reject publication |
| Missing or malformed checksum | Reject publication |
| Desktop offline | Keep app usable under existing offline-grace rules; do not download |
| Download interrupted | Retain no executable final file; allow retry |
| Size/checksum mismatch | Delete temporary file and show verification failure |
| Release withdrawn during download | Recheck before execution and refuse a withdrawn manifest |
| Installer failure | Preserve current data and restart into a clear retry state |

## Testing Strategy

### Database and Edge Functions

- Migration tests for existing organizations and default payment values.
- Both founder accounts are accepted independently.
- Ordinary and unverified accounts are rejected from every admin endpoint.
- Users cannot read drafts, audit logs, or other organizations.
- Plan/payment/suspension changes produce correct audit records.
- Firm sync can update only the caller's organization.
- Draft releases are invisible to desktop callers.
- Publish, mandatory change, supersession, and withdrawal follow the lifecycle.
- URL, size, checksum, and semantic-version validation reject malformed input.

### Web dashboard

- Auth hydration does not bounce a valid founder session.
- Authorization failure and API failure render different states.
- Organization metrics, pagination, and detail views map the API contracts correctly.
- Plan and payment controls require confirmation and display server results.
- Saving a draft does not release it.
- Release and withdrawal require explicit confirmation and refresh audit history.

### Desktop

- Newer semantic versions show the update badge; equal/older versions do not.
- Optional updates allow Later; mandatory updates block new ingestion.
- Profile opening and six-hour polling refresh the manifest.
- Interrupted, wrong-size, wrong-checksum, and unapproved-host downloads never execute.
- Successful updater handoff closes, installs, and restarts the app.
- Auth session, database, firm settings, and local documents survive installation.
- Withdrawn releases are rejected before execution.

### Manual release gate

Before enabling mandatory updates in production, validate on a clean Windows VM:

1. Install the current public version and sign in.
2. Create a draft release and confirm the desktop sees nothing.
3. Publish it as optional and confirm profile discovery.
4. Install it and confirm automatic restart and retained session/data.
5. Publish a test mandatory release and confirm ingest blocking.
6. Withdraw it and confirm it is no longer offered.

## Delivery Phases

### Phase 1 — Founder access and firm administration

- Port the admin-session hydration fix selectively.
- Harden shared admin authorization.
- Add payment fields and immutable audit logging.
- Sync firm names and expose firm/usage/device detail APIs.
- Complete overview, firm list, and firm detail screens.

### Phase 2 — Release control plane

- Add `app_releases` and release lifecycle functions.
- Add release dashboard and audit events.
- Validate GitHub URL, size, checksum, and semantic versions.

### Phase 3 — Desktop updater

- Add version reporting and release polling.
- Add profile/settings update UI.
- Implement secure download, verification, updater handoff, silent install, and restart.
- Validate optional and mandatory flows on Windows.

### Phase 4 — Production rollout

- Deploy migrations and Edge Functions.
- Deploy the admin dashboard.
- Ship the first updater-capable desktop version through the existing release process.
- Keep the first production update optional until installation telemetry and support checks pass.

## Success Criteria

The feature is complete when:

1. Each founder can sign in separately and access the same admin capabilities.
2. Ordinary users cannot access admin pages or admin APIs.
3. The dashboard accurately shows registered user email, firm name, aggregate usage, devices, app versions, plan, and payment state.
4. Either founder can change plan/payment/suspension state and every change is auditable.
5. A saved draft update is invisible until a founder explicitly releases it.
6. Every signed-in desktop app discovers a published applicable update through profile/settings.
7. A user can install a verified update and the app restarts without losing session or local data.
8. Mandatory releases block new processing while retaining update and logout access.
9. Withdrawing a release stops new offers and prevents execution after the final pre-install check.
10. Network inspection confirms no client document content or extracted financial data is transmitted.
