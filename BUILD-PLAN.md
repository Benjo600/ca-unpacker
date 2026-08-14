# CA Data Unpacker — Full Project Build Plan

A Windows desktop app where a CA dumps every client document. Processing stays on that PC. They get back a GST-ready, source-linked, reconciliation-ready data pack.

This file is the **whole-product** plan. It is not a ticket-by-ticket implementation spec.

Build order and pass/fail gates live in `STAGES.md`. Do not start the next stage until the current gate is checked.

Source: `ca portal idea.docx`

---

## 1. Product in one paragraph

CAs currently run bank PDFs through one tool, invoices through another, GST portal JSON through a third, Tally through a fourth, then spend ~40% of their time pasting four Excels into a master sheet before real work starts. This product is a **smart document factory**, not a generic OCR tool: classify each file, send it to a specialist parser, validate GST/bank math, and emit a unified pack plus (later) a master reconciliation grid.

**Generic tool:** “We extract text.”
**This tool:** “We extract GST-ready data, validate it, and deliver a pre-reconciled master Excel.”

---

## 2. Users and jobs

| Who | Job |
|---|---|
| Practising CA / article staff | Create a client, dump a month’s documents, download clean files, start recon |
| Firm owner (later) | Multiple staff, usage limits, billing |
| Out of scope for v1 | Clients uploading their own docs, government e-filing, Tally live API write-back, cloud processing of client files |

**First success test (from the idea doc):** upload a messy bank statement PDF → click convert → get a formatted Excel with validation alerts in ~2 minutes. Ask: “Would you pay ₹2,500/month for this for every client document?”

---

## 3. Golden rules (non-negotiable)

1. **Contextual routing.** Never one generic model for every file. Bank PDF, invoice image, GSTR JSON, and Tally export each have their own parser.
2. **Show your work.** Every extracted row has a Source pointer (file + page + region). Preview: click a number → cropped snippet from the original.
3. **Validate, don’t just extract.** GSTIN checksum, HSN length, bank debit/credit vs stated closing balance.

---

## 4. What we will not build in the first product

- Legal contracts, property papers, ITR PDFs, Form 26AS, salary slips
- Live GST portal login / scraping (CAs upload JSON/PDF they already downloaded)
- Live Tally ODBC / TallyPrime running instance (we read **exports**, not a live company)
- Full ITC recon engine as a standalone product (that is the later Tier 1 upsell)
- GSTR-9 auto-filler (Tier 2 upsell)
- Mobile app
- Multi-firm white-label
- Sending client PDFs/JSON to any cloud API (OCR vendors included) in v1

Those stay on the roadmap only as named later phases.

---

## 5. Platform decision: Windows desktop, local processing

**Yes — this is feasible, and it is now the plan.** Indian CAs will not put a month of client bank statements and GSTR JSON on someone else’s server. Local processing is the product, not a compromise.

The parsers (PDF tables, OCR, Excel, GSTIN checks) are already Python. Python runs well on Windows 10/11. The hard part is **packaging**, not the processing.

### What “Windows app” means here

- One installer (`.exe` / Inno Setup). Double-click, no Docker, no browser bookmark, no “start the server.”
- Every original file, page image, SQLite DB, and output Excel stays under the user’s profile, e.g. `%LOCALAPPDATA%\CAUnpacker\`.
- The engine never uploads client documents. License check (phase 8) may ping the internet; files do not.
- A 50-page digital bank PDF is fine on a normal CA laptop. A 50-page *scan* is slower (OCR) but still local.

### Three ways to ship it (and the pick)

| Approach | Pros | Cons |
|---|---|---|
| **A. Python engine + WebView2 window (recommended)** | Same portal UI we already wanted; parsers stay Python; WebView2 is already on Win 10/11; one language for the engine | Need a thin shell + a Vite/React UI bundle |
| **B. Pure native Python UI (PySide6)** | One runtime, simpler installer | Dense CA tables, crop preview, dump tray are slower to build in Qt widgets |
| **C. Electron + Python sidecar** | Familiar web stack | 200–400 MB, two runtimes, worse Windows Defender false positives |

**Pick A.** A small Windows shell (pywebview, or Tauri talking to a local Python worker) opens a desktop window. The window loads a local React UI. The UI calls the local Python engine. Nothing listens on the public network — bind `127.0.0.1` only if we use HTTP at all.

Do **not** use Postgres, Redis, or Docker on the CA’s PC. Those are server toys. SQLite + a process/thread pool is the local equivalent.

```
┌──────────────────────────────────────────────────────────┐
│  Windows app window (WebView2)                           │
│  clients · dump tray · job status · crop preview         │
└──────────────────────────┬───────────────────────────────┘
                           │ in-process / localhost only
