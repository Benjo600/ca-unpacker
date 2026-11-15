# Scanning & Extraction — Benchmark Results (2026-11-15)

**Branch:** `feat/ultimate-document-scanning` · **Engine:** baseline `feat/advanced-reconciliation` @ `3cc66f7`
**Suite:** `python -m apps.engine.benchmarks` (results persisted to `apps/engine/benchmarks/results/last_run.json`)
**Principle:** every metric is graded against ground truth known by construction — never against the
parser's own output. Monetary accuracy and debit/credit classification are graded separately from
general text, because misreading an amount is worse than misreading prose.

---

## 1. Ground-truth scenarios (final state)

| Scenario | Input | Metric | Result |
|---|---|---|---|
| clean_searchable_invoice | searchable PDF, 3 line items | field_accuracy | **1.0** |
| | | amount_accuracy | **1.0** |
| | | total-maths checks | **all ok** |
| scanned_invoice_ocr | 96 dpi JPEG-softened image (RapidOCR) | field_accuracy | **1.0** |
| | | amount_accuracy | **1.0** |
| clean_statement | searchable 6-txn statement | row_recall / dr_cr / amounts | **1.0 / 1.0 / 1.0** |
| | | duplicates | **0.0** |
| lowres_statement | 100 dpi blurred image | row_recall / dr_cr / amounts | **1.0 / 1.0 / 1.0** |
| rotated_statement | 120 dpi image rotated 2.5° (deskew path) | row_recall / dr_cr / amounts | **1.0 / 1.0 / 1.0** |
| multipage_statement_continuation | 2-page PDF, repeated header, wrapped narration | row_recall / dr_cr / amounts | **1.0 / 1.0 / 1.0** |
| mixed_pdf_per_page_routing | page 1 text layer + page 2 scanned image | page-1 native / page-2 OCR / both pages text | **all ok** |
| ledger_table_extraction | columnar 7-column SAP-style ledger | row_recall / amounts | **1.0 / 1.0** (document_number cells merged by SAP PDF reader recorded in `notes`) |

Runtime: ~37 s total, peak RSS 11–108 MB per scenario (mixed-PDF scenario includes two full engine
passes). The OCR scenarios reuse the shipped local RapidOCR models — nothing is downloaded.

During bring-up the suite caught and drove three real fixes:
1. `DATE_RE` did not match ISO dates (`2026-04-02`) — ISO statements produced zero transactions.
2. Invoice positional mapping mis-assigned amounts for single-line packed rows (the fix: contiguous
   value runs map in document order; sparse packed runs right-align to trailing columns; visible-gap
   tables keep strict x-band mapping).
3. Post-footer invoice lines and page-boundary table fragments were dropped silently.

## 2. Large-document scale (before → after this branch)

Synthetic long statements (`make_long_statements.py`, balance-verified):

| Statement | Pages | Rows | Before | After | Balance |
|---|---|---|---|---|---|
| AXIS_SouthSpices | 7 | 120 | 51.6 s | **31.6 s** | match |
| HDFC_MehtaTrading | 9 | 160 | 54.2 s | **28.6 s** | match |
| ICICI_AnitaMehta | 8 | 140 | 39.7 s | **24.2 s** | match |
| SBI_KiranAgencies | 8 | 130 | 36.0 s | **23.3 s** | match |

Peak memory 33–64 MB per parse; zero `running_balance_break`/`balance_mismatch` flags.

**Where the time goes (cProfile, HDFC 9-page statement):**
- before: full parse 34 s = `extract_pdf` 20.2 s (pymupdf `find_tables` 10.2 s + pdfplumber tables
  7.9 s) **+ a duplicate pdfplumber re-pass of 12.2 s** (the lines strategy had already produced a
  balance-matched 160-row ledger; the re-pass recomputed the same rows).
- after: the re-pass runs only when no cheaper strategy yields a balance-verified ledger
  (`_quality` rank < 3). The lines strategy itself costs 0.21 s for 160 rows.
- an extraction cache (`extract_pdf`) removes the remaining double work between classification and
  parsing in the real app flow (both previously ran the full three-engine pass).
- `pymupdf find_tables(strategy="lines_strict")` was measured 28 % faster with identical output on
  the benchmark document but is **rejected**: it drops borderless-table detection, which invoice
  parsing depends on. Accuracy is not traded for speed.

## 3. Test suites

| Suite | Baseline | Final |
|---|---|---|
| `apps/engine/tests` | 507 passed, 4 skipped | **526 passed, 4 skipped** (0 failed) |
| `apps/desktop/tests` | 54 passed | **54 passed** (0 failed) |
| `apps/engine/tests/test_benchmarks.py` | — | 4 passed |

New tests added on this branch:
`test_ingestion_integrity.py` (11), `test_job_cancellation.py` (4), `test_benchmarks.py` (4), plus
migration-v4 coverage through the existing `test_migrations.py` (parameterised, all assertions kept).

## 4. Known limitations (measured, not hidden)

- **SAP PDF table reader merges adjacent ID cells** (`5100000012 KR`): the benchmark records
  `document_number_cells_merged` instead of hiding it. Row recall is graded on reference+amounts.
- Sub-150 dpi scans with broken decimals (glyph-split cells, e.g. `4821\n.`) defeat the table
  strategies; the lines strategy compensates when word boxes are available.
- Regional-language OCR is out of scope for the shipped models (English financial text is the
  product's documented scope).
- 22–31 s for a 9-page dense text statement is dominated by the three-engine extraction pass
  (pymupdf `find_tables` ≈ 1.1 s/page). Further gains require lazy per-consumer table extraction —
  documented as future work, not silently shipped as a heuristic.
