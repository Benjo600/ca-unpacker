# CA Unpacker v0.7.0 — Install & Runtime Audit Findings

Date: 2026-08-16

This note records issues found during a code-level audit of the current `v0.7.0` release/tag. The goal is to make the next debugging session straightforward: fix the confirmed blockers first, then validate on a genuinely clean Windows machine.

## Current verdict

Do **not** assume the current `CAUnpacker-Windows.zip` is safe to hand to a real CA yet.

The overall architecture is promising and Stages 1–7 are substantially implemented, but there are several release/runtime risks that can cause launch failure, missing features, or worse: a job appearing successful while some input was not actually parsed.

Recommended order:

1. Fix the launch-blocking syntax problem.
2. Fix false-success / silent parser failure behavior.
3. Fix or remove unsupported `.xls` handling.
4. Make Tesseract bundling deterministic.
5. Add an explicit warning when folder imports exceed 400 files.
6. Add reproducible tests + CI build/smoke checks.
7. Test the actual installer on a clean Windows 11 machine before continuing Stage 8.

---

## P0 — Release blocker: invalid Python function body in desktop app

**File:** `apps/desktop/app.py`

Inside `_bind_explorer_drop`, the nested function currently looks like this conceptually:

    def on_zone_drop(_event) -> None:
        # comments only

A Python function cannot have only comments as its body. It needs at least `pass` or executable code.

### Why this matters

`apps/desktop/__main__.py` imports `main` from `apps.desktop.app`, so a syntax/indentation error here can prevent the application from importing and launching at all.

The `v0.7.0` tag points at the same commit containing this source.

### Fix

Add an executable body, for example:

    def on_zone_drop(_event) -> None:
        pass

Or implement the intended drop callback properly.

### Verification

- Run `python -m py_compile apps/desktop/app.py`.
- Run `python -m apps.desktop` from source.
- Rebuild PyInstaller package.
- Install the rebuilt Setup EXE on a clean machine and verify the window opens.

---

## P0 — False success: non-bank parsers can fail while the job becomes `done`

**Files:**
- `apps/engine/pipeline.py`
- `apps/engine/dump.py`

`parse_period()` catches per-file exceptions, records a `could not parse: ...` reason, and continues.

After parsing, `ingest_paths()` contains an explicit validation that a detected **bank** file produced a bank Excel. Equivalent postconditions do not currently exist for invoice, GSTR, Tally, or Zoho inputs.

The job can therefore reach status `done` even though one or more recognised files produced no usable output.

### Why this matters

For accounting software, silent omission is a severe correctness problem. A visible crash is preferable to telling a CA processing is finished when data was skipped.

### Fix direction

Track parse outcome per recognised file.

At minimum distinguish:

- parsed successfully with rows
- recognised but validly empty
- needs review
- password required
- parser failed

Then make the overall job status reflect failures/partial failures.

Possible statuses:

- `done`
- `done_with_warnings`
- `failed`

The UI should show exactly which files were skipped and why.

### Verification

Create one deliberately malformed file for each recognised type:

- invoice
- GSTR-1
- GSTR-2B
- GSTR-3B
- Tally
- Zoho

Confirm the UI never reports a clean success without surfacing the failed file.

---

## P1 — `.xls` Zoho support is not reliable on a clean install

**Files:**
- `requirements.txt`
- `apps/engine/classifier.py`
- `apps/engine/parsers/zoho.py`

The app advertises/accepts `.xls` files.

The Zoho parser attempts to use `xlrd` for legacy `.xls`, but `xlrd` is not listed in `requirements.txt`.

The classifier also sends `.xls` through `_xlsx_header_cells`, which uses `openpyxl`; `openpyxl` does not provide legacy binary `.xls` support.

### Result

On a clean machine, `.xls` can classify poorly and/or parse into zero rows.

The parser catches exceptions and returns empty output, which makes this harder for the user to diagnose.

### Choose one fix

**Option A — actually support `.xls`:**

- add and pin `xlrd`
- make classifier use the same `.xls` reader
- add `.xls` fixture tests

**Option B — remove `.xls` for now:**

- remove `.xls` from the file picker
- remove `.xls` from supported suffixes
- show a message asking the user to export as `.xlsx` or `.csv`