┌──────────────────────────▼───────────────────────────────┐
│  Python engine (shipped inside the installer)            │
│  classifier · bank/invoice/gstr/tally parsers            │
│  validators · Excel pack writer · job runner             │
└──────┬─────────────────────────────┬─────────────────────┘
       │                             │
  SQLite                        Disk folder
  %LOCALAPPDATA%\               %LOCALAPPDATA%\
  CAUnpacker\app.db             CAUnpacker\files\
                                CAUnpacker\packs\
```

Tesseract (OCR) is bundled in the installer, not “please install this separately.”

### Firm / multi-PC reality

v1 is **one machine = one firm library**. A small firm that wants two articles on two PCs either:

- works on one shared machine, or
- later (phase 9) points the data folder at a NAS / OneDrive folder we treat as the library.

Do not build a cloud sync service until a paying firm asks.

### Windows-only constraints we design for

| Topic | Rule |
|---|---|
| OS | Windows 10 21H2+ or Windows 11. WebView2 Evergreen. |
| Paths | Never assume `/tmp`. Use `pathlib` + `%LOCALAPPDATA%`. |
| Long paths / OneDrive | Support `\\?\` and warn if the library sits on a syncing Desktop/OneDrive folder (lock files). Prefer LocalAppData. |
| Password PDFs | Prompt in the app; keep password in memory for the job only. |
| Defender / SmartScreen | Unsigned `.exe` will warn. Code-sign before first paid rollout (phase 8). |
| CPU | Parse jobs off the UI thread. Show progress. Cap parallel OCR (default 1–2 workers) so the laptop stays usable. |
| RAM | Render PDF pages one-at-a-time for scans, not all 80 pages in memory. |

---

## 6. Tech stack (lock this unless we have a reason to change)

| Layer | Choice |
|---|---|
| Shell | Windows desktop window via **pywebview (WebView2)** |
| UI | Vite + React + TypeScript + Tailwind (static files loaded by the shell) |
| Engine | Python 3.12, packaged with PyInstaller |
| Engine API | FastAPI bound to `127.0.0.1` on a random local port, or pywebview `js_api` (same machine only) |
| DB | **SQLite** + SQLAlchemy 2 + Alembic |
| Jobs | In-process thread/process pool (no Redis) |
| Files | `%LOCALAPPDATA%\CAUnpacker\` (library root configurable in Settings) |
| Native PDF tables | pdfplumber (primary), camelot as fallback for lattice tables |
| Scanned PDF / images | pypdfium2 → page images → **bundled Tesseract** |
| Excel in/out | openpyxl |
| Installer | Inno Setup (one `.exe`), includes Python engine + Tesseract + WebView2 bootstrap if missing |
| Auth (phase 1) | None. This PC holds the firm data. Optional unlock PIN later. |
| Billing (phase 8) | License key / Razorpay; online check only. Documents stay local. |
| Tests | pytest for parsers/validators; Playwright against the UI in a window or `localhost` |
| Package layout | `apps/desktop` (shell), `apps/ui`, `apps/engine` |

**Accuracy rule in code:** the classifier only chooses a parser. It never extracts amounts. Each parser owns its schema.

**Cloud OCR is off by default.** A later setting may allow it; v1 never sends a page image out.

---

## 7. Domain model

```
Firm   (one row on this PC)
  id, name, plan, file_quota_month, library_path, created_at

