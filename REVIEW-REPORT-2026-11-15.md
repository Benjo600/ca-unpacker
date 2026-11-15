# Independent Review Report — Ultimate Document Scanning Upgrade

**Date:** 2026-11-15 · **Reviewer scope:** post-implementation quality & regression review of `feat/ultimate-document-scanning` before approval
**Rule honoured:** no new features added during review; discovered defects were fixed; nothing committed or pushed.

---

## 1. Git safety — CONFIRMED

- Branch is `feat/ultimate-document-scanning`; HEAD `3cc66f7` equals `git merge-base HEAD feat/advanced-reconciliation` equals `feat/advanced-reconciliation` tip — the branch sits exactly one commit on the declared parent with all work uncommitted in the working tree.
- No stashes exist; no reset/clean/checkout/amend/commit/push performed.
- **30 tracked files modified** (engine: pdf_extract, ocr, classifier, dump, pipeline, db, migrations, 3 pack writers, 5 bank-parser files, invoice/gstr/tally/vendor_statement; tests: 4 era-pinned fixtures updated intent-preserving; desktop/app.py; UI app.js/index.html/styles.css/status-summary.js + its test) plus **runtime-log-only** `start-log.txt`.
- **24 untracked paths**: 4 new engine modules (`imageprep.py`, `evidence.py`, `pack/formatting.py`, `benchmarks/`), 3 new test files, 3 report docs, 7 review/verification scripts (`review_*.py`, `verify_desktop_flow.py`, `measure_scale.py`, `profile_scale.py`, `cprof_scale.py`, `capture_app*.py`), `screenshots/`, and the pre-existing empty `ca/` placeholder (untouched).
- Working tree preserved exactly; review scripts are untracked additions only.

## 2. Financial accuracy review — 46/46 adversarial checks PASS

`review_financial_accuracy.py` (kept as an untracked review artifact) plus targeted suite runs:

