# Backend Document Processing Fix Plan

> **For agentic workers:** Implement this plan task-by-task. Every task starts with a failing
> regression test, then the fix. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every backend parser produce correct rows or an honest, visible failure on
realistic documents. Route all uncertainty through the existing outcome contract so the app
never reports a silently wrong result.

**Architecture:** Preserve parser interfaces. Fix extraction and normalization at the source
(bank money/date handling and row assembly, invoice field selection, GSTR/Tally/Zoho
faithfulness), harden the Excel output writers, and make pipeline review status driven by the
persisted outcome contract in `apps/engine/outcomes.py`.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy/SQLite, openpyxl, pdfplumber, PyMuPDF,
Docling, RapidOCR/Tesseract.

**References:** `BUILD-PLAN.md` (golden rules, canonical row shapes, validation policy),
`STAGES.md` (stages 3-8), `AUDIT-FINDINGS-2026-08-16.md`,
`docs/superpowers/specs/2026-08-17-ca-unpacker-full-product-design.md`.

## Global Constraints

- Reuse `FileOutcome` / `derive_job_status` in `apps/engine/outcomes.py`. Do not invent new
  file or job statuses.
- Never auto-correct a GSTIN or an amount. Flags and source pointers only (`BUILD-PLAN.md` section 10).
- Preserve canonical row shapes (`BUILD-PLAN.md` section 7) so Stage 8 recon joins keep working.
- One failing regression test per fix before implementation.
- Verification per task: `.venv\Scripts\python.exe -m pytest <focused tests> -q`.
- Verification per phase: `.venv\Scripts\python.exe -m pytest apps/engine/tests -q` (231 baseline, all green).

---

## Phase 1 - Bank parser correctness (Stage 3)

### Task 1.1: Capture amount sign and Dr/Cr indicators

**Files:** `apps/engine/parsers/bank/money.py`

- [ ] Add failing tests for `-1000.00`, `(2500.00)`, `1,00,000.00 Cr`, `2500Dr`.
- [ ] Extend `AMOUNT_RE` and `parse_amount` to accept a leading minus, surrounding
  parentheses, and a trailing or attached `Dr`/`Cr`; expose a sign-aware helper.
- [ ] Confirm overdrafts are no longer inverted.

**Verification:** new money tests pass; `test_stage3_bank.py` unchanged.

### Task 1.2: Accept integer and one-decimal amounts

**Files:** `apps/engine/parsers/bank/money.py`, `apps/engine/parsers/bank/layout.py`

- [ ] Add failing tests: `amounts_in("2500 147500")` and `"2500.5"` currently return `[]`.
- [ ] Relax the amount pattern to `\d[\d,]*\.?\d{0,2}` with boundary guards; make the
  table path and the line/column paths share one parser.
- [ ] Confirm dates and reference numbers are not mis-split.

**Verification:** integer and one-decimal statement fixtures parse rows.

### Task 1.3: Accept `DD-Mon-YYYY` dates

**Files:** `apps/engine/parsers/bank/money.py`, `apps/engine/parsers/bank/parser.py`

- [ ] Add failing tests: `12-Jun-2026`, `01-JUL-26` are currently unmatched.
- [ ] Add `-` to the separator class in `DATE_RE` and `DAY_MON_RE`; extend named-date parsing.
- [ ] Confirm full statements with hyphenated month dates produce rows.

**Verification:** hyphen-date fixture yields rows (currently 0).

### Task 1.4: Harden date normalization

**Files:** `apps/engine/parsers/bank/money.py`

- [ ] Add failing tests: `15/07/99` should not become `2099`; `31/13/2026` is invalid.
- [ ] Window two-digit years; validate day/month; return a flag on ambiguity rather than emitting invalid ISO.

**Verification:** date validation tests pass.

### Task 1.5: Fix debit/credit direction detection

**Files:** `apps/engine/parsers/bank/layout.py`, `apps/engine/parsers/bank/profiles.py`

- [ ] Add failing tests: `"MICR charges"` must not be a credit; `"IMPS from X"` must not default to debit.
- [ ] Match whole tokens (`\bcr\b`, `\bdr\b`); prefer explicit column or Dr/Cr indicator over
  narration; default to unknown plus a `direction_unknown` flag.