User   (unused in v1; this PC is the operator)
  id, firm_id, display_name, pin_hash (optional later)

Client
  id, firm_id, name, gstin (optional), pan (optional), status

Period
  id, client_id, label  e.g. "FY 2025-26 / Jul"
  (a dump belongs to a client + period so 12 months of history can live here)

Job
  id, client_id, period_id, status (queued|routing|parsing|validating|packing|done|failed)
  created_by, error_message, started_at, finished_at

File
  id, job_id, original_name, mime, size, storage_key
  detected_kind (bank|invoice|gstr_1|gstr_2b|gstr_3b|tally|zoho|unknown)
  parser_name, page_count, confidence

ExtractedRow
  id, file_id, kind, payload_json
  source_file_id, source_page, source_bbox
  validation_flags[]   e.g. ["gstin_checksum", "hsn_length", "balance_mismatch"]

DataPack
  id, job_id
  bank_xlsx_key, purchase_xlsx_key, gstr2b_xlsx_key, master_xlsx_key
```

**Canonical row shapes** (shared contract between parsers and Excel writers):

**Bank line**

- date, description, cheque_ref, debit, credit, balance, account_name, account_number, ifsc (if present)
- source_page, source_bbox, raw_text

**Invoice / purchase line**

- supplier_name, supplier_gstin, invoice_number, invoice_date
- taxable_value, cgst, sgst, igst, cess, invoice_value
- hsn, place_of_supply, document_type (tax invoice / debit / credit)
- source_page, source_bbox

**GSTR-2B / GSTR-1 line**

- gstin, trade_name, invoice_number, invoice_date, invoice_value
- taxable, igst, cgst, sgst, cess, itc_availability (2B)
- source: portal json path or pdf page

**Tally / Zoho register line**

- voucher_type, voucher_number, date, party_name, gstin
- taxable, tax_breakup, ledger, amount
- source: export file + row index

Every Excel the product emits is a projection of these shapes. Do not invent a fifth schema inside the spreadsheet writer.

---

## 8. End-to-end pipeline

```
1. CA creates Client (+ Period)
2. Dump: drag-drop many files (pdf, jpg, png, json, zip, txt, xml)
3. Job created. Files stored. Job queued.
4. Classifier (metadata + first-page text + light structure)
      → bank | invoice | gstr_* | tally | zoho | unknown
5. Unknown files stay in an "Needs review" tray. CA can override kind and re-run.
6. Specialist parser writes ExtractedRows + source pointers
7. Validators attach flags (they do not silently "fix" numbers)
8. Pack builder writes:
      Bank_Statement_Cleaned.xlsx
      Purchase_Register_Extracted.xlsx
      GSTR_2B_Formatted.xlsx
      Master_Reconciliation_Grid.xlsx   (phase 7)