Option B is safer until real `.xls` samples are tested.

---

## P1 — Tesseract bundling is optional even though OCR is presented as a product capability

**Files:**
- `installer/bundle_tesseract.py`
- `build_installer.bat`
- `apps/engine/ocr.py`

The build script runs the Tesseract bundler, but if no Tesseract installation is found on the build machine, `bundle_tesseract.py` prints a warning and exits successfully.

That means a release can be built and published without bundled OCR.

### Why this matters

A user's clean Windows machine may not have Tesseract installed. Scanned statements/images will then behave differently from the development machine.

OCR functions also tend to return empty results on failures instead of raising a strong user-visible error.

### Fix direction

For release builds, treat missing Tesseract as a **build failure**.

Example policy:

- development build: missing Tesseract may warn
- release build: missing `tesseract.exe` or required `tessdata` must fail

Also verify `eng.traineddata` exists in the installer output.

### Verification

After build, automatically assert that the distribution contains:

- `tesseract/tesseract.exe`
- required Tesseract DLLs
- `tesseract/tessdata/eng.traineddata`

Then test a scanned PDF on a machine with no separate Tesseract installation.

---

## P1 — Folder import silently stops at 400 files

**File:** `apps/engine/dump.py`

`MAX_FOLDER_FILES = 400`.

`collect_paths()` returns as soon as 400 files are collected.

There is no clear indication to the user that additional files were ignored.

### Why this matters

Silent input omission is unacceptable in accounting workflows.

### Fix

Either:

- reject the folder before processing and say it contains more than 400 supported files, or
- process only 400 but return a prominent warning containing total discovered vs imported counts.

Do not silently truncate.

### Verification

Create a folder containing 401 small files and verify the UI explicitly tells the user what happened.

---

## P1 — Tests are not reproducible from the repository

**File:** `.gitignore`

The repository ignores:

- `apps/engine/tests/`
- `test-dump/`
- test data generator scripts

`STAGES.md` records up to 110 passing tests, but a fresh clone cannot run those same tests because they are not committed.

There are also no GitHub Actions checks attached to the v0.7.0 release commit.

### Why this matters

A release can regress without GitHub detecting it. It also makes the recorded test count impossible to reproduce independently.

### Fix

Commit the test suite.

If real CA/customer documents cannot be committed, keep them private but create synthetic fixtures that exercise the same shapes and edge cases.

Add CI that at least performs:

1. dependency install
2. Python compile check
3. unit tests
4. PyInstaller build
5. simple launch/import smoke check where feasible

The compile check alone would have caught the current `app.py` issue.

---

## P1 — Dependencies are not locked for reproducible releases

**File:** `requirements.txt`

Dependencies currently use minimum versions such as `>=`.

### Risk

A build next month may resolve newer dependency versions than v0.7.0 did and behave differently even if the repository commit did not change.

This is particularly important for:

- pywebview
- pypdf / pypdfium2
- pdf-inspector
- openpyxl
- SQLAlchemy

### Fix direction

Keep a developer requirements file if desired, but create a locked release dependency set.

For example:

- `requirements.in`
- `requirements.lock.txt`

Build releases from the lock file.

---

## P1/P2 — WebView2 should be explicitly verified on clean Windows

**Files:**
- `installer/ca-unpacker.iss`
- desktop packaging setup

The installer copies the PyInstaller application but does not explicitly install or verify Microsoft's WebView2 Runtime.

Modern Windows 11 systems normally have WebView2, but the release process should not simply assume every target machine has a compatible runtime.

### Fix direction

Before adding another dependency, first clean-machine test what pywebview does on your supported Windows versions.

If needed:

- detect WebView2
- document the prerequisite
- or bundle/install the evergreen runtime according to Microsoft's supported distribution method

### Verification

Test on:

- current Windows 11
- Windows 10 if you intend to support it
- a fresh VM/user profile without development tooling

Test all JS-heavy interactions, not only window launch.

---

## P2 — Invoice extraction heuristics will need real-world hardening

**File:** `apps/engine/parsers/invoice.py`

Current heuristics include behavior such as:

