# CA Unpacker Prototype Build Log

**Work period:** 17–18 August 2026

**Branch:** `codex/full-product-integration`

**Starting commit:** `b4dd8cc`

**Prototype completion commit:** `3c3412f`

## Executive summary

This work session converted the existing Stage 1–7 CA Unpacker code into a safer local prototype that can be tested without pretending every document was processed successfully.

The central product rule implemented during the session is:

> Every accepted file must have a visible, persisted result. The app must not report clean success when a file failed, needs review, or is unclassified.

The work deliberately stopped at a **lean local prototype**. Release-grade packaging, automated licence inventory, CI, installer certification, and broader product features remain future work.

## What changed for a non-technical user

The desktop app now:

- opens successfully from source;
- accepts mixed folders without silently stopping after 400 files;
- rejects legacy `.xls` files with guidance to export them as `.xlsx` or `.csv`;
- records whether every accepted file was processed, needs review, failed, or is unclassified;
- distinguishes **Completed**, **Completed with warnings**, and **Processing failed**;
- shows the reason a file needs attention;
- keeps successful Excel outputs visible even when other files need review;
- preserves password-unlock and manual document-type controls;
- protects existing local databases with a backup before schema upgrades.

## Scope decision made during the session

The original roadmap described a production-ready foundation followed by reconciliation, completeness detection, capital gains, firm-scale processing, billing foundations, and optional OCR improvements.

During implementation, the scope was intentionally reduced to get a working prototype in front of the founders sooner:

1. Keep the reliability work needed to avoid misleading results.
2. Add the minimum UI needed to see those results.
3. Defer production packaging and infrastructure work.
4. Use the prototype to decide which product feature should be built next.

## Detailed implementation

### 1. Isolated development branch

- Created `codex/full-product-integration` in a separate Git worktree.
- Kept the existing `main` checkout untouched.
- Added `.worktrees/` to `.gitignore` so the isolated checkout cannot be accidentally committed inside the repository.

### 2. Restored a reproducible test baseline

- Restored and tracked the existing Stage 1–7 engine tests.
- Restored the synthetic data generators used by those tests.
- Kept generated `test-dump/` files ignored.
- Added `requirements-dev.txt` with pinned testing dependencies.
- Added a desktop import regression test.

The restored baseline initially exposed the audited launch blocker: `apps/desktop/app.py` contained a Python function whose body had only comments. The function now has an executable no-op body, allowing the desktop module to import and launch.

### 3. Safe intake preflight

Added an intake preflight step before any file is copied or entered into the database.

The preflight now:

- resolves and de-duplicates selected paths;
- reports discovered and accepted counts separately;
- fails visibly when a selected path no longer exists;
- counts unknown files because they must still be accounted for;
- rejects an intake containing more than 400 files instead of silently truncating it;
- rejects directly selected `.xls` files, including hidden `.xls` filenames;
- continues accepting `.xlsx` and `.csv` files.

### 4. Backed-up SQLite migrations

Added a numbered migration system for local SQLite databases.

- Existing unversioned app databases are treated as schema version 1.
- The new outcome fields are schema version 2.
- Existing databases receive a collision-safe backup before upgrading.
- Fresh databases are created directly at the latest schema.
- Migrations and version updates are transactional.
- Failed migrations roll back without advancing the schema version.
- Concurrent app initialisation is serialised through SQLite before schema inspection.
- Fresh and upgraded databases use matching SQL defaults.
- Existing database records and physical Excel pack files are preserved.

### 5. Per-file outcome engine

Added `apps/engine/outcomes.py` as the single source of truth for file results.

The exact terminal file outcomes are:

| Outcome | Meaning |
|---|---|
| `processed` | The recognised parser completed with usable rows, or positively identified a valid empty file. |
| `needs_review` | The file is recognised but ambiguous, password-protected, or produced no rows without proof that it was validly empty. |
| `failed` | Copying, storage, parsing, or infrastructure failed. |
| `unclassified` | No supported parser confidently understands the file. |

The exact terminal job states are:

| Job state | Meaning |
|---|---|
| `done` | Every file in the period was processed cleanly. |
| `done_with_warnings` | At least one file needs review, failed alongside usable files, or remains unclassified. |
| `failed` | Failures occurred and no usable processed result exists, or the job infrastructure failed. |

Every stored file can now retain:

- outcome;
- stable reason code;
- safe user-facing reason;
- extracted row count;
- warnings;
- parser identity and version;
- processing timestamp.

### 6. Durable intake manifest

The app now writes one database manifest row for every accepted file before creating destination folders, copying, or classifying.

This prevents cases where:

- an accepted file disappears from the audit trail after an early error;
- copied bytes exist without a corresponding database row;
- accepted counts disagree with the number of persisted file outcomes.

Infrastructure cleanup is restricted to files owned by the failing job, so a new failed intake cannot overwrite earlier or migrated file history.

