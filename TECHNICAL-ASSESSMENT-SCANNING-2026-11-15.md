# Technical Assessment — Document Scanning, OCR & Financial Extraction Pipeline

**Date:** 2026-11-15 · **Branch:** `feat/ultimate-document-scanning` (from `feat/advanced-reconciliation` @ `3cc66f7`)

Phase 1 audit of the complete pipeline before any code changes. Everything below was verified by
reading the code, not assumed. A parallel audit of the desktop shell, persistence, Excel packs and
recon consumption accompanies this (see §8 for the integration map).

---

## 1. Existing architecture (verified)

Ingestion → extraction → persistence today:

```
UI (start_dump) → preflight_paths → assert_can_ingest → start_job
  → ingest_paths (daemon thread, dump.py:417)
      StoredFile rows (size=0, kind="unknown") committed first
      per file: stat check → 100MB cap → shutil.copy2 → dest.is_file() only
      classify_path(dest)  ← runs a FULL extract_pdf (incl. OCR) per file (classifier.py:312-325)
  → parse_period_banks (pipeline.py:278)
      per file: _dispatch_stored → _dispatch → per-kind parser
      rows → pending_extracted (payload_json, source_page, source_bbox, validation_flags)
      packs written to disk → ExtractedRow delete+reinsert → DataPack
```

Extraction stack (`pdf_extract.py`): three engines run over the whole document —
pymupdf (text+words+find_tables), pdf-inspector (markdown+positioned items), pdfplumber
(text+words+2 table strategies); pypdf as last resort (zero coordinates). Winner is chosen
document-wide; tables merged; words/lines replaced wholesale by whichever candidate has more words.
Then `_should_ocr` (pdf_extract.py:195) — **document-level, all-or-nothing**: any single page with
`needs_ocr=True` (e.g. one blank separator page) promotes the *entire document* to OCR, and the OCR
result overwrites text-layer pages/lines/words (pdf_extract.py:114-126).

OCR (`ocr.py`): RapidOCR singleton (no lock on lazy init) → Tesseract fallback. PDF pages are
rendered at fixed scale 2.0 with **no preprocessing** (no autocontrast, deskew, denoise, threshold —
only standalone *images* get `autocontrast`). Word confidence is used purely as a drop threshold
(RapidOCR <0.35, Tesseract <40) and then **discarded — never persisted anywhere**. Per-page OCR
exceptions are silently swallowed (ocr.py:393-395): a page that fails contributes zero lines and no
warning. Docling runs only as a deep fallback for scanned bank PDFs.

Records: bank rows carry date/description/debit/credit/balance + `source_page`/`source_bbox`/
`source` ("file#pN@bbox") + currency stamp. Invoice headers/line items carry located-field evidence
(`fields` map with page+bbox), `checks`, `flags`, `skipped_rows`. GSTR/Tally/Zoho rows carry no
coordinates (JSON path / filename only). There is **no per-row extraction confidence** anywhere; row
trust is expressed only through string flags. `ExtractedRow` persists payload_json + source_page +
source_bbox + validation_flags; packs are rebuild-per-run (delete+reinsert).

Recon consumes `payload_json` via tolerant `.get()` chains and decorates rows with
`_ca_file_id/_ca_page/_ca_bbox/_ca_currency` — additive payload keys are safe.

## 2. Major weaknesses identified (ordered by financial-data risk)

**A. Accuracy-critical**
1. **Whole-document OCR overwrite on mixed PDFs** (pdf_extract.py:114-126). Searchable pages lose
   their exact text-layer coordinates and are replaced by lower-fidelity OCR boxes. No per-page
   routing exists. pdfplumber never sets `needs_ocr` (pdf_extract.py:432), so whether a mixed PDF
   gets OCR depends on which engine happened to win.
2. **Engine merge is document-level replace, not per-page merge** (pdf_extract.py:105-108): if
   candidate B has more words overall, pages where A was better are silently downgraded to B.
3. **No OCR digit-confusion repair anywhere.** An OCR'd `O` for `0`, `l`/`I` for `1`, `S` for `5`,
   `B` for `8` fails `[0-9.,']+` in `parse_amount` (money.py:152) and the amount silently becomes
   `None` — the row drops or loses its amount with no flag.
4. **Dr/Cr suffixes are stripped but never applied** (money.py:126-127): `"25,000 Cr"` parses to
   +25000 and the sign is then guessed by heuristics, defeating the strongest printed evidence.
