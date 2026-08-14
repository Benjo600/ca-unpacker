# CA Data Unpacker — Stage Gates

Companion to `BUILD-PLAN.md`. That file is the product map. This file is the **order we build**, and the **only** reason we are allowed to start the next stage.

**Rule:** do not start Stage N+1 until Stage N’s gate is checked. A half-working stage is not a pass. If a later stage needs a fix in an earlier one, go back, pass that gate again, then continue.

**Current stage:** Prototype pack (bank + GSTR + invoice + books). Stage 4 crops/OCR still open.

---

## How a gate works

Each stage has:

- **Goal** — the one thing this stage exists to prove
- **Objectives** — the work that must be true, not a task list
- **Success gate** — a test you can run on a Windows PC. All items must pass.
- **Not this stage** — work that belongs later. Doing it early is a fail.

No installer polish, no extra parsers, no billing, no recon, until their stage.

---

## Stage map

| Stage | Name | Proves |
|---|---|---|
| 1 | Windows shell | A local Windows app exists |
| 2 | Dump and router | Mixed files land in a client folder and get a type |
| 3 | Bank pack | A messy bank PDF becomes a checked Excel, offline |
| 4 | Trust | A CA can see the source crop; scans work |
| 5 | Invoices | Bills become a flagged purchase register |
| 6 | GST portal files | Ugly 2B/1/3B JSON becomes a readable sheet |
| 7 | Books exports | Tally/Zoho exports become registers without opening Tally |
| 8 | Master grid | 2B vs books (and a light bank assist) in one pack |
| 9 | License | Paid plans work without sending documents to the cloud |
| 10 | Firm-ready | A real firm can live on it (installer, wipe, second PC folder) |

Stages 8–10 stay closed until Stage 7 passes. Stages after 10 (ITC engine, GSTR-9) are not in this file.

---

## Stage 1 — Windows shell

**Goal:** prove we can ship a local Windows window, not a website.

**Objectives**

