# Desktop Self-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Show signed-in Windows users when a founder-published update is available and let them securely download, verify, install, restart, and retain their login and local work; mandatory releases block new processing until installed.

**Architecture:** The app checks Supabase after authenticated startup, when Profile opens, and every six hours. A Python update service owns manifest cache, download, redirect/host checks, exact-size and SHA-256 verification, and state reporting. Installation is delegated to a small separately built updater executable copied into the user's temporary update directory before launch, so Windows can replace the installed app and installed updater safely. The updater waits for the desktop PID to exit, runs Inno Setup silently, and restarts the installed app.

**Tech Stack:** Python 3.13, httpx, PyWebView, vanilla JavaScript/CSS, PyInstaller, Inno Setup 6, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-founder-admin-billing-desktop-updates-design.md`

**Prerequisite:** Complete and deploy `docs/superpowers/plans/2026-09-11-release-control-plane.md` through `latest-release`.

**Global Constraints:** Never delete or migrate `%LOCALAPPDATA%\CAUnpacker` during update. Never execute an unverified installer. HTTPS, approved redirect hosts, exact byte size, and SHA-256 are mandatory. Optional updates can be deferred. Mandatory updates block new ingest/reparse operations but leave Profile, update installation, logout, and access to existing local outputs available. Authenticode verification is added when a signing certificate exists; it is not a substitute for checksum validation.

## Task 1: Create one application version source

**Files:**
- Create: `apps/version.py`
- Modify: `apps/desktop/app.py`
- Modify: `CAUnpacker.spec`
- Modify: `installer/ca-unpacker.iss`
- Modify: `build_installer.bat`
- Create: `apps/engine/tests/test_version_contract.py`

- [ ] Add a failing test that imports `APP_VERSION`, verifies strict `major.minor.patch`, verifies the installer reads the version from a generated include/command-line define rather than a second hardcoded value, and verifies `DesktopApi.get_state()` reports the same version.
- [ ] Run `python -m pytest apps/engine/tests/test_version_contract.py -q` and confirm failure.
- [ ] Define `APP_VERSION = "0.11.0"` (or the next version chosen at execution time) in `apps/version.py`; import it in desktop code.
- [ ] Change `build_installer.bat` to query `apps.version.APP_VERSION` once and pass `/DAppVersion=<value>` to ISCC. Change `ca-unpacker.iss` to require that define and remove its hardcoded version.
- [ ] Ensure PyInstaller collects `apps.version`. Add `app_version` to `DesktopApi.get_state()` and heartbeat payloads.
- [ ] Run the new test plus `python -m pytest apps/desktop/tests/test_app_import.py -q`.
- [ ] Commit: `git add apps/version.py apps/desktop/app.py CAUnpacker.spec installer/ca-unpacker.iss build_installer.bat apps/engine/tests/test_version_contract.py && git commit -m "build: centralize desktop app version"`.

## Task 2: Implement manifest parsing, caching, and mandatory policy

**Files:**
- Create: `apps/engine/updates.py`
- Create: `apps/engine/tests/test_updates.py`
- Modify: `apps/engine/auth.py`

- [ ] Write failing tests for strict SemVer comparison, manifest schema validation, same/newer version suppression, explicit mandatory, `minimum_supported_version` mandatory override, withdrawn/no-update response, corrupted cache, and a six-hour cache TTL.
- [ ] Add failing tests that `check_for_update(force=False)` requires an authenticated session, calls `latest-release` with only current version/platform/architecture, persists no auth tokens in the update cache, and falls back to the last valid manifest on transient network failure without inventing an update.
- [ ] Run `python -m pytest apps/engine/tests/test_updates.py -q` and confirm failure.
- [ ] Add a narrow public `auth.call_authenticated_function(name, body)` that refreshes the session if possible and delegates to `_call_function`; preserve `_reject_document_keys`.
- [ ] Implement immutable `ReleaseManifest` and `UpdateState` data structures plus `compare_versions`, `parse_latest_release`, `load_update_cache`, `save_update_cache`, `check_for_update(force=False)`, and `mandatory_update_required()`.
- [ ] Store only release metadata and last-check time in existing local settings. A malformed response/cache must become a safe error/no-execution state.
- [ ] Run update/auth tests.
- [ ] Commit: `git add apps/engine/updates.py apps/engine/auth.py apps/engine/tests/test_updates.py && git commit -m "feat: check published desktop updates"`.

## Task 3: Download and cryptographically verify installers

**Files:**
- Modify: `apps/engine/updates.py`
- Modify: `apps/engine/tests/test_updates.py`

- [ ] Add failing tests using `httpx.MockTransport` for approved initial URL, approved redirect chain, unapproved initial/redirect host, non-HTTPS URL, missing/incorrect content length, stream larger/smaller than declared size, checksum mismatch, network interruption, cancellation, and successful atomic `.partial` to `.exe` rename.
- [ ] Use a dedicated directory such as `%LOCALAPPDATA%\CAUnpacker\updates\<version>` obtained through existing settings/library helpers. Resolve it to an absolute path and ensure it remains under that exact update root before cleanup or overwrite.
- [ ] Implement `download_update(manifest, progress_callback, cancel_event)` with streaming reads, a hard byte ceiling equal to `installer_size`, incremental SHA-256, redirect handling disabled by default and manually followed after validating every `Location`, and a bounded redirect count.
- [ ] Write to a newly created `.partial` file, flush/fsync, compare exact bytes and lowercase digest, then atomically rename to `CAUnpacker-Setup-<version>.exe`. On failure remove only that resolved partial file; never remove the update root recursively.
- [ ] Reuse an already verified final file only after recomputing its size and checksum.
- [ ] Run update tests.
- [ ] Commit: `git add apps/engine/updates.py apps/engine/tests/test_updates.py && git commit -m "feat: securely download desktop installers"`.

## Task 4: Build the external updater helper

**Files:**
- Create: `apps/desktop/updater.py`
- Create: `apps/desktop/updater_entry.py`
- Create: `CAUnpackerUpdater.spec`
- Create: `apps/desktop/tests/test_updater.py`
- Modify: `CAUnpacker.spec`
- Modify: `build_installer.bat`
- Modify: `installer/ca-unpacker.iss`

- [ ] Write failing unit tests for argument validation, waiting for the exact parent PID, installer command construction, successful restart, installer failure without restart, log redaction, and refusal to run an installer whose path is outside `%LOCALAPPDATA%\CAUnpacker\updates`.
- [ ] Implement a console-less helper CLI with required `--installer`, `--parent-pid`, `--app-exe`, `--expected-version`, `--expected-size`, and `--expected-sha256`. Reverify size/checksum immediately before execution.
- [ ] Wait for the parent process using a Windows process handle (with a bounded wait and a clear log error), then invoke the installer as an argument array: `/VERYSILENT`, `/SUPPRESSMSGBOXES`, `/NORESTART`, `/CLOSEAPPLICATIONS`, `/RESTARTAPPLICATIONS` omitted because the helper performs the controlled restart. Accept only Inno success exit codes documented for the chosen flags.
- [ ] On success launch the exact validated installed `CAUnpacker.exe` path with `subprocess.Popen([app_exe], cwd=app_exe.parent)` and exit. On failure preserve the verified installer for Retry and write a non-secret log below the update directory.
- [ ] Add `CAUnpackerUpdater.spec` as a one-file `CAUnpackerUpdater.exe`. Build it before the main COLLECT and place it in `dist\CAUnpacker` so Inno installs it.
- [ ] The desktop must copy the installed helper to the version-specific update directory before starting it; the running temporary copy prevents the installed helper from locking itself during replacement.
- [ ] Update Inno `[Files]` behavior without deleting user data and ensure silent upgrades use the existing stable `AppId` and install directory.
- [ ] Run updater tests and a local PyInstaller build of both executables.
- [ ] Commit: `git add apps/desktop/updater.py apps/desktop/updater_entry.py apps/desktop/tests/test_updater.py CAUnpackerUpdater.spec CAUnpacker.spec build_installer.bat installer/ca-unpacker.iss && git commit -m "feat: add safe desktop updater helper"`.

## Task 5: Add desktop update controller APIs

**Files:**
- Modify: `apps/engine/updates.py`
- Modify: `apps/desktop/app.py`
- Create: `apps/desktop/tests/test_update_api_contract.py`

- [ ] Write failing API tests for `get_update_state(force_check=False)`, background check deduplication, progress reporting, retry after failure, install refusal before verification, helper copy/launch arguments, and window close only after helper launch succeeds.
- [ ] Implement a thread-safe `UpdateController` with states `idle`, `checking`, `available`, `downloading`, `ready`, `installing`, and `error`; include version/title/notes/mandatory/progress/error but never tokens or filesystem paths in UI responses.
- [ ] Add Desktop API methods `get_update_state(force_check: bool = False)`, `download_update()`, `cancel_update_download()`, and `install_update()`. Long network work runs in one daemon worker with a lock; repeated calls return current state.
- [ ] At authenticated startup, schedule a nonblocking update check after the UI is created. Profile-triggered checks use `force_check=True`; periodic checks are initiated by the UI every six hours and use the cache-aware path.
- [ ] `install_update()` must reverify the installer, copy the helper to the validated version update directory, start it with the current PID and exact frozen executable path, then destroy `_WINDOW`. In source/dev mode return an explanatory error instead of simulating an install.
- [ ] Run desktop and update tests.
- [ ] Commit: `git add apps/engine/updates.py apps/desktop/app.py apps/desktop/tests/test_update_api_contract.py && git commit -m "feat: expose desktop self-update controls"`.

## Task 6: Enforce mandatory updates at processing boundaries

**Files:**
- Modify: `apps/engine/license.py`
- Modify: `apps/desktop/app.py`
- Modify: `apps/engine/tests/test_stage9_stage10_gate.py`
- Modify: `apps/desktop/tests/test_update_api_contract.py`

- [ ] Add failing tests that a cached mandatory update blocks `start_dump` before job creation and blocks `reparse_period`, while optional/no/offline-unknown update state does not. Confirm opening existing packs, profile, logout, and update APIs remain callable.
- [ ] Add `assert_update_allows_ingest()` in the update service with the user-facing message “A required CA Unpacker update must be installed before processing more files.”
- [ ] Call it at every processing entry point before mutating job state: `DesktopApi.start_dump` and `DesktopApi.reparse_period`. Keep quota enforcement in place after the update gate.
- [ ] Do not block application startup or access to existing local outputs; mandatory means “no new processing,” not “wipe or lock the app.”
- [ ] Run targeted gate/desktop tests.
- [ ] Commit: `git add apps/engine/license.py apps/desktop/app.py apps/engine/tests/test_stage9_stage10_gate.py apps/desktop/tests/test_update_api_contract.py && git commit -m "feat: enforce mandatory desktop updates"`.

## Task 7: Add the Profile update experience

**Files:**
- Modify: `apps/ui/index.html`
- Modify: `apps/ui/app.js`
- Modify: `apps/ui/styles.css` (or the actual stylesheet referenced by `index.html`)
- Create: `apps/ui/update-state.js`
- Create: `apps/ui/tests/update-state.test.js` if a JavaScript test harness exists; otherwise extend `apps/desktop/tests/test_update_api_contract.py` with static UI contract assertions.

- [ ] Add failing pure rendering tests/static contracts for hidden/no-update, checking, optional available, mandatory available, downloading percentage, ready/install, error/retry, and Later visibility.
- [ ] Add an update card inside the existing Profile panel with version, title, release notes, mandatory label, progress, error, and buttons: Check, Download update, Cancel, Install and restart, Retry, and Later where allowed.
- [ ] Implement a pure `viewModelForUpdateState(state)` in `update-state.js`; keep DOM wiring in `app.js`.
- [ ] On Profile open, force a check. Poll controller state only while checking/downloading/installing, and schedule a normal check every six hours while signed in. Stop timers on logout.
- [ ] Optional update: Later hides the card until the next scheduled check/profile force-check. Mandatory update: no Later button and show a persistent banner explaining that new processing is paused.
- [ ] Before install, show “CA Unpacker will close, install the verified update, and reopen automatically.” Disable double clicks while the helper starts.
- [ ] If startup is offline, show no false mandatory block; surface the last valid published mandatory cache only if already known.
- [ ] Run UI contracts, desktop API tests, and manually exercise keyboard/focus behavior.
- [ ] Commit: `git add apps/ui apps/desktop/tests/test_update_api_contract.py && git commit -m "feat: add profile update experience"`.

## Task 8: Produce and validate the first updatable installer

**Files:**
- Modify: `FIRST-RUN.txt` only if update behavior needs user-facing documentation.

- [ ] Run the targeted suites: `python -m pytest apps/engine/tests/test_updates.py apps/desktop/tests/test_updater.py apps/desktop/tests/test_update_api_contract.py apps/engine/tests/test_version_contract.py apps/engine/tests/test_stage9_stage10_gate.py -q`.
- [ ] Run the full Python test suite and record any pre-existing unrelated failures separately. Build with `build_installer.bat`; verify both executables are in the installed payload.
- [ ] Compute installer SHA-256 and exact byte size using PowerShell `Get-FileHash` and `Get-Item`; upload the immutable installer to a GitHub Release matching `APP_VERSION`.
- [ ] On a clean Windows VM install the previous authenticated build, sign in, create local sample work, and publish the new release as optional. Confirm Profile detects it, downloads with progress, closes, silently installs, restarts, remains signed in, and preserves local work.
- [ ] Test interrupted download/retry, wrong checksum, wrong size, redirect to an unapproved host, installer failure, no-network startup, and running from source mode.
- [ ] Publish a staging release as mandatory. Confirm new dump and reparse are blocked, existing outputs/profile/logout remain available, and successful update removes the block after restart.
- [ ] Verify Windows Event Viewer/app logs contain no access/refresh tokens. Verify the temp updater exits and the installed app is not left locked.
- [ ] Do not publish the first production mandatory release until both optional and mandatory VM matrices pass. A founder makes the final production publish decision in the dashboard.
- [ ] Commit documentation changes, if any, with `git commit -m "docs: document verified desktop update flow"`.

## Final Verification

- [ ] Confirm the downloaded installer is verified twice: after download and immediately before updater execution.
- [ ] Confirm every redirect host is validated and HTTP is rejected.
- [ ] Confirm the desktop window closes only after the temporary updater process starts successfully.
- [ ] Confirm login tokens and `%LOCALAPPDATA%\CAUnpacker` data survive upgrades.
- [ ] Confirm optional updates remain deferrable and mandatory updates block only new processing.
- [ ] Confirm version, installer metadata, and published dashboard record match exactly.
- [ ] Confirm `git status --short` includes only planned changes and known pre-existing unrelated user changes.