- [ ] Handle a single combined `Amount` column with Dr/Cr suffix.

**Verification:** direction tests pass; combined-amount fixture parses.

### Task 1.6: Never report MATCH on zero rows

**Files:** `apps/engine/validators/balance.py`, `apps/engine/pack/bank_xlsx.py`

- [ ] Add failing tests: `check_balance([], 1000, 1000)` currently returns `match`.
- [ ] Empty rows must yield `unverified`; the bank cover must not show green MATCH when `row_count == 0`.

**Verification:** balance and workbook cover tests pass.

### Task 1.7: Flag balance-derived corrections

**Files:** `apps/engine/parsers/bank/parser.py`, `apps/engine/pack/bank_xlsx.py`

- [ ] Add failing tests: a direction flip in `_align_to_running` and an `_implied_gap_row`
  must carry an explicit flag.
- [ ] Add `direction_inferred`; highlight `inferred_from_balance` rows in the workbook; surface
  inferred rows so a dropped page-break line is visible rather than hidden.

**Verification:** correction-flag tests pass.

### Task 1.8: Fix split rows and page breaks

**Files:** `apps/engine/parsers/bank/parser.py`, `apps/engine/parsers/bank/tables.py`,
`apps/engine/parsers/bank/plumber.py`

- [ ] Add failing tests: a two-line row (date/narration then amounts) and a row split across a
  page break.
- [ ] Allow merging an amount-bearing continuation when the current block has a date but no
  amounts; carry pending rows and `last_date` across pages in the table path.

**Verification:** split-row and cross-page tests pass.

### Task 1.9: Column mapping improvements

**Files:** `apps/engine/parsers/bank/tables.py`, `apps/engine/parsers/bank/patterns.py`,
`apps/engine/parsers/bank/layout.py`

- [ ] Add failing tests: a table with `Value Date` and `Txn Date` columns; a statement using `B/F`.
- [ ] Prefer transaction date over value date; add a combined `Amount` column; broaden
  opening/closing detection to `B/F`, `Brought Forward`, `C/F`, `Carried Forward`, `Closing Bal`.

**Verification:** column and opening/closing tests pass.

### Task 1.10: Strategy selection honesty

**Files:** `apps/engine/parsers/bank/parser.py`

- [ ] Add failing test: a text PDF must not report `docling` when Docling never ran.
- [ ] Only rank strategies that ran; tie-break on completeness; record the runner-up in diagnostics.

**Verification:** strategy test passes.

---

## Phase 2 - Invoice parser correctness (Stage 5)

### Task 2.1: Correct invoice date extraction

**Files:** `apps/engine/parsers/invoice.py`

- [ ] Add failing test: invoice number `ACME/26-27/0142` must not yield date `0142-27-26`.
- [ ] Extract dates only from labeled contexts (`Invoice Date`, `Bill Date`, `Dated`, `Dt`);
  exclude the invoice-number line and due date; flag `date_missing` instead of guessing.

**Verification:** date tests pass on shipped fixtures.

### Task 2.2: Stop fabricating tax; fix taxable value

**Files:** `apps/engine/parsers/invoice.py`

- [ ] Add failing test: `Taxable value 10000.00 / Total Tax 1800.00 / Invoice value 11800.00`
  must not produce `tax == taxable_value`.
- [ ] `_standalone_tax` must not match the prefix of `Taxable`; prefer explicit component
  labels. Read `taxable_value` from summary labels or line-item sums, never the item-table header.

**Verification:** Mehta two-line fixture and math tests pass.

### Task 2.3: Supplier name and GSTIN selection

**Files:** `apps/engine/parsers/invoice.py`

- [ ] Add failing tests: buyer GSTIN listed first; unlabeled letterhead supplier.
- [ ] Prefer a labeled supplier GSTIN; flag `gstin_ambiguous` when buyer and seller are both
  present; add a letterhead fallback for supplier name; flag `supplier_missing`.

**Verification:** extraction tests pass.

### Task 2.4: Evidence-based arithmetic flags