5. **No image preprocessing for PDF pages**: no deskew (skewed phone photos band into wrong lines),
   no denoise, no adaptive thresholding for faint photocopies; autocontrast only for raster images.
   No variant selection by measured quality.
6. **OCR word confidence is discarded**; no row-level or field-level confidence exists; per-page OCR
   failure is silent.
7. **Bank cross-page table continuation splits transactions**: `pending` narration is reset per
   pdfplumber table; a fragment lacking date/balance fails `_row_ok` (tables.py:156-161) and is
   dropped **silently**. A page-boundary continuation is often lost entirely.
8. **Hardcoded geometry**: debit/credit/balance assigned by absolute x-bands 340/415/488 pt
   (bank/parser.py:395-400) — an A4-portrait assumption; other layouts mis-assign amounts.
9. **`_debit_credit` sign guessing** uses substring keyword matching (layout.py:268-273) and a
   positional guess (`amounts[-3]` is debit) that can mis-assign on 3-amount layouts.
10. **Sign destruction**: Tally `_amount` applies `abs()` (tally.py:151-157) — debit notes and
    credit notes become numerically identical; vendor statement `abs(debit-credit)` (line 37-41)
    loses direction.
11. **Invoice post-footer lines vanish unrecorded** (invoice.py:1155-1170): after a totals row, same
    page lines are skipped and a later page without a repeated header `break`s — not even in
    `skipped_rows`.
12. **Classification window is tiny**: first 4 pages / 30 lines (classifier.py:318-320); a scanned
    cover page misclassifies the document. Double extraction cost: classification runs a full
    extract_pdf (incl. OCR) and each parser re-extracts again (bank/parser.py:67, invoice.py:315).

**B. Ingestion integrity**
13. **Extensions fully trusted** — no magic-byte sniffing; a renamed ZIP/`.pdf` misroutes to
    `unknown` with a misleading reason. TIFF is in `IMAGE_SUFFIXES` but never sanity-checked.
14. **No content hash, no copy verification**: dedupe is path-only (dump.py:204, 250); the same
    statement dropped twice under different names is ingested, parsed and reconciled **twice**.
    Copy success is `dest.is_file()` only (dump.py:485).
15. **Password dead-end**: an encrypted PDF classifies `unknown`/`password-protected`;
    `parse_period` skips unknown kinds (pipeline.py:321-332), so setting a password + Retry never
    parses the file unless the user also manually overrides the type.

**C. Scale & operability**
16. **No cancellation** for ingestion jobs; only wipe/kill. No retry counter. RapidOCR singleton
    has a check-then-set race (ocr.py:19-31); Tesseract sets process-global state per call.
17. Memory: whole document's words/lines/tables held at once; period-wide `pending_extracted` list
    before bulk insert. Guards exist (500 pages, 1,048,575 rows, 100 MB) — good.
18. Pack/DB inconsistency window: XLSX written before the DB commit (pipeline.py:470-637).

**D. Output & review**
19. table/gstr/recon workbooks use bare `#,##0.00` — western grouping, no ₹, no red negatives
    (bank pack and recon-run report do this properly; the shared builders were just never reused).
20. SAP workbook ships up to 500 chars of raw OCR text in a customer column (`Source row`).
21. No row-cap guard on table/gstr writers (bank has one). No page/bbox columns outside bank.
22. No persisted review state for treatment/file-review flags; corrections have no audit trail
    (recon has a complete one).

## 3. Engine selection (Phase 4 evaluation, measured on this codebase)

| Engine | Role | Verdict |
|---|---|---|
| pymupdf text/words/tables | primary text path | keep — best coordinates + find_tables |
| pdf-inspector | markdown + item boxes | keep — feeds inspector line parsers |
| pdfplumber | table strategy 2nd pass | keep — only engine with strategy scoring |
| RapidOCR (ONNX local) | primary OCR | keep — offline, fast, no install; **needs lock + preprocessing + confidence persistence** |
| Tesseract (bundled) | OCR fallback | keep — discovery chain already solid |
| Docling TableFormer | deep fallback for scanned bank tables | keep — expensive, correctly gated |
| PaddleOCR | candidate | **rejected**: heavy install (paddle wheel + model downloads), no accuracy win over RapidOCR on English financial text to justify 2nd engine |
| Cloud OCR | candidate | **rejected**: violates local-only privacy guarantee |