- Open a desktop window on Windows 10/11 with no Docker and no browser bookmark
- Create one firm (name) and one client; persist them in SQLite under `%LOCALAPPDATA%\CAUnpacker\`
- Close the app, open it again, the client is still there
- Client documents have nowhere to go yet — that is fine

**Success gate**

- [ ] `python -m desktop` (or the agreed dev entry) opens a native window
- [ ] A client can be created from that window
- [ ] Restarting the app still shows that client
- [ ] Nothing in this stage requires internet
- [ ] No Postgres, Redis, or Docker is involved

**Not this stage:** file drop, parsers, Excel, installer, login.

---

## Stage 2 — Dump and router

**Goal:** prove a CA can dump a messy folder and the app sorts it without them labelling files.

**Objectives**

- A client has periods (e.g. Jul)
- Drag-drop from Explorer and “Add folder” copy files into the library (never parse in-place)
- Each file gets a kind: bank, invoice, gstr_1, gstr_2b, gstr_3b, tally, zoho, or unknown
- Unknown files sit in Needs review; the CA can override kind and re-run
- The window stays usable while files are classified

**Success gate**

- [ ] Drop a mixed folder (PDF + image + JSON + zip/txt) onto one period
- [ ] Every file appears with a kind or as unknown
- [ ] An unknown file can be forced to a kind
- [ ] Originals exist under the library path, not only as a temp drop
- [ ] Turning the PC’s network off does not change this

**Not this stage:** extracting amounts, Excel output, OCR.

---

## Stage 3 — Bank pack (first real product)

**Goal:** prove the idea-doc demo. This is the first stage a CA would pay attention to.

**Objectives**

- Digital (not scanned) bank PDFs for HDFC, ICICI, and SBI go through the bank parser
- Rows are stored in the canonical bank shape
- Stated closing balance is checked against a running total
- `Bank_Statement_Cleaned.xlsx` is written to the pack folder
- “Open in Excel” works
- Source column has at least a page number

**Success gate**

- [ ] On a Windows laptop with Wi-Fi off: drop one real messy digital bank PDF
- [ ] Within about two minutes, an Excel exists with transactions
- [ ] The Excel has a balance-check sheet or cover that says match or mismatch
- [ ] A CA would recognise the rows as that statement (spot-check 10 lines)
- [ ] Digital-PDF row accept rate on the three banks is at least 95% before we call this done
- [ ] Scanned statements are allowed to fail. Do not block this gate on OCR.

**Not this stage:** invoice parser, Tesseract, click-to-crop, other banks, installer branding.

---

## Stage 4 — Trust (crops + scans)

**Goal:** prove a CA can verify a number without trusting the AI.

**Objectives**

- PDF pages can be rendered to images on disk
- Extracted bank rows (and later other rows) carry a page + bbox
- Click a number in the app → cropped snippet from the original
- Password-protected PDFs prompt once; password is not saved
- Scanned bank PDFs go through bundled Tesseract and the same bank mapper
- Scan quality may be worse than digital; flags and Needs review are acceptable

**Success gate**

- [ ] Click a debit or credit from a digital statement and see that number on the page crop
- [ ] A password PDF asks for a password and then parses (or fails with a clear error)
- [ ] At least one scanned/photographed statement produces rows, even if some are flagged
- [ ] Tesseract runs from the app bundle or a documented local path — the user did not install a cloud OCR
- [ ] No page image is sent off the machine

**Not this stage:** invoices, GSTR, Tally, billing.

---

## Stage 5 — Invoice parser

**Goal:** prove a folder of purchase bills becomes a GST-aware register.

**Objectives**

- JPEG, PNG, and PDF tax invoices produce purchase rows
- GSTIN checksum, HSN length (4/6/8), and invoice arithmetic are flagged, never silently fixed
- `Purchase_Register_Extracted.xlsx` is in the pack
- Field-level crops work the same way as bank crops
- Printed GST invoices only; handwritten bills may be unknown

**Success gate**

- [ ] Drop a folder of printed purchase bills (mix of PDF and images)
- [ ] A purchase register Excel exists with supplier, GSTIN, invoice no, date, tax, total
- [ ] A known-bad GSTIN is flagged
- [ ] A known HSN that is not 4, 6, or 8 digits is flagged
- [ ] Click a GSTIN or amount and see the crop
- [ ] Handwritten or unreadable bills land in Needs review instead of fake rows

**Not this stage:** GSTR JSON, Tally, recon against 2B.

---

## Stage 6 — GST portal files

**Goal:** prove ugly portal downloads become a sheet a CA will actually open.

**Objectives**

- Official GSTR-1, GSTR-2B, and GSTR-3B **JSON** parse into typed rows
- `GSTR_2B_Formatted.xlsx` (and the 1 / 3B equivalents that apply) are in the pack
- Recon columns may exist but stay empty
- Portal **PDFs** are only in scope if JSON is not enough after JSON works

**Success gate**

- [ ] Drop a real GSTR-2B JSON; get a readable B2B sheet in one click
- [ ] GSTR-1 JSON produces a usable outward register
- [ ] GSTR-3B JSON produces a usable summary sheet
- [ ] No GST portal login or scraping is involved
- [ ] Still fully offline

**Not this stage:** matching 2B to books, Tally, e-filing.

---

## Stage 7 — Tally / Zoho reader

**Goal:** prove books can enter the same pipeline without opening Tally or Zoho.

**Objectives**

- Zoho Books CSV/XLS maps into the same purchase/sales shape as invoices
- Tally XML / zip / daybook export produces purchase and sales registers
- Live Tally ODBC and a running TallyPrime instance stay out
- Output sits in `Purchase_Register_Extracted.xlsx` (and a sales sheet/file as designed)

**Success gate**

- [ ] A Zoho export becomes a register without opening Zoho
- [ ] A Tally export becomes purchase + sales registers without opening Tally
- [ ] Rows use the same canonical fields as invoice rows (so Stage 8 can join them)
- [ ] A garbage or unknown backup is unknown / Needs review, not a crash

**Not this stage:** recon, GSTR-9, live Tally write-back.

---

## Stage 8 — Master reconciliation grid

**Goal:** prove the four inputs can meet each other.

**Objectives**

- One period that has books + 2B (+ optional bank) writes `Master_Reconciliation_Grid.xlsx`
- Match key: GSTIN + invoice number + date + amount within ₹1
- In-app tray: matched / unmatched / amount-mismatch
- Bank vs invoice totals are an assist only, never treated as certain

**Success gate**

- [ ] One dump that includes bills or Tally + 2B produces a master grid
- [ ] A known matching invoice appears as matched
- [ ] A known 2B-only invoice appears unmatched
- [ ] A known amount clash appears as amount-mismatch
- [ ] A CA can open the grid in Excel and continue work from there

**Not this stage:** full ITC product, GSTR-9, billing.

---

## Stage 9 — License and plans

**Goal:** prove we can charge without becoming a cloud document store.

**Objectives**

- Starter ₹999 / 100 files per month vs Pro ₹2,500 unlimited, all four modules
- Suite ₹6,000 is visible and gated as coming
- License or Razorpay check may use the internet
- Client files still never upload
- Starter hits a hard stop at 100 files with a clear message

**Success gate**

- [ ] A test Starter license blocks the 101st file
- [ ] A test Pro license does not
- [ ] Wi-Fi off: already-imported files still open; new license activation may fail honestly
- [ ] Packet capture / code review: no PDF, JSON, or row payload leaves the PC

**Not this stage:** multi-PC sync, code signing (unless needed to collect money).

---

## Stage 10 — Firm-ready

**Goal:** prove a practising firm can keep using it after the first week of the month.

**Objectives**

- One signed (or at least single-file) installer: engine + UI + Tesseract, no Python on PATH
- Delete client wipes DB rows **and** files on disk
- Warn if the library path is a OneDrive/Desktop sync folder
- Optional shared-folder library with a lock file for a second PC
- Duplicate-period protection
- Accuracy / override notes good enough to add the next bank profile from a CA sample

**Success gate**

- [ ] A CA who is not the developer installs from the `.exe` and completes a Stage 3-style bank dump
- [ ] Delete client leaves no leftovers under the library path for that client
- [ ] SmartScreen/Defender story is known (signed, or a written workaround for the first firms)
- [ ] A second machine can open a shared library folder without corrupting SQLite (or we document “one writer at a time” and the lock works)

**Not this stage:** ITC engine, GSTR-9 auto-filler, mobile, white-label.

---

## Closed until a later file

These are not stages in this build. Do not open them because a CA asked once.

- ITC reconciliation as its own product
- GSTR-9 auto-filler
- Live GST portal login
- Live Tally company access
- Cloud OCR
- Mobile app

---

## Gate log

Record the date a stage passed. Empty means not passed. Do not start the next stage with an empty box above it.

| Stage | Passed on | Notes |
|---|---|---|
| 1 Windows shell | 2026-08-13 | Client “Benny” created and stored locally |
| 2 Dump and router | 2026-08-13 | Mixed test-dump labelled correctly; jpg + docx left as Unknown |
| 3 Bank pack | | |
| 4 Trust | | |
| 5 Invoices | | |
| 6 GST portal files | | |
| 7 Tally / Zoho | | |
| 8 Master grid | | |
| 9 License | | |
| 10 Firm-ready | | |
