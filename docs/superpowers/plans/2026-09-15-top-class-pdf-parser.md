# Top-Class PDF Parser Plan

> **For agentic workers:** Implement this plan workstream by workstream. Each task starts with a
> failing regression test, then the change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the local PDF extraction layer so that every downstream parser receives a
faithful, coordinate-consistent document model with real table-cell provenance, and so that
extraction quality is measured against a real corpus. The layer never silently loses or invents
content.

**Architecture:** Introduce a canonical document model (pages, words, lines, tables with cell
bounding boxes), normalize all engines to one coordinate space (PDF user space, bottom-left
origin, points, rotation-applied), select/fuse engines deterministically per page (digital vs
scanned), reconstruct tables with a scored cascade, and emit an extraction report plus a
confidence signal that feeds `apps/engine/outcomes.py`.

**Tech Stack:** PyMuPDF 1.28, pdfplumber 0.11, pdf-inspector 1.18, Docling 2.126
(TableFormer), RapidOCR 3.9 (onnxruntime backend), Tesseract, pypdfium2, OpenCV, Pillow, pytest.

**References:** `BUILD-PLAN.md` (golden rules, "show your work", Windows constraints),
`docs/ADDING-A-BANK.md`, `AUDIT-FINDINGS-2026-08-16.md`,
`docs/superpowers/specs/2026-08-17-ca-unpacker-full-product-design.md`.

## The contract

No PDF parser can guarantee correctness on unpredictable documents. The achievable and
required guarantee is:

> **Every extraction is either self-verified or explicitly flagged as uncertain. Silent wrong
> output is zero.**

For bank statements this is enforceable because the numbers self-check:
`balance[i] = balance[i-1] - debit[i] + credit[i]`, plus the printed closing balance. The
extraction layer's job is to reconstruct the document faithfully and hand the parser enough
evidence to prove or doubt the reconstruction.

## Global Constraints

- Local only. No page image, text, or derived artefact leaves the machine.
- One coordinate convention everywhere: PDF user space, bottom-left origin, points, rotation
  applied, 1-based pages. `apps/engine/pdf_render.py` already assumes this; enforce it in every engine.
- Nothing is merged across coordinate spaces.
- No bare `except: pass` in the extraction layer; every failure is recorded in the extraction report.
- Preserve the public shape that parsers already consume (`ExtractedPdf` with `pages`, `lines`,
  `words`, `tables`) so parsers keep working during migration.
- Verification per task: `.venv\Scripts\python.exe -m pytest <focused tests> -q`.

---

## Current-state diagnosis (verified)

| # | Defect | Location |
|---|---|---|
| 1 | Coordinate spaces mixed: PyMuPDF and pdfplumber flip y to bottom-left; pdf-inspector does not, and `extract_pdf` then merges words across engines | `pdf_extract.py:98-105`, `_words_from_items` |
| 2 | Table `bbox` is always the whole page, never the table region | `pdf_extract.py:275`, `:461`, `plumber.py:_page_bbox` |
| 3 | No table cell coordinates; `ExtractedTable` is only a string grid | `pdf_extract.py:39-45` |
| 4 | Two divergent pdfplumber table configs (lines-first vs text-first) | `pdf_extract.py:427`, `plumber.py:8` |
| 5 | Two duplicate markdown-table parsers | `pdf_extract.py:233`, `tables.py:38` |
| 6 | All-or-nothing OCR; no per-page handling of mixed digital+scan PDFs | `pdf_extract.py:111-123` |
| 7 | RapidOCR is dead: `onnxruntime` not installed, failure swallowed | `ocr.py:16-29` |
| 8 | Rotation ignored; word bboxes and render crops diverge on rotated pages | `pdf_extract.py`, `pdf_render.py` |
| 9 | pypdf fallback fabricates zero-coordinate boxes | `pdf_extract.py:629-636` |
| 10 | Fixed 3pt line banding | `_lines_from_words` |
| 11 | Docling only runs when fewer than 5 lines and 10 words | `parser.py:54-56` |
| 12 | Extraction repeats at classify, preview, and parse; no cache | `classifier.py`, `pipeline.py` |

