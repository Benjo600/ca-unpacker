# Ultimate Document Scanning, OCR & Financial Extraction — Implementation Report

**Date:** 2026-11-15 · **Branch:** `feat/ultimate-document-scanning` (created from `feat/advanced-reconciliation` @ `3cc66f7`)
**Companion documents:** `TECHNICAL-ASSESSMENT-SCANNING-2026-11-15.md` (Phase 1 audit), `BENCHMARK-RESULTS-2026-11-15.md` (measurements)

---

## 1. Existing scanning architecture (verified before any change)

Ingestion: UI `start_dump` → `preflight_paths` → `ingest_paths` (daemon thread) → copy into
content store → `classify_path` (which ran a **full `extract_pdf` including OCR** per file) →
`parse_period` → per-kind parsers → `ExtractedRow` rows → Excel packs.

Extraction: three engines over the whole document (pymupdf, pdf-inspector, pdfplumber; pypdf last
resort), winner chosen document-wide, then an all-or-nothing OCR trigger — any single page flagged
`needs_ocr` promoted the *entire* document to OCR and OCR output overwrote native text pages.
OCR: RapidOCR → Tesseract, no preprocessing on PDF pages, word confidence used only as a drop
threshold and then discarded, per-page OCR failures silent.

Downstream: bank/invoice/GSTR/Tally/Zoho/SAP/vendor parsers, balance/GSTIN/HSN validators, pack
writers, advanced reconciliation (untouched — recon already had a complete decision trail).

## 2. Major weaknesses identified (audit result)

Full list with file:line references in the assessment document. Headline items:

1. Whole-document OCR overwrite destroyed native coordinates on mixed PDFs; no per-page routing.
2. Engine merge was document-level replace, not per-page merge.
3. No OCR digit-confusion repair (0/O, 1/I/l, 5/S, 8/B) — one confused character silently killed an amount.
4. Dr/Cr printed markers were stripped, never applied as directional evidence.
5. No image preprocessing for PDF pages (no deskew, denoise, threshold, variant selection).
6. OCR confidence discarded; no per-row extraction confidence or method anywhere.
7. Bank cross-page table continuation silently dropped page-boundary fragments.
8. Extensions fully trusted (no magic-byte sniffing); no content hash; no copy verification; the same file ingested twice was parsed twice.
9. Encrypted-PDF password dead-end: setting a password never re-classified the file.
10. Sign destruction (`abs()`) in Tally/vendor-statement amounts.
11. Invoice post-footer lines vanished unrecorded.
12. Double extraction (classification + parser each ran the full engine pass); a duplicate pdfplumber re-pass even when a verified ledger already existed.
13. `DATE_RE` did not match ISO dates (statements printed `2026-04-02` produced zero rows).
14. Invoice positional mapping mis-assigned amounts on single-line packed rows.
15. No cancellation for ingestion jobs.
16. Excel: western number formats everywhere except bank; up to 500 chars of raw OCR text shipped in the SAP workbook; no row-cap guards on table/gstr writers.
17. Migration system was solid (v3); additive-only extension path already proven.
18. No benchmark suite.

## 3. Architecture improvements implemented

**Per-page hybrid extraction** (`pdf_extract.py`): `_page_needs_ocr` routes per page — pages with a
usable text layer keep native coordinates; only text-poor pages are OCR'd; results merge per page
(`_merge_ocr_pages`), never letting an empty OCR pass blank native content. Mixed PDFs become
`pdf_type="mixed"` with `page_methods` recording which engine read each page. Measured by the
`mixed_pdf_per_page_routing` benchmark scenario.

**Extraction cache** (`pdf_extract.py`): classification and parsing reuse the same extraction
(path+size+mtime+password fingerprint, bounded to 4 entries ≤120 pages, deep-copied on hit) —
removing the audit's double-extraction cost.

## 4. OCR engines and extraction methods selected

Measured decision (assessment §3): **pymupdf + pdf-inspector + pdfplumber** (native paths),
**RapidOCR** (primary OCR) → **Tesseract** (fallback) → **Docling TableFormer** (deep fallback for
scanned bank tables, unchanged gating). PaddleOCR rejected (heavy install, no measurable accuracy
win for English financial text on this codebase); cloud OCR rejected (privacy guarantee).
`lines_strict` table strategy rejected after measurement (drops borderless-table detection).

## 5. Image-processing improvements

New `imageprep.py` (Pillow + numpy only — no OpenCV dependency added):
`assess` (contrast/ink/faint indicators), `estimate_skew`/`deskew` (projection-profile search,
±8° cap, no rotation for sub-degree noise), `enhance_contrast`, `denoise` (median r=1 — keeps
decimal points), `adaptive_threshold` (local mean, pure numpy integral image), `resolution_scale`
(band-limited, never upscales beyond 2×), `variant_sequence`.
`ocr.py` selects among variants by **measured recognition quality** (mean word confidence with a
word-count penalty) and stops early when a variant is already good; weak pages are retried at a
higher render scale and the better result wins (`_better_result` requires comparable word count).
RapidOCR init is now thread-safe (lock around lazy init). Standalone images get measured skew
correction (`_estimate_skew_safe`, ≥1° only). Originals are preserved — preprocessing feeds only
the OCR engine; crops/evidence come from `pdf_render` on the original.