9. UI: job done → download pack + preview any flagged cell against the crop
```

**Classifier signals (phase 1, rule-based first)**

| Signal | Suggests |
|---|---|
| Filename contains `GSTR2B`, `GSTR-2B`, `2B` + JSON | gstr_2b |
| JSON keys like `gstin`, `fp`, `b2b` | gstr_1 / gstr_2b / gstr_3b by schema |
| Zip/xml with Tally namespaces or `DAYBOOK` / `VOUCHER` | tally |
| Zoho Books export headers | zoho |
| Multi-page PDF + words like Opening Balance, Withdrawal, Deposit, CR/DR | bank |
| 1–2 page image/PDF + GSTIN regex + Invoice No | invoice |

Add an ML classifier only if rule-based routing is wrong often. The idea doc’s 60% → 95% jump comes from **specialist parsers**, not from a fancy router.

---

## 9. The four MVP parsers

### 9.1 Bank parser

**Input:** native digital PDFs and scanned PDFs of Indian bank statements (HDFC, ICICI, SBI, Axis, Kotak first; add banks as samples arrive).

**Output:** one sheet of transactions + a cover sheet with opening, closing, computed close, match/mismatch.

**Key feature:** auto-match stated closing balance vs running total.

**Build order inside this parser**

1. Digital table extraction (pdfplumber) for 2–3 common bank layouts
2. Column mapping (date / narration / debit / credit / balance) with a layout profile per bank
3. Running balance check + mismatch flag
4. Scanned PDF path (render pages → OCR → same mapper)
5. Source bbox per row (table cell coords, or OCR word boxes)

**Hard parts to budget time for:** merged header rows, two-column “narration + chq no”, credit/debit in one signed column, password-protected PDFs (ask for password in UI; never store it after the job).

### 9.2 Invoice parser

**Input:** JPEG, PNG, single/multi-page PDF tax invoices.

**Output:** one grid row per invoice (and line items in a second sheet if present).

**Key feature:** flag invalid GSTINs.

**Build order**

1. GSTIN regex + checksum validator on any text we can read
2. Field extraction: supplier, GSTIN, invoice no, date, taxable, tax, total, HSN
3. HSN length flag (must be 4, 6, or 8)
4. Math flag: taxable + tax ≈ invoice value (tolerance ₹1)
5. Source crop for each field, not just each row

Start with **printed GST tax invoices**. Handwritten bills are phase-later.

### 9.3 Portal extractor (GSTR-1 / 2B / 3B)

**Input:** official JSON download first; PDF only if JSON is missing.

**Output:** a readable register (2B especially: “ugly JSON turned beautiful”).

**Key feature:** one-click download of a pre-shaped recon grid (empty match columns until phase 7).

This is the easiest high-value parser. Build JSON **before** PDF. Official schema is stable enough to write typed Pydantic models.

### 9.4 Tally / Zoho reader

**Input:** Tally export (XML / daybook / XML-in-zip) and Zoho Books CSV/XLS export. Not a live Tally company.

**Output:** purchase register + sales register in the same canonical invoice-like shape so they can join 2B later.

**Key feature:** usable registers without opening Tally.

Zoho is a CSV mapper. Tally XML is the real work (namespaces, voucher types, inventory vs accounting). Budget it last of the four.

---

## 10. Validation layer

Validators are pure functions over canonical rows. They never call OCR.

| Check | Applies to | Fail behaviour |
|---|---|---|
| GSTIN format + checksum | invoice, 2B, Tally | flag `gstin_checksum` |
| HSN length in {4,6,8} | invoice, Tally items | flag `hsn_length` |
| Invoice arithmetic | invoice | flag `invoice_math` |
| Bank running balance vs stated close | bank | flag `balance_mismatch` + cover-sheet alert |
| Date parseable, in the selected period | all | flag `date_out_of_period` (warning) |
| Duplicate invoice (gstin + inv no + date) | invoice + 2B + Tally | flag `possible_duplicate` |

**Policy:** never auto-correct a GSTIN or an amount. CAs will not trust a tool that silently edits source data. Flags + source crop only.

---

## 11. Excel pack (the product)

Always the same filenames, always a **Source** column.

| File | When | Sheets |
|---|---|---|
| `Bank_Statement_Cleaned.xlsx` | bank files in job | Transactions, Balance Check |
| `Purchase_Register_Extracted.xlsx` | invoices and/or Tally purchases | Register, Flags |
| `GSTR_2B_Formatted.xlsx` | 2B present | B2B, Flags |
| `Master_Reconciliation_Grid.xlsx` | phase 7 | 2B vs books vs bank (summary) |

**Source column format:** `filename.pdf#p12@x,y,w,h` so the web preview can jump without another lookup table (DB still stores the structured bbox).

**Preview mode:** click a cell in the app table (not inside Excel) → modal with the page image cropped to bbox. Excel is the takeaway; trust is built in the app.

---

## 12. Product UI (what we actually screen)

1. **First launch** — firm name, where to keep the library (default LocalAppData)
2. **Clients list** → create client (name + optional GSTIN)
3. **Client home** → periods (Apr, May, …) → open a period
4. **Dump tray** — large drop zone *and* “Add folder”; mixed files, no pre-labelling
5. **Needs review** — unknown files, override type, requeue
6. **Job progress** — per-file: queued / routed to X / parsed / flags (never freeze the window)
7. **Results** — tables + flag filters + crop preview + **Open pack folder** / Save As
8. **Settings** — library path, worker count, bundled Tesseract status
9. **Later:** license key, usage meter
10. **Later:** shared library folder for a second PC

