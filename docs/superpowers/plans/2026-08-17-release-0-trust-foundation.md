# CA Unpacker Release 0 Trust Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Stage 1–7 app reproducibly testable, impossible to report silent parser success, and deterministic to package for a Windows 11 pilot.

**Architecture:** Preserve current parsers while adding explicit intake and per-file outcome contracts. Apply numbered, backed-up SQLite migrations before opening the database; derive job completion from persisted file outcomes; expose the same truth through the desktop API and UI.

**Tech Stack:** Python 3.13, SQLAlchemy, SQLite, pytest, pywebview/WebView2, PyInstaller, Inno Setup, Tesseract, openpyxl, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-17-ca-unpacker-full-product-design.md`

## Global Constraints

- File terminal statuses are exactly `processed`, `needs_review`, `failed`, and `unclassified`.
- Job terminal statuses are exactly `done`, `done_with_warnings`, and `failed`.
- Recognized parser failures never produce `done`.
- Folder import never silently truncates at 400; 401 or more supported files are rejected before copying.
- `.xlsx` and `.csv` remain supported; `.xls` is rejected with re-export guidance.
- Original copied files are never mutated.
- Release OCR remains local and Tesseract assets are mandatory.
- Existing user databases and output packs survive migrations.

---

### Task 1: Reproducible Baseline and Launch Fix

**Files:** `.gitignore`, `apps/engine/tests/**`, test-data generators, `apps/desktop/app.py`, `requirements-dev.txt`

- [ ] Restore the existing ignored tests and synthetic generators to tracked source, while continuing to ignore generated `test-dump/` data.
- [ ] Add a regression test that imports `apps.desktop.app` so the current invalid callback body fails before production code changes.
- [ ] Run the focused test and confirm the expected import/indentation failure.
- [ ] Give `on_zone_drop` an executable no-op body without changing drag/drop ownership.
- [ ] Add a pinned developer test dependency file and run the restored suite.
- [ ] Commit the independently testable baseline repair.

### Task 2: Intake Preflight and Spreadsheet Policy

**Files:** `apps/engine/dump.py`, `apps/engine/kinds.py`, `apps/desktop/app.py`, `apps/ui/index.html`, intake tests

- [ ] Add failing tests for a 401-file folder rejection, duplicate paths, missing paths, and `.xls` rejection with `.xlsx`/`.csv` acceptance.
- [ ] Replace truncating path collection with an intake preflight result that reports discovered and accepted counts and raises a user-facing error before copying when the limit is exceeded.
- [ ] Remove `.xls` from supported suffixes and file pickers and return re-export guidance when explicitly selected.
- [ ] Run focused intake tests and the full suite.
- [ ] Commit intake preflight and spreadsheet-policy changes.

### Task 3: Backed-Up Numbered Database Migrations

**Files:** `apps/engine/db.py`, `apps/engine/migrations.py`, migration tests

- [ ] Add failing tests for fresh schema creation, upgrade from the current schema, automatic pre-upgrade backup, idempotent reopen, and rollback/no version advance on migration failure.
- [ ] Add `schema_version` tracking and sequential transactional migrations.
- [ ] Extend stored files with parse outcome, reason code/message, row count, warnings JSON, parser identity/version, and processed timestamp; extend jobs with intake totals.
- [ ] Run migrations before ORM use while preserving current databases and packs.
- [ ] Run focused migration tests and the full suite.
- [ ] Commit the migration foundation.

### Task 4: Per-File Outcomes and Derived Job Completion

**Files:** `apps/engine/outcomes.py`, `apps/engine/pipeline.py`, `apps/engine/dump.py`, `apps/engine/db.py`, outcome tests

- [ ] Add failing tests for processed-with-rows, valid-empty, password-required, unknown, missing-copy, parser failure, mixed warning jobs, and all-failed jobs.
- [ ] Persist one terminal outcome for every accepted file, including files without storage keys and recognized parsers that return no rows.
- [ ] Derive job status from file outcomes: clean processed files produce `done`; any review/unclassified/partial failure produces `done_with_warnings`; infrastructure failure or no usable result with failures produces `failed`.
- [ ] Preserve redacted parser error details and prevent reparsing from erasing unresolved file truth.
- [ ] Run focused outcome tests and the full suite.
- [ ] Commit the outcome engine.

### Task 5: Desktop API and Visible Warning States

**Files:** `apps/engine/dump.py`, `apps/desktop/app.py`, `apps/ui/app.js`, `apps/ui/index.html`, `apps/ui/styles.css`, API/UI contract tests

- [ ] Add failing contract tests for file outcome fields, job outcome counts, and `done_with_warnings` polling behavior.
- [ ] Return versioned file outcome and job summary data through existing desktop API calls.
- [ ] Render warning completion distinctly from success and failure; list skipped/review/failed files with their reason without hiding generated outputs.
- [ ] Keep password retry and manual classification flows working.
- [ ] Run focused contract tests and the full suite.
- [ ] Commit API and UI warning-state changes.

### Task 6: Deterministic Release Inputs, OCR, and License Inventory

**Files:** `requirements.in`, `requirements.lock.txt`, `build_installer.bat`, `installer/bundle_tesseract.py`, `scripts/generate_third_party_licenses.py`, `THIRD_PARTY_LICENSES.md`, packaging tests

- [ ] Add behavior tests for release-mode Tesseract failure and successful verification of executable, DLL, and `eng.traineddata` assets.
- [ ] Separate human-maintained dependency inputs from exact release pins and make release builds install from the lock file.
- [ ] Make missing OCR assets fatal in release mode while retaining an explicit development warning mode.
- [ ] Generate an exact third-party inventory with versions, source URLs, license identifiers, required notices, and separate asset/model-license fields.
- [ ] Run packaging checks without publishing an installer.
- [ ] Commit deterministic release and compliance tooling.

### Task 7: Continuous Integration and Release Gate

**Files:** `.github/workflows/ci.yml`, `scripts/release_gate.py`, `README.md`, `STAGES.md`

- [ ] Add executable release-gate checks for Python compilation, unit/integration tests, migrations, locked dependencies, license inventory freshness, PyInstaller build, Tesseract assets, and desktop import smoke.
- [ ] Configure GitHub Actions to run portable checks on pushes/PRs and a Windows build job for packaging-specific checks.
- [ ] Document the clean Windows 11 installed-app checklist and clearly leave that external gate pending until run on a clean VM.
- [ ] Run every locally available gate and the full test suite.
- [ ] Commit CI and release-gate documentation.