Confirmed toolchain: `pymupdf 1.28.2`, `pdfplumber 0.11.10`, `pdf-inspector 1.18.0`,
`docling 2.126.0` + `docling-ibm-models 4.0.2`, `rapidocr 3.9.2`, `pypdfium2 5.13.0`,
`opencv-python 5.0.0.93`, `Pillow 12.3.0`; `onnxruntime` **missing**.

---

## Workstream 1 - Canonical document model

**Files:** `apps/engine/pdf/model.py` (new), `apps/engine/pdf_extract.py`

- [ ] Add failing test: every Word/Line/Table reports a page, a real bbox, and an engine.
- [ ] Define the model: `Document`, `Page`, `Word`, `Line`, `Table`, `Cell`, `ExtractionReport`.
- [ ] `Table` carries a real `bbox` and a grid of `Cell` objects, each with its own bbox,
  `row`, `col`, `rowspan`, `colspan`, `is_header`, and text.
- [ ] Extend the existing `ExtractedPdf` dataclasses with the new optional fields (no breaking
  rename) and provide an adapter so parsers keep working.

**Verification:** model tests pass; existing parser tests unchanged.

## Workstream 2 - Coordinate normalization and rotation

**Files:** `apps/engine/pdf/coords.py` (new), `apps/engine/pdf_extract.py`,
`apps/engine/parsers/bank/layout.py`

- [ ] Add failing tests: same page yields identical word boxes from PyMuPDF and pdfplumber;
  a rotated page yields bboxes that map to the rendered image crop.
- [ ] Normalize all engines to bottom-left origin, points, rotation applied (PyMuPDF
  `page.rotation_matrix`); fix pdf-inspector's missing y-flip.
- [ ] Add a coordinate round-trip test through `pdf_render._pixel_box`.

**Verification:** coordinate and crop tests pass.

## Workstream 3 - Faithful digital text

**Files:** `apps/engine/pdf/engines/pymupdf.py` (new), `apps/engine/pdf_extract.py`

- [ ] Add failing test: a dense statement with varying fonts yields correct line grouping.
- [ ] Make PyMuPDF the primary digital engine: rotation-aware words, adaptive line clustering
  (font size and baseline, not fixed 3pt), intra-line gap preservation.
- [ ] Remove fabricated coordinates from the pypdf fallback; mark it bbox-unusable in the report.

**Verification:** text/line tests pass; no zero-coordinate words reach the DB.

## Workstream 4 - Table reconstruction cascade

**Files:** `apps/engine/pdf/tables.py` (new), `apps/engine/parsers/bank/plumber.py`,
`apps/engine/parsers/bank/docling_tables.py`, `apps/engine/parsers/bank/tables.py`

- [ ] Add failing tests: a ruled table, a borderless table, and a table split across two pages.
- [ ] Cascade strategies: pdfplumber `lines`, pdfplumber `text`, PyMuPDF `find_tables`, then
  Docling TableFormer for hard cases.
- [ ] Score each candidate (row/column consistency, non-empty ratio, header plausibility,
  presence of a numeric column); pick the best and retain the runner-up in the report.
- [ ] Extract real cell bboxes (pdfplumber `table.rows[].cells`, PyMuPDF, Docling) so every row
  and cell has a source region; set the table bbox to the actual region.
- [ ] Stitch multi-page table continuations (repeated headers, split rows).
- [ ] Unify the two pdfplumber table configs and the two markdown-table parsers into this module.

**Verification:** table tests pass; bank source crops point at the correct cell.

## Workstream 5 - Scanned and OCR path

**Files:** `apps/engine/pdf/ocr.py` (moved from `apps/engine/ocr.py`),
`apps/engine/pdf_extract.py`, `README`/`requirements.txt`

- [ ] Add failing tests: a mixed PDF (page 1 digital, page 2 scanned) OCRs only page 2.
- [ ] Add `onnxruntime` to `requirements.txt`; verify `RapidOCR()` initialises; record an
  explicit reason when it does not.