UI tone: a working desk for a busy CA in the first two weeks of the month. Dense tables, obvious flags, almost no marketing chrome inside the app. Native window: drag files from Explorer, open output in Excel with one click.

---

## 13. Pricing (implement late, design now)

| Plan | Price | Product behaviour |
|---|---|---|
| Starter | ₹999/month | 100 files/month, bank + invoice only |
| Pro | ₹2,500/month | unlimited files, all 4 parsers + validation |
| Suite | ₹6,000/month | Pro + recon + future GSTR-9 (not built yet) |

Phase 1–6: no paywall. Hard-code “Pro” features on. Phase 8: Razorpay + quota on Starter.

---

## 14. Phased roadmap

Each phase ends with something a CA can click. Do not start the next phase until the previous one is demoable.

### Phase 0 — Windows skeleton (about 3–5 days)

- Monorepo: `apps/desktop`, `apps/ui`, `apps/engine`
- pywebview window loads the Vite UI
- Engine starts with SQLite in `%LOCALAPPDATA%\CAUnpacker\`
- One dummy “create client” screen
- Dev loop: `python -m desktop` (no Docker)
- **Done when:** double-clicking the dev entry opens a Windows window that can create a client

### Phase 1 — Dump + router

- Clients + periods (no login)
- Drag-drop from Explorer + add folder
- Job record, progress in the window
- Rule-based classifier + manual override
- Copy-in (do not parse in-place): originals go to the library
- **Done when:** drop a mixed folder, see each file labelled bank/invoice/gstr/tally/unknown

### Phase 2 — Bank parser + first Excel (first real demo)

- Digital PDF path for 2–3 banks
- Canonical bank rows in DB
- Balance check validator
- `Bank_Statement_Cleaned.xlsx` written to the pack folder; “Open in Excel”
- Source page number in Excel (bbox can be rough)
- **Done when:** the idea-doc GTM test works on a real messy statement, on a Windows laptop, with no internet

### Phase 3 — Trust: source crops + scan path

- Render PDF pages to images
- Store bbox; click-to-crop in the results UI
- Scanned-PDF / image OCR path for banks
- Password-protected PDF prompt
- **Done when:** a CA can click a debit and see the number on the scan

### Phase 4 — Invoice parser

- Image + PDF invoices
- GSTIN checksum + HSN + invoice math flags
- `Purchase_Register_Extracted.xlsx`
- Field-level crops
- **Done when:** a folder of purchase bills becomes a flagged register

### Phase 5 — GSTR portal extractor

- GSTR-1 / 2B / 3B JSON → typed models → formatted Excel
- PDF portal extracts only if we still need them after JSON
- Pre-shaped recon columns (empty)
- **Done when:** an ugly 2B JSON becomes a readable sheet in one click

### Phase 6 — Tally / Zoho reader

- Zoho CSV/XLS mapper
- Tally XML / zip daybook → purchase + sales registers
- Same canonical shape as invoices
- **Done when:** a Tally export produces registers without opening Tally

### Phase 7 — Master reconciliation grid

- Match 2B vs books (GSTIN + invoice no + date + amount tolerance)
- Optional: bank lines vs invoice totals (weaker match; treat as assist, not gospel)
- `Master_Reconciliation_Grid.xlsx` + in-app unmatched tray
- **Done when:** one job with bills + 2B + books shows matched / unmatched / amount-mismatch

### Phase 8 — Billing, quotas, lock-in basics

- Razorpay Starter / Pro
- File-count quota on Starter
- Export history stays on the firm (data gravity)
- Suite plan visible but gated (“coming”)
- **Done when:** a test UPI/card sub enforces the 100-file cap

### Phase 9 — Hardening for real firms (after first paying CAs)

- More bank layouts from real samples
- Shared library folder (NAS / second PC) with a lock file
- Duplicate-period protection
- Delete-client (wipe files from disk, not just the DB row)
- Accuracy dashboard (override rate, flag rate)
- Code-signed installer; SmartScreen reputation

### Later (not scheduled)

- ITC recon product (Tier 1)
- GSTR-9 auto-filler (Tier 2)
- More portals (e-way bill, 26AS) only if CAs ask twice

---

## 15. Suggested repo layout

```
ca-unpacker/
  apps/desktop/             pywebview shell, window, file dialogs
  apps/ui/                  Vite + React (dump tray, tables, preview)
  apps/engine/              Python processing engine
    engine/routers/         clients, files, jobs, packs
    engine/library.py       %LOCALAPPDATA% paths
    engine/jobs.py          local worker pool
    engine/parsers/bank/
    engine/parsers/invoice/
    engine/parsers/gstr/
    engine/parsers/tally/
    engine/parsers/zoho/
    engine/validators/
    engine/pack/            excel writers
    tests/                  fixtures: sample pdfs/json (anonymised)
  third_party/tesseract/    bundled at install time, not in git
  installer/                Inno Setup script
  BUILD-PLAN.md             this file