Chosen architecture: **per-page hybrid extraction** — native text per page where the text layer is
usable; OCR per page only where needed; quality-based variant selection for image preprocessing;
confidence captured from whichever engine produced the words; Docling unchanged as deep fallback.

## 4. What will be implemented (and what deliberately not now)

Implementing (Stages 2-7 of the plan):
- **Ingestion integrity**: sha256 content hash + copy size verification, magic-byte sniffing with
  extension-mismatch surfacing, duplicate-content flagging (never silent drop), TIFF validated.
- **Per-page hybrid extraction** in `pdf_extract.py` (mixed searchable/scanned PDFs keep native
  coordinates on text pages; OCR only pages that need it; per-page method recorded).
- **Image preprocessing** (`imageprep.py`): autocontrast, denoise, adaptive threshold, deskew
  estimate, resolution assessment — variant selection by measured OCR quality; original preserved.
- **OCR evidence**: WordBox/LineBox confidence persistence, per-page failure warnings, RapidOCR
  init lock, row-level `extraction_confidence`/`extraction_method` on bank + invoice rows.
- **Numeric accuracy**: OCR digit-confusion repair with evidence (0/O, 1/I/l, 5/S, 8/B + more),
  Dr/Cr as directional evidence in bank rows, sign preservation in Tally/vendor statement,
  GSTR date normalization (additive ISO field), invoice currency ambiguity flag.
- **Table reconstruction**: cross-page pending-narration threading for bank tables, repeated-header
  skipping, unrecorded-fragment accounting, post-footer line capture in invoices.
- **Validation/QC**: `extraction_confidence` + method columns (migration v4), duplicate-content
  warnings in file outcomes & Needs_Review, existing balance/GSTIN/HSN validators preserved.
- **Password dead-end fix**: setting a password on an unknown/password file re-classifies it.
- **Cancellation**: cooperative cancel flag checked per file; `cancel_job` API.
- **Excel quality**: shared Indian-currency number formats with red negatives, page references,
  row-cap guards, raw-text column capping.
- **Benchmark suite**: synthetic ground-truth documents (searchable, scanned, low-res, rotated,
  multi-page, mixed) + CER/WER/field/amount/row-recall/timing/memory metrics + persisted results.

Explicitly deferred (documented, not silently skipped): Tesseract OSD orientation detection for
≥15° rotations (deskew estimator covers small skews first), per-field manual-correction audit UI
(recon already has decision-trail patterns to reuse — treatment/file-review state is a larger UI
project), full 1,000-page streaming (existing guards + cancellation cover the realistic range),
regional-language OCR models (no bundled tessdata for them; RapidOCR English is the shipped scope).

## 5. Non-negotiables respected

- No working parser replaced without evidence; changes are additive behind the same entry points.
- Existing schemas preserved; DB changes are additive `ALTER TABLE ADD COLUMN` via migration v4
  following the tested v1→v2→v3 pattern (backup → step → version bump).
- Everything stays local/offline; no new mandatory dependencies (opencv is already present as a
  transitive dependency of docling; imageprep uses Pillow/numpy which are already required).
- Flags, never silent rewrites, except the existing (flagged) `_align_to_running` behaviour which
  stays untouched.
- Existing tests must keep passing; new tests use independently constructed ground truth.

## 6. Baseline (recorded before changes)

- Branch `feat/advanced-reconciliation` @ `3cc66f7`, working tree clean except untracked `ca/`
  placeholder dir and `start-log.txt` runtime log.
- Full `apps/engine/tests` + `apps/desktop/tests` suite run recorded in
  `BENCHMARK-RESULTS-2026-11-15.md` (updated as work lands).

## 7. Files inventory (planned)

| Change | Files |
|---|---|
| New | `apps/engine/imageprep.py`, `apps/engine/evidence.py`, `apps/engine/benchmarks/*`, `pack/formatting.py` |
| Modified | `pdf_extract.py`, `ocr.py`, `money.py`, `bank/{parser,layout,tables,plumber}.py`, `invoice.py`, `gstr.py`, `tally.py`, `vendor_statement.py`, `dump.py`, `classifier.py`, `kinds.py`, `pipeline.py`, `db.py`, `migrations.py`, `pack/{table,gstr,recon,bank}_xlsx.py`, `desktop/app.py`, `ui/app.js` (cancel button) |
| Migrations | v4: `files.content_sha256`, `extracted_rows.extraction_confidence`, `extracted_rows.extraction_method` |