**Files:** `apps/engine/parsers/invoice.py`

- [ ] Add failing test: a pre-tax amount column must not raise a false `invoice_math`.
- [ ] Emit `invoice_math` only when taxable, tax, and total are all explicit; add a
  `line_sum_untaxed` note otherwise.

**Verification:** math-flag tests pass.

### Task 2.5: Add `date_out_of_period` validator

**Files:** `apps/engine/validators/`, `apps/engine/pipeline.py`

- [ ] Add the validator from `BUILD-PLAN.md` section 10 (warning only) and wire it into the pipeline.

**Verification:** validator tests pass.

---

## Phase 3 - GSTR / Tally / Zoho (Stages 6-7)

### Task 3.1: GSTR integrity

**Files:** `apps/engine/parsers/gstr.py`

- [ ] Add failing tests: string amounts become numeric cells; a `b2ba`-only file is not a silent empty success.
- [ ] Coerce all money via `_num`; add encoding fallback (`utf-8-sig` -> `utf-16` -> `cp1252`);
  detect recognized-but-unsupported sections and surface `unsupported_sections`; drop the
  all-None placeholder row.

**Verification:** GSTR parser and pack tests pass.

### Task 3.2: Tally voucher taxonomy and nested ledgers

**Files:** `apps/engine/parsers/tally.py`

- [ ] Add failing tests: `Purchase Order` must not become a purchase register.
- [ ] Restrict registers to Purchase/Sales (and register variants); map Order/Delivery Note/Journal
  to `other`; prefer the party-ledger amount for nested entries; normalize non-ISO dates.

**Verification:** Tally tests pass.

### Task 3.3: Zoho encoding, headers, and `.xls` policy

**Files:** `apps/engine/parsers/zoho.py`, `apps/engine/classifier.py`, `apps/engine/kinds.py`

- [ ] Add failing tests: latin-1 CSV; `GST Identification Number(GSTIN)` header.
- [ ] Add encoding fallback; normalize header punctuation before alias matching; reconcile the
  `.xls` policy with the classifier (default: reject `.xls`, guide to `.xlsx`/`.csv`, per
  `AUDIT-FINDINGS-2026-08-16.md`).

**Verification:** Zoho tests pass.

---

## Phase 4 - Classifier and password flow (Stage 4)

### Task 4.1: Reclassify encrypted PDFs after unlock

**Files:** `apps/engine/classifier.py`, `apps/engine/dump.py`, `apps/engine/pipeline.py`

- [ ] Add failing test: encrypted PDF -> set password -> reparse -> rows extracted.
- [ ] Reclassify on password-set or reparse; keep the password in memory only.

**Verification:** password flow test passes end to end.

### Task 4.2: Classifier precision

**Files:** `apps/engine/classifier.py`, `apps/engine/kinds.py`

- [ ] Add failing tests: invoice text with bank words is not `bank`; Zoho JSON with an `hsn`
  key is not `gstr_1`; a bank CSV is recognized.
- [ ] Require structural signals for bank; require GSTR-specific keys; add bank CSV detection;
  content-sniff `.txt` instead of routing only to Tally.

**Verification:** classifier tests pass.

### Task 4.3: OCR engine visibility

**Files:** `apps/engine/ocr.py`, `apps/engine/classifier.py`

- [ ] Record once why RapidOCR is unavailable; align `classifier._ocr_available` with
  `ocr.ocr_available`; pin bundled RapidOCR model paths so no first-run fetch occurs.

**Verification:** availability tests pass.

### Task 4.4: Wrong password reported as a password problem

**Files:** `apps/engine/pipeline.py`

- [ ] Add failing test: a wrong password must not be overwritten to `no rows extracted`.
- [ ] Preserve the `password_required` outcome through the pipeline so the user is re-prompted.

**Verification:** review-status test passes.

---

## Phase 5 - Output and pipeline integrity

### Task 5.1: Excel writer text sanitization

**Files:** `apps/engine/pack/*.py`

- [ ] Add failing test: a description containing `\x0b` currently aborts the whole pack.
- [ ] Add a shared `_clean()` that strips C0 control characters and truncates to 32767; apply to
  every text cell.