```

Keep sample documents **anonymised**. Never commit a real client PDF.

---

## 16. Testing strategy

| Kind | What |
|---|---|
| Parser fixtures | One anonymised file per bank / invoice style / GSTR JSON version. Golden Excel or golden JSON of expected rows. |
| Validators | Table-driven unit tests (known good GSTIN, known bad checksum, known balance break). |
| Classifier | Folder of mixed filenames + tiny fixtures → expected kind. |
| App smoke | Create client → drop fixture → wait for done → pack xlsx exists and opens. |
| Accuracy | Manual scorecard: % rows a CA would accept without edit. Target ≥ 95% on digital bank PDFs before calling phase 2 done. Scans start lower; do not block phase 2 on scan quality. |

---

## 17. Risks (plan around these)

| Risk | Mitigation |
|---|---|
| Every bank PDF is a different layout | Bank **profiles**, not one mega-parser. Add a profile when a CA sends a sample. |
| CAs refuse to trust AI numbers | Source crop is phase 3, not a polish item. Never silent-fix. |
| OCR on bad phone photos | Accept “needs review”; don’t pretend 95% on garbage scans. |
| Scope explosion (recon, GSTR-9, live Tally) | This file’s phase gates. Recon is phase 7. |
| Password PDFs / huge 80-page statements | Job queue + password prompt + page cap with a clear error. |
| Legal: storing client financials | Files never leave the PC in v1. Delete-client wipes disk. Say this in the first-run screen. |
| “Just install this .exe” friction | One installer; bundle Tesseract; no Docker; no Python on PATH required. |
| Windows Defender flags PyInstaller | Code-sign before paid rollout; submit to Microsoft if needed. |
| OneDrive lock / file-in-use | Default library is LocalAppData, not Desktop. Detect sync folders and warn. |
| Two articles, two PCs | Out of v1. Shared-folder library is phase 9. |

---

## 18. What we build immediately after this plan is approved

**Phase 0 + Phase 1 + Phase 2 only** as the first implementation plan:

1. Windows window + SQLite library (no Docker)
2. Client + dump + classifier
3. Bank parser for digital PDFs + balance check + Excel on disk

That is the smallest product that proves the idea-doc story. Phases 3–8 stay in this file as the map; they get their own implementation plans when we start them.

---

## 19. Open decisions (defaults if you say nothing)

| Decision | Default |
|---|---|
| Platform | Windows 10/11 desktop, local processing |
| Shell | pywebview (WebView2) + Vite/React UI + Python engine |
| First banks | HDFC, ICICI, SBI |
| First auth | None (this PC is the firm) |
| OCR | Bundled Tesseract only; no cloud OCR in v1 |
| Hosting | No server. Installer on the CA’s PC. |
| Recon in v1 | No. Phase 7. |
| Billing in v1 | No. Phase 8 license key, files still local. |

If any default is wrong, change it here before Phase 0 starts.