- **Reference numbers never repaired**: `12AB3`, `INV-12O5`, `XYZ 500`, `NIFTY 50` → None; `9405` remains a legitimate plain integer (HSN exclusion is the caller's `_HSN_TOKEN_RE` job — pre-existing, intended).
- **Repairs are evidence-backed and originals preserved**: `1O5,OOO.OO` → 105,000.00 with `repaired_from` = original; `(l,234.56)` → −1234.56 (parentheses sign preserved through repair); `-1O,OOO.50` → −10000.50; clean values report `repaired=False`.
- **Locale parsing**: Indian `1,25,000.50`, European `1.234,56`, French space, Swiss apostrophe, trailing minus, parentheses negatives, known-code currency stripping (`INR`/`₹`/`USD`), `1.234` ambiguity → None, `1,234` → thousands.
- **Dr/Cr evidence**: spaced/glued/perioded markers set direction; balance-column markers ignored; **conflicting `Dr`+`Cr` → refused**; **markers after bare reference numbers rejected** (`REF 12345 DR` no longer hijacks the real 500.00 debit — positional evidence wins).
- **Defects found & fixed during review** (2 High): pure Indian grouping `12,34,567` / `1,00,000` returned None (count>1 branch mis-read the trailing group as a fraction) — fixed in `_parse_number`; conflicting Dr/Cr and bare-reference Dr markers mis-graded — fixed with `_NUMBER_BODY` token guard and conflict refusal.
- Original values remain available: row `raw_text`, `extraction_notes`, `repaired_from`, and flags are all additive — nothing is silently rewritten.

## 3. PDF & table extraction — 15/15 adversarial checks PASS

`review_extraction.py` (kept): cross-page wrapped narration (survives the page boundary, not double-counted, ledger still balances), repeated headers never become rows, orphan amount rows recorded in skipped/warnings (nothing silent), mixed searchable+scanned (page 1 native, page 2 OCR, both pages carry text), blank middle page (no phantom rows), faint scan (contrast 0.45) extracts, rotated 2.5° scan extracts, borderless single-line tables extract with correct debit/credit split.

- **Defects found & fixed during review** (1 High + 2 latent): the absolute debit/credit/balance x-bands (340/415/488 pt) mis-fired on image-coordinate pages — a rotated image statement produced debit=0/balance=2500 that *happened to reconcile* with a fabricated gap row (silently wrong, no flags). Bands are now gated to PDF-point pages; zero debit/credit is never emitted; plus a missing import and a bad unpack that crashed one OCR fallback path.
- **Rotated-page OCR accuracy**: RapidOCR mis-read `98,000.00` as `00·00086` at "good enough" quality; the variant selector now treats digit-runs broken by bullet glyphs as a failure signature, keeps trying preprocessing variants, and the threshold variant reads the value correctly (`rapidocr:threshold`). End-to-end: the rotated transaction now extracts with the correct amounts.

## 4. Migration v4 on a COPY of a v3 library — 59/59 PASS

`review_migration_v4.py` (kept), all databases in temp dirs; the real library was never touched:

- Realistic v3 library built (firms/clients/periods/jobs/files/extracted_rows/data_packs with representative data), copied, then migrated.
- Backup `app.db.v3-to-v4.backup`: version 3, byte-equivalent data, v4 columns absent. Migrated DB: version 4, three new columns with exact types (`VARCHAR(64)`/`FLOAT`/`VARCHAR(40)`), **every value of every row preserved**, new columns NULL on old rows. Reopen idempotent (still one backup). ORM reads/writes the new columns cleanly.
- Interrupted migration (step that alters then raises): RuntimeError propagates, version still 3, partial column absent, data intact; a subsequent real run completes the migration (recovery), leaving a second non-overwriting backup.
- **Defects found & fixed during review** (1 Medium + 1 Low, both on the repair path only — normal v3→v4 was unaffected): repaired list-typed `*_json` columns got `'{}'` defaults (now model-driven `[]`/`{}`); repaired `parse_outcome` got `''` instead of `'unclassified'` (now honours the model's `server_default` literal, with TextClause-safe handling).

## 5. Integration regression through the real DesktopApi — 63/63 PASS

`review_integration.py` (kept), fully sandboxed: mixed-month upload → honest outcomes (4 processed / 1 review / 1 failed / 1 unclassified) with source evidence on every bank row; Dashboard and Reports reflect the data; SAP CSVs detected/parsed with `SAP_Reports_Extracted.xlsx`; currency override accepted/persisted on an inferred statement (invalid codes refused); recon `gst_2b_invoices` matched 1/1 with explainable fields, `bank_accounting` degrades gracefully with an explanatory message; wrong-type override → honest needs-review (no invented rows, verified in the DB); source crops reachable; cancellation honoured (immediate *and* delayed), no stuck jobs.

- **Defects found & fixed during review** (2 High + 1 Medium): a wrong-type override ("invoice" file forced to "bank") manufactured a processed ₹5,900 transaction from invoice header totals — now refused honestly via the `no_statement_context` guard (no opening/closing balance evidence + ≤2 rows ⇒ needs-review, not a fabricated ledger); the immediate-cancel lost-update race (worker's blind `status="routing"/"parsing"` writes erased a concurrently committed `cancel_requested`) — fixed by re-reading the job at every status transition, verified through the real API.
- Low observations (no action needed): the confirmed-currency refusal branch is covered by `test_currency.py` ("clearly shows USD") rather than by test-dump fixtures; a manual override can be re-overridden (by contract; UI shows both as "confirmed").

## 6. Benchmark integrity — CONFIRMED, with evidence gaps fixed

Independent audit of `apps/engine/benchmarks/`: ground truth is by-construction (generator imports no parser code; expectations are literals used for both rendering and grading; invoice arithmetic self-consistent; statement running-balance verified; ledger truth matches the planted rows line-by-line). All eight hard scenarios intact (rotated, low-res, multipage, mixed per-page routing, ledger). Amounts and Dr/Cr are graded separately from text metrics; nothing is derived from parser output.

- **Defects found & fixed during review** (1 High + 3 Medium): the pytest smoke run clobbered `results/last_run.json` (now separate `pytest_smoke.json`); `python -m apps.engine.benchmarks` never exited nonzero (now exits 1 on errors/failed checks); `status="ok"` ignored failed checks (now `failed_checks`); `amount_accuracy` let one occurrence satisfy duplicate expectations (now multiset-consumed); the ledger scenario had no Dr/Cr direction metric (now `dr_cr_accuracy` graded per row). The full suite is now asserted by tests (all eight scenarios, thresholds row_recall/dr_cr/amount ≥0.99, duplicates ≤0.01), not just two.
- Minor notes left as-is: ground-truth literals duplicated in runner.py (safe direction — drift causes false alarms, never false passes), `total_maths_ok` vacuous when the parser's checks list is empty (other six checks bind), dead CER/WER helpers documented as informational.

## 7. Exact test results (final state)

| Suite | Result |
|---|---|
| `pytest apps/engine/tests -q` | **530 passed, 4 skipped, 36 subtests, 0 failed** (526 before review; +4 from the strengthened benchmark tests) |
| `pytest apps/desktop/tests -q` | **54 passed, 0 failed** |
| UI status-summary (node) | **passed** |
| `pytest apps/engine/tests/test_benchmarks.py -q` | **8 passed** (smoke + full-suite assertions) |
| `python -m apps.engine.benchmarks` | 8/8 scenarios at 1.0 / all checks ok, **exit code 0**, full artifact restored |
| Adversarial reviews | financial 46/46 · extraction 15/15 · migration 59/59 · integration 63/63 |

## 8. Migration results

v4 upgrade of a copied v3 library: **59/59 checks pass** after the two repair-path fixes above. Backup created and verified pre-migration; data preserved byte-for-byte; reopen idempotent; interrupted migration rolls back cleanly and recovers on the next run. Production library never touched.

## 9. Remaining limitations (unchanged, documented)

- SAP PDF table reader merges adjacent ID cells (`5100000012 KR`) — recorded in benchmark `notes`.
- Sub-150 dpi scans with glyph-split decimals can still defeat table strategies (the lines strategy compensates when word boxes exist).
- English-scope OCR models; extreme rotations (>8°) rely on the deskew cap.
- Dense-text statements spend ~1.1 s/page in pymupdf `find_tables`; lazy per-consumer table extraction remains future work.
- Treatment/file-review flags still have no persisted decision state (recon's audit trail is the pattern to reuse).

## 10. Git status confirmation

Working tree preserved; branch `feat/ultimate-document-scanning` one commit above `feat/advanced-reconciliation`; review added only untracked scripts/reports (`review_financial_accuracy.py`, `review_extraction.py`, `review_migration_v4.py`, `review_integration.py`, `debug_rotated.py`, this report). No stash, no commit, no push — **waiting for explicit approval**.