**Verification:** control-char test passes.

### Task 5.2: Excel writer numeric coercion

**Files:** `apps/engine/pack/bank_xlsx.py`, `apps/engine/pack/gstr_xlsx.py`

- [ ] Add failing test: `_money("1,180.00")` and `_money("Rs 500")` currently raise.
- [ ] Route numerics through a `to_float` mirroring `recon.money()`; return `None` on failure.

**Verification:** numeric coercion tests pass.

### Task 5.3: Atomic writes and per-artifact isolation

**Files:** `apps/engine/pack/*.py`, `apps/engine/pipeline.py`

- [ ] Add failing test: a writer that raises must not abort the period.
- [ ] Write to `*.tmp` then `os.replace`; wrap each output in `try/except`; surface a friendly
  `PermissionError` ("close the workbook").

**Verification:** writer-failure test passes.

### Task 5.4: Stale output purge

**Files:** `apps/engine/pipeline.py`, `apps/engine/settings.py`

- [ ] Add failing test: after a kind changes, the previous Excel must be gone.
- [ ] Write the pack into a per-run directory and swap, or delete outputs no longer produced.

**Verification:** stale-output test passes.

### Task 5.5: Outcome-driven review status

**Files:** `apps/engine/pipeline.py`, `apps/engine/outcomes.py`

- [ ] Add failing test: a deleted source (`source_missing`) must appear in `Needs_Review.xlsx`.
- [ ] Branch `_review_status` on `parse_outcome` / `parse_reason_code`; set `classify_reason` on
  the `source_missing` and `copy_failed` paths.

**Verification:** review-row tests pass.

### Task 5.6: Recon honesty

**Files:** `apps/engine/recon.py`, `apps/engine/pack/recon_xlsx.py`,
`apps/engine/pack/bank_xlsx.py`

- [ ] Add failing tests: a books row with no date must not false-match; a missing amount must
  not be reported as `amount_mismatch`.
- [ ] Downgrade missing-date matches to unverified; separate missing amounts; make sheet naming
  case-insensitive; give GSTR-1 a CDN sheet and align `CDN_TYPES`.

**Verification:** recon tests pass.

### Task 5.7: Accurate `row_count`

**Files:** `apps/engine/pipeline.py`

- [ ] Add failing test: `Needs_Review` file counts must not inflate `DataPack.row_count`.
- [ ] Count extracted rows only.

**Verification:** pack summary test passes.

---

## Phase 6 - Guardrails

### Task 6.1: Non-ASCII filenames

**Files:** `apps/engine/dump.py`

- [ ] Add failing test: `बैंक_विवरण.pdf` must keep its `.pdf` suffix and classify as bank.
- [ ] Sanitize the stem only and reattach the original suffix.

**Verification:** filename test passes.

### Task 6.2: Stale job recovery

**Files:** `apps/engine/dump.py`, startup path

- [ ] Add failing test: a job left in `parsing` by a dead process must be recoverable.
- [ ] Mark dead-owner `queued`/`routing`/`parsing` jobs failed on startup.

**Verification:** recovery test passes.

### Task 6.3: In-process run serialization

**Files:** `apps/engine/library.py`, `apps/engine/db.py`

- [ ] Add failing test: two periods parsed concurrently must not corrupt state.
- [ ] Add a `threading.Lock` (or per-period lock) and SQLite `BEGIN IMMEDIATE` for the
  delete/reinsert section.

**Verification:** concurrency test passes.

### Task 6.4: Regression corpus

**Files:** `apps/engine/tests/`, `make_*.py`

- [ ] Add realistic fixtures: overdraft, `DD-Mon-YYYY`, integer amounts, split rows,
  invoice number containing a date, buyer-GSTIN-first, string GSTR amounts, latin-1 Zoho,
  control characters, non-ASCII filenames.
- [ ] Wire the existing `*_busy` fixtures into tests.

**Verification:** full suite green, including the new fixtures.

---

## Suggested execution order

Trust-critical cut first: tasks 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 5.1, 5.2, 4.1. Then the remaining
tasks phase by phase. Each phase closes with a green full suite.