## 6. Financial field accuracy improvements

- **`money.py`:** `parse_amount_with_evidence` (value + repair + Dr/Cr evidence); conservative OCR
  digit repair (`repair_ocr_digits` — strong lookalikes only, repaired text must fully parse and
  contain a separator, so reference numbers are never mangled); currency-edge stripping now accepts
  only *known ISO codes* (fixes `2OOO` → `2`); `DATE_RE` gains ISO dates.
- **Dr/Cr directional evidence** (`layout._debit_credit`): printed markers now outrank heuristics
  (`annotated_txn_direction`, glued `5,000.00Dr` and spaced `25,000 Dr`, balance-column markers
  correctly ignored).
- **Sign preservation:** Tally rows gain `amount_signed` + `direction`; vendor statements gain
  `direction` (magnitude kept for downstream compatibility).
- **GSTR:** additive `invoice_date_iso` normalisation (printed value preserved).
- **Invoice:** currency ambiguity flag (`currency_ambiguous`), HSN metadata lines recognised
  (`_METADATA_PREFIXES` += hsn/sac), "Bill To" per-word label matching for pymupdf word boxes,
  packed-run positional repair (full runs in order, sparse runs right-aligned, gap-separated
  tables unchanged), money-bearing unmappable rows recorded instead of folded into descriptions.
- **Bank:** ISO dates, word-position evidence, table-session state threading, hardcoded geometry
  now wrapped in evidence (unchanged where verified, flagged otherwise).

## 7. Table reconstruction improvements

`tables.py` rewritten around `TableSession`: pending narration threads **across pages/tables**
(page-boundary continuations no longer split-and-drop); repeated headers recorded as
`repeated_header` skips; orphan amount rows and incomplete fragments recorded in `skipped` with
reasons (surfaced in file parse warnings as `table_rows_skipped: N`) instead of vanishing;
`plumber.py` and `parser._rows_from_extracted_tables` feed all of a document's tables through one
session in order. Invoice `_line_items` records post-footer lines (`after_footer`) and remaining
lines when extraction stops.

## 8. Validation and quality-control capabilities

- New columns (migration **v4**, additive, backup-then-apply like v1→v3):
  `files.content_sha256`, `extracted_rows.extraction_confidence` (0..1, NULL = no recognition
  evidence — never zero), `extracted_rows.extraction_method` (`text`/`ocr`).
- Rows carry `extraction_confidence`/`extraction_method`/`extraction_notes` (repairs) additively in
  payload_json; OCR repair rows get `ocr_digit_repair` flags and a file-level warning.
- All existing validators unchanged and still flag-not-rewrite (balance/GSTIN/HSN advisory).
- Duplicate content: identical bytes ingested twice are both parsed and flagged
  (`duplicate content of …`, `duplicate_content` in the file payload) — never silently dropped.
- Honest outcomes preserved: broken GSTR stays `failed`, header-only invoice stays `needs_review`.

## 9. Source traceability improvements

Existing page/bbox/source columns preserved everywhere. Additions: `content_sha256` per file,
extraction method per row, `Page` columns added to Purchase/Sales/Line-items/Books/SAP workbooks,
crop previews verified reachable end-to-end (`get_source_crop` over real parsed rows in the
verification run). Recon's `_ca_*` provenance decoration untouched.

## 10. Large-file performance benchmarks

Before → after on balance-verified synthetic long statements (see §2 of the benchmark document):
36–54 s → **23–31 s** per 7–9 page statement; peak memory 33–64 MB; 120–160 rows at 4–6 rows/s
single-file, balance `match` with zero break flags. Root causes removed: duplicate pdfplumber
re-pass (12.2 s on the profiled document) now conditional on quality; classification↔parse double
extraction removed by the cache. Remaining cost is the three-engine pass itself (pymupdf
`find_tables` ≈1.1 s/page); further gains need lazy per-consumer table extraction (documented).

## 11. Memory and processing-time measurements

cProfile evidence in `BENCHMARK-RESULTS` §2; scenario timings and peak RSS per benchmark stored in
`apps/engine/benchmarks/results/last_run.json`; the app never loads page images wholesale (pages
are rendered, OCR'd and released per page; temp dirs are per-document; pypdfium2 bitmaps closed
deterministically — all pre-existing guards kept and re-verified).

## 12. Excel output improvements

New shared `pack/formatting.py`: Indian lakh/crore ₹ format (mirrors the recon report), foreign
currency symbols when rows agree, red negatives, `MAX_SHEET_ROWS` guard (clear error, never silent
overflow). Applied to table/gstr/recon workbooks. SAP workbook's raw-OCR debug column replaced with
a `Page` reference column. Date columns unchanged (strings preserved; not faked as dates).
`Needs_Review.xlsx` unchanged (already carries file/status/reason).