- selecting the first detected GSTIN unless a `supplier GSTIN` label is found
- selecting a matching date using a broad date regex
- falling back to the last detected amount when a labelled total is not found

These are reasonable prototype heuristics but can fail on invoices containing:

- supplier GSTIN + buyer GSTIN
- invoice date + due date + supply date
- subtotal, round-off, previous balance and grand total
- multiple tax tables
- OCR noise

### Fix direction

Do not try to solve every invoice format immediately.

Instead:

- strengthen confidence/flagging
- prefer explicit labels
- flag ambiguity rather than guessing
- test against diverse real invoices
- preserve clickable source evidence for every extracted field

A CA being asked to review an ambiguous field is better than a confidently wrong value.

---

## P2 — Tally parsing is intentionally simplistic and should be treated as partial support

**File:** `apps/engine/parsers/tally.py`

The current parser reduces vouchers into a relatively small canonical representation and uses generic searches such as the first/deep `AMOUNT` field, converting the result with `abs()`.

Real Tally XML can contain multiple ledger allocations, taxes, inventory allocations, debit/credit semantics, notes, and voucher structures.

### Risk

A fixture can parse correctly while a real firm's export maps the wrong amount or tax fields.

### Fix direction

Keep the current Stage 7 implementation but mark unsupported/ambiguous structures for review instead of pretending every Tally export is fully understood.

Build a real Tally sample corpus before marketing broad Tally compatibility.

---

## P2 — GSTR parser covers selected schemas/sections, not every GST portal shape

**File:** `apps/engine/parsers/gstr.py`

Current support is useful but section-specific.

Do not interpret successful fixture parsing as universal support for every historical/current GST JSON structure.

### Fix direction

Maintain schema fixtures by form/version and fail visibly when an unknown structure is encountered.

Never silently generate a partial Excel when a recognised GST file contains unsupported important sections.

---

# Recommended repair session order

## Step 1 — Make the source provably launchable

- [ ] Add executable body to `on_zone_drop`
- [ ] Run compile check across all Python files
- [ ] Run app from source

## Step 2 — Make failures impossible to hide

- [ ] Track parser result per input file
- [ ] Add partial-success state
- [ ] Show failed/skipped recognised files in UI
- [ ] Add 401-file truncation test/warning

## Step 3 — Make installer deterministic

- [ ] Decide `.xls` support policy
- [ ] Lock dependencies
- [ ] Make release build fail if Tesseract is missing
- [ ] Verify bundled OCR assets
- [ ] Verify WebView2 behavior

## Step 4 — Restore reproducible tests

- [ ] Commit test suite
- [ ] Commit synthetic fixtures/generators
- [ ] Add compile + tests CI
- [ ] Add PyInstaller build check

## Step 5 — Clean-machine smoke test

Use a fresh Windows VM or laptop with no Python/Tesseract/dev tools.

Test this exact sequence:

- [ ] Download release ZIP
- [ ] Extract Setup EXE
- [ ] Install as normal user
- [ ] Launch from Start menu
- [ ] Complete first-run firm/output setup
- [ ] Create client
- [ ] Create period
- [ ] Add files through file picker
- [ ] Add folder
- [ ] Drag/drop from Explorer
- [ ] Digital HDFC statement -> Excel
- [ ] Digital ICICI statement -> Excel
- [ ] Digital SBI statement -> Excel
- [ ] Password-protected PDF
- [ ] Scanned bank PDF -> local OCR
- [ ] PDF invoice
- [ ] Image invoice
- [ ] GSTR-1 JSON
- [ ] GSTR-2B JSON
- [ ] GSTR-3B JSON
- [ ] Tally export
- [ ] Zoho CSV/XLSX
- [ ] Intentionally corrupted recognised file
- [ ] Open generated Excels
- [ ] Source crop interaction
- [ ] Restart app and confirm data persists
- [ ] Delete/wipe and restart
- [ ] Verify no silent failures appeared during the run

# Gate before Stage 8

Stage 8 should ideally wait until this condition is true:

> The exact release installer can be installed on a clean Windows machine and complete Stages 1–7 with real/synthetic representative files while every parser failure is surfaced to the user and no input is silently omitted.

Once that passes, Stage 8 reconciliation can be built on a much more trustworthy foundation.