### 7. Parser failure handling

- Python parser exceptions are captured per file rather than silently swallowed.
- Known passwords and traceback-shaped messages are redacted before persistence.
- Structured parser errors returned by GST, Tally, or other parsers become `failed/parser_error` instead of `needs_review/no_rows`.
- Password evidence takes priority and remains a review/unlock flow.
- Parser failures cannot produce clean `done`.

### 8. Consistent period summaries

Because CA Unpacker reparses and regenerates outputs for the complete period, job API summaries now explicitly declare:

```text
summary_scope: period
```

The job status, returned files, and outcome counts are therefore calculated from the same period rows. Job-specific discovered and accepted intake totals remain tied to the individual job.

This fixes two inconsistencies:

- a second intake could previously show counts that did not explain its warning status;
- a reparse job could show “no files” even though it processed the period’s existing files.

### 9. Visible warning states in the existing UI

The existing period screen was retained to keep the prototype lightweight.

It now shows:

- an accessible outcome badge on every file row;
- extracted row counts for processed files;
- persisted reasons for review or failure;
- processed files in the normal file list;
- review, failed, and unclassified files in the review section;
- separate summaries for clean completion, warnings, and failure;
- successful Excel outputs even when other files need attention.

A small `status-summary.js` module contains the pure display logic. It works in the browser and can be tested directly with Node without adding a frontend build system.

## API additions

The existing job response now includes:

```json
{
  "api_version": 1,
  "summary_scope": "period",
  "outcome_counts": {
    "processed": 0,
    "needs_review": 0,
    "failed": 0,
    "unclassified": 0
  }
}
```

Existing file dictionaries now include the persisted outcome, reason, row count, warnings, parser provenance, and processing time.

## Verification performed

Development followed a test-first and independent-review workflow.

Final verification on commit `3c3412f`:

- Python compilation: passed;
- Node UI behaviour tests: passed;
- Node JavaScript syntax checks: passed;
- Python tests: **145 passed**;
- optional test skipped: **1**;
- additional unittest subtests: **8 passed**;
- final independent code review: approved;
- tracked working tree: clean before this build-log document was added.

The skipped test is an optional local OCR/fixture scenario, not a newly introduced failure.

## How to test the prototype locally

On the development computer:

1. Open:

   ```text
   C:\Users\Admin\OneDrive\Desktop\CA idea\.worktrees\full-product-integration
   ```

2. Double-click `start.bat`.
3. Keep the command window open while testing.
4. Create a test firm, client, and period.
5. Select **Add folder** and choose the local `test-dump` folder.
6. Confirm each file displays an outcome and reason.
7. Confirm warnings are not presented as clean success.
8. Confirm generated Excel outputs can still be opened.

The local `test-dump` contains synthetic bank, invoice, GST, Tally, Zoho, image, and unknown examples. It is intentionally not committed to GitHub; the tracked generator scripts can recreate synthetic fixtures.

## Intentionally deferred work

The following items are not part of this lean prototype:

- release dependency locking;
- release-mode Tesseract asset enforcement;
- automated SBOM and third-party licence inventory;
- GitHub Actions CI;
- signed or certified Windows installer;
- clean Windows 11 installation test;
- PaddleOCR;
- reconciliation, gap detection, capital gains, bulk queue, or billing features from later releases.

## Known non-blocking edge cases

Independent review recorded these for later hardening:

- a narrow source-disappearance race can display `copy_failed` instead of `source_missing`;
- nested bank password metadata can occasionally omit the Unlock action, though it still avoids clean success;
- parser warnings are persisted but not all are displayed in the file row or reflected in the completion tone;
- concurrent first access to the global engine/session factory has a small publication race outside the current sequential desktop startup;
- files larger than 100 MB display a generic copy failure instead of a specific size-limit message;
- a migrated historical job can retain `done` while its migrated file starts as `unclassified` until reprocessed.

None of these was judged a blocker for testing the local prototype.

## Commit timeline

```text
b9cf3c8 chore: ignore local worktrees
45e403e docs: define release 0 trust foundation
49b533d test: restore reproducible baseline
5cca8c1 feat: add intake preflight validation
26c7ea1 fix: report intake preflight candidates
e1ea1ab feat: add backed-up database migrations
f2bd97c fix: serialize database initialization
d14d16e feat: derive jobs from per-file outcomes
f927e98 fix: persist intake manifest before processing
fdc9808 feat: surface job outcome warnings
3c3412f fix: align period summaries and job cleanup
```

## Suggested next product step

Test this prototype with the synthetic dump and a small set of non-sensitive sample documents. Record:

- which files were processed correctly;
- which files were sent to review;
- whether generated Excel files are useful;
- confusing messages or interactions;
- the single workflow that would save the most manual time next.

Use that evidence to choose the next prototype feature rather than automatically continuing the full production roadmap.