## 13. Integration results across existing modules

- **Verification through the real DesktopApi** (`verify_desktop_flow.py`, sandboxed library):
  firm/client/period → mixed month dump (7 files) → honest outcomes (4 processed / 1 review /
  1 failed / 1 unclassified) → previews with evidence → source crop reachable → 6 Excel packs →
  `gst_2b_invoices` reconciliation runs → 11 extracted rows with page refs and methods recorded.
- Recon consumption untouched (tolerant payload readers; `_ca_*` provenance keys unchanged).
- Desktop API gained `cancel_job`; UI gained a Cancel button + cancelled-status handling
  (`status-summary.js`, `app.js`, `index.html`, `styles.css`).
- Migration v4 follows the tested v1→v3 pattern (`repair_missing_columns` also covers older files).

## 14. New and modified files

**New:** `apps/engine/imageprep.py`, `apps/engine/evidence.py`, `apps/engine/pack/formatting.py`,
`apps/engine/benchmarks/` (synth, metrics, runner, `__main__`, results/),
`apps/engine/tests/{test_ingestion_integrity,test_job_cancellation,test_benchmarks}.py`,
`verify_desktop_flow.py`, `measure_scale.py`, `profile_scale.py`, `cprof_scale.py`,
`capture_app*.py` (screenshot tooling), `screenshots/`.

**Modified:** `pdf_extract.py`, `ocr.py`, `classifier.py`, `dump.py`, `pipeline.py`, `db.py`,
`migrations.py`, `pack/{table,gstr,recon}_xlsx.py`, `parsers/bank/{money,parser,layout,tables,plumber}.py`,
`parsers/{invoice,gstr,tally,vendor_statement}.py`, `desktop/app.py`,
`ui/{app.js,index.html,styles.css}`, `ui/status-summary.js`, `ui/tests/status-summary.test.js`,
and three test files (backup-name parameterisation, format assertions to the new shared format,
flpk skipped-rows intent preservation).

## 15. Database migrations

**v4** (`migrations.py`): `ALTER TABLE files ADD COLUMN content_sha256 VARCHAR(64)`,
`ALTER TABLE extracted_rows ADD COLUMN extraction_confidence FLOAT`,
`ALTER TABLE extracted_rows ADD COLUMN extraction_method VARCHAR(40)`. Additive only; backup
created before apply; fresh libraries stamped v4; older files repaired additively. Migration tests
parameterised to `LATEST_SCHEMA_VERSION` (assertions kept, now version-proof).

## 16. Full test results

| Suite | Baseline | Final |
|---|---|---|
| engine (`pytest apps/engine/tests -q`) | 507 passed, 4 skipped | **526 passed, 4 skipped, 36 subtests** |
| desktop (`pytest apps/desktop/tests -q`) | 54 passed | **54 passed** |
| UI status-summary (node) | passed | **passed** (incl. cancelled status) |
| benchmarks (pytest smoke) | — | **4 passed** |
| full benchmark suite | — | 8/8 scenarios at 1.0 / all checks ok |

No existing test was deleted, skipped or weakened; three era-pinned assertions were parameterised
to `LATEST_SCHEMA_VERSION` / the new shared currency format with intent preserved, and the flpk
skipped-rows assertion now asserts the stronger property (no silently dropped item rows).

## 17. Known limitations

- SAP PDF reader merges adjacent ID cells (recorded in benchmark `notes`, not hidden).
- Sub-150 dpi scans with glyph-split decimals defeat table strategies; lines strategy compensates
  when word boxes exist.
- English-scope OCR models only (RapidOCR/Tesseract shipped state).
- Dense-text statements spend ~1.1 s/page in pymupdf `find_tables`; lazy per-consumer table
  extraction is the documented next step.
- Cancellation is cooperative (file-boundary granularity) — by design, so partial results stay valid.
- Treatment/file-review flags still have no persisted decision state (documented; recon's audit
  trail is the pattern to reuse — a larger UI project deliberately not rushed).

## 18. Application screenshots (real desktop app, sandboxed library)

Captured from the actual PyWebView window (`capture_app*.py`, PrintWindow):

| File | Shows |
|---|---|
| `screenshots/01_app_window.png` | Real app window, fresh sandbox (sign-in gate) |
| `screenshots/02_workspace.png` | Period desk over a real parsed month: honest review states (failed/needs review/unclassified) beside processed files with row counts and currency |
| `screenshots/04_dashboard.png` | Dashboard live counts (7 documents · 4 processed · 3 need attention) |
| `screenshots/05_reconciliation.png` | Reconciliation Control Centre over the same data |
| `screenshots/06_reports.png` | Reports list with all six generated Excel packs |

The end-to-end verification (upload → classification → extraction → review evidence crops → Excel
generation → reconciliation) was driven through the real `DesktopApi` surface in a sandboxed
library; nothing outside `%TEMP%` was touched and the working tree was not committed.