- [ ] Decide OCR per page; render one page at a time via pypdfium2 at a fixed scale.
- [ ] Preprocess scans: orientation detection, deskew, DPI normalization (OpenCV).
- [ ] Use Docling TableFormer for tabular scans; RapidOCR primary, Tesseract fallback, with one
  consistent confidence threshold.
- [ ] Self-check OCR output (expected column count, numeric regex, balance equation) and flag
  low-confidence pages.
- [ ] Pin RapidOCR model paths to bundled assets so no first-run download occurs.

**Verification:** OCR, mixed-page, and rotation tests pass.

## Workstream 6 - Orchestration, fusion, diagnostics, cache

**Files:** `apps/engine/pdf_extract.py`, `apps/engine/classifier.py`,
`apps/engine/pipeline.py`, `apps/engine/preview.py`

- [ ] Add failing test: a document reports which engines ran, coverage, tables found, OCR used.
- [ ] Replace ad-hoc winner selection with deterministic per-page engine policy (digital vs
  scanned) and element-precedence fusion; never merge across coordinate spaces.
- [ ] Attach an `ExtractionReport` and expose it in outcome metadata for debuggability.
- [ ] Cache extraction by file hash so classify, preview, and parse reuse one result.
- [ ] Replace bare `except: pass` with recorded failures.

**Verification:** orchestration tests pass; repeated calls hit the cache.

## Workstream 7 - Extraction self-verification and confidence

**Files:** `apps/engine/pdf/verify.py` (new), `apps/engine/outcomes.py`

- [ ] Add failing tests: out-of-page boxes, inconsistent table column counts, and a page with
  near-zero text coverage are flagged.
- [ ] Add checks: every box within page bounds; table cells within the table bbox; column
  consistency; text coverage per page; duplicate rows; engine agreement on key numbers.
- [ ] Compute a per-document and per-row confidence from engine tier and invariant agreement;
  feed it to the outcome contract so unverified output routes to `needs_review`.

**Verification:** verification tests pass; low-confidence docs land in review.

## Workstream 8 - Corpus and accuracy harness

**Files:** `apps/engine/tests/corpus/`, `scripts/score_extraction.py` (new), `STAGES.md`

- [ ] Add an anonymized sample corpus: at least one digital and one scanned statement per
  supported bank, a mix of invoice styles, and one GSTR/Tally/Zoho export each.
- [ ] Add golden expectations (expected IR summary and/or expected rows) per sample.
- [ ] `score_extraction.py` reports per file: text character accuracy, table cell accuracy,
  row precision/recall, and **false-MATCH rate**.
- [ ] Add a CI gate: false-MATCH rate must be 0; row recall threshold on digital baselines.

**Verification:** harness runs on the corpus and prints a per-file scorecard.

---

## Milestones

1. **M1 - Faithful foundation:** Workstreams 1-3. Correct coordinates, real table cell bboxes,
   reliable lines. Fixes the broken "show your work" crops and column detection.
2. **M2 - Table accuracy:** Workstream 4. The biggest accuracy lever for bank statements.
3. **M3 - Scans:** Workstream 5. RapidOCR restored, per-page OCR, preprocessing, Docling.
4. **M4 - Trust:** Workstreams 6-7. Diagnostics, caching, verification, confidence into outcomes.
5. **M5 - Evidence:** Workstream 8. Corpus and scorecard, then parser integration (bank first).

## Decisions to confirm

1. **Architecture:** hybrid (PyMuPDF + pdfplumber for digital, Docling for scans and complex
   tables) versus Docling-centric. Recommend hybrid: fast, accurate digital path and ML tables
   only where needed.
2. **Model:** extend the existing `ExtractedPdf` dataclasses versus a new IR module with an
   adapter. Recommend extend plus new optional fields for low churn.
3. **Table engine investment:** pdfplumber versus Docling TableFormer versus the scored cascade.
   Recommend the cascade, decided by the corpus scorecard.
4. **Corpus:** the harness is only as good as the samples. Real anonymized documents are the
   gate for any accuracy claim.
