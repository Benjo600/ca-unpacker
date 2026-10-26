# CA Unpacker — Master Plan

**Single source of truth for direction, progress, bugs, and features.**
Last consolidated: 2026-09-20. Verified against the working tree on that date.

This document merges the former planning and build files (see [Source documents](#source-documents)).
When a detail conflicts, this file wins; when a plan changes, update this file first.

---

## 1. What the product is

CA Unpacker is a **Windows-only, offline-first** desktop app that turns a CA client's messy
document dump into GST-ready, source-linked Excel packs. Every parser, check, and Excel write
happens on the CA's own PC under `%LOCALAPPDATA%\CAUnpacker\`. Client documents never leave the
machine; only license/auth may use the internet.

It is not an AI accountant, a bank PDF converter, or another GST recon tool. Its job is the
**preparation layer** between a client's chaos and the CA's real work:

```text
client dump → identify → organize → extract → normalize → validate
→ cross-check → find gaps → flag exceptions → CA-ready working pack
```

**Positioning:** "CA Unpacker converts messy client documents into structured, review-ready
accounting working papers."

**Non-negotiable rules**

1. **Local-first / confidential.** No client document, page image, or row payload is ever uploaded.
2. **Contextual routing.** Bank PDF, invoice image, GSTR JSON, and Tally export each get a specialist parser. No one generic model.
3. **Show your work.** Every extracted value links back to file + page + region (source crop).
4. **Validate, don't silently fix.** GSTIN checksum, HSN length, invoice math, bank balance — flag them, never edit source data.
5. **Never silently ignore.** Every input ends as `processed`, `needs_review`, `failed`, or `unclassified`. No clean success when a file was skipped.
6. **Software finds evidence; the CA makes the accounting judgment.** Never assert "₹50,000 credit = income."
7. **Extraction honesty (2026-09-15 contract):** every extraction is either self-verified or explicitly flagged. Silent wrong output is a zero-tolerance defect.

---

## 2. Status snapshot (2026-09-20)

| Item | State |
|---|---|
| Stages 1–10 (fixture gates) | **Passed** (see [gate log](#4-stage-gate-log)) |
| Python test suite | **266 passed**, 8 subtests, ~59s (verified 2026-09-20) |
| Node UI tests | `status-summary`, `recon-summary` — plain Node scripts |
| Current git branch | `docs/document-processing-plans`, 3 commits ahead of `main` |
| `main` last moved | 2026-09-11 |
| Uncommitted content changes | ~10 files (mostly `apps/web` SPA + `start-log.txt`); rest of the 148 “modified” entries are CRLF line-ending churn |
| Installer | `build_installer.bat` → Inno Setup 6 → `dist\CAUnpacker-Setup.exe` (Tesseract bundled) |
| Cloud control plane | Supabase project `ovcddryhcqgzmafutrha`; 5 Edge Functions deployed; signup/login/desktop auth live |
| Biggest open risk | Parser accuracy + silent-failure hardening is planned but **not started** |

**One-line read:** the product works end-to-end on fixtures and demo data, has a working cloud
auth/usage layer, and a redesigned desktop shell — but real-world parser hardening, release
automation, and two unmerged workstreams are still open.

---

## 3. Stage map and phases

### Stage map (what each stage proves)

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

### Phase roadmap (BUILD-PLAN, mapped to stages)

| Phase | Scope | Stage equivalent | Status |
|---|---|---|---|
| 0 | Windows skeleton, monorepo, SQLite library | 1 | Done |
| 1 | Clients + periods, dump + router, classifier override | 2 | Done |
| 2 | Bank parser + first Excel | 3 | Done |
| 3 | Source crops + scan/OCR + password PDFs | 4 | Done |
| 4 | Invoice parser + GST flags | 5 | Done |
| 5 | GSTR-1/2B/3B JSON extractor | 6 | Done |
| 6 | Tally / Zoho reader | 7 | Done |
| 7 | Master reconciliation grid | 8 | Done (with concerns) |
| 8 | Billing, quotas, license | 9 | Done on fixtures |
| 9 | Hardening for real firms | 10 | Done on fixtures |
| 10+ | Completeness detection, capital gains, bulk queue, ITC, GSTR-9 | — | Not started |

**Rule:** do not open a later stage because a CA asked once. ITC recon, GSTR-9, live GST
login, live Tally, cloud OCR, and mobile stay closed until their own file says otherwise.

---

## 4. Stage gate log

Recorded passes. Empty = not passed. A half-working stage is not a pass.

| Stage | Passed on | Notes |
|---|---|---|
| 1 Windows shell | 2026-08-13 | Client "Benny" created and stored locally |
| 2 Dump and router | 2026-08-13 | Mixed test-dump labelled correctly; jpg + docx left as Unknown |
| 3 Bank pack | 2026-08-15 | HDFC/ICICI/SBI simple+complex+long all match; Excel Balance Check + Source #p; 37 tests OK. Scans still out. |
| 4 Trust | 2026-08-15 | Click-to-crop + in-memory password + local Tesseract at `%LOCALAPPDATA%\CAUnpacker\tesseract`. Scan fixture produces rows. 57 tests OK. |
| 5 Invoices | 2026-08-15 | Digital + rendered PNG invoices; GSTIN/HSN/math flags; 1x1 photo stays unknown; field crops. 75 tests OK. |
| 6 GST portal files | 2026-08-15 | 2B B2B + 1 outward + 3B summary Excel; Match/Books ref empty; offline JSON only. 92 tests OK. |
| 7 Tally / Zoho | 2026-08-15 | Canonical invoice fields; purchase+sales Excels; garbage zip safe. 110 tests OK. |
| 8 Master grid | 2026-08-30 | ACME+2B matched; extra 2B portal_only; amount off ₹50 mismatch; GSTR-only still no master. (See concerns below.) |
| 9 License | 2026-08-30 | STARTER-TEST blocks 101st; PRO-TEST unlimited; offline activate fails honestly; payload is product+key hash only. |
| 10 Firm-ready | 2026-08-30 | Delete client wipes disk; OneDrive/Desktop warn; `library.lock` one-writer; SMARTSCREEN.txt; Inno+Tesseract bundle. |

**Standing caution:** all ten gates were proven on **synthetic fixtures**. Real anonymised CA
corpus has not yet been scored, so treat accuracy claims as unproven until §9 is done.

---

## 5. Workstreams and their real status

Audited 2026-09-20 from plans, SDD ledgers, git history, and file presence.

| # | Workstream (date) | Delivers | Status |
|---|---|---|---|
| 1 | **Release 0 Trust Foundation** (08-17) | Reproducible tests, no silent parser success, deterministic packaging | Tasks 1–5 **done**; Tasks 6–7 **not started** |
| 2 | **Stage 8 Master Reconciliation** (08-30) | `Master_Reconciliation_Grid.xlsx` + tray | **Done with concerns** |
| 3 | **Admin Dashboard & Auth – Phase 1** (09-03) | Supabase signup/login, desktop session, operator dashboard, quotas | Tasks 1–11 **done**; Task 12 manual E2E **deferred** |
| 4 | **Founder & Firm Administration** (09-11) | Two founder logins, firm/user/device/payment admin, audit log | **Implemented on unmerged branch**; deploy/smoke not done |
| 5 | **Release Control Plane** (09-11) | Publish/withdraw Windows releases; `latest-release` endpoint | **Not started** |
| 6 | **Desktop Self-Update** (09-11) | Check → download → verify (SHA-256) → install → restart | **Not started** (depends on #5) |
| 7 | **Backend Document Processing Fixes** (09-15) | Bank/invoice/GSTR/Tally/Zoho correctness + honest failure across 6 phases | **Not started** |
| 8 | **Top-Class PDF Parser** (09-15) | Canonical PDF model, coordinate space, table cascade, per-page OCR, scorecard | **Not started** |
| 9 | **Document Processing Index** (09-15) | Governing contract + order for #7/#8 | Informational |

### Details worth keeping

**#1 Release 0.** Done: restored tracked tests + generators, `requirements-dev.txt`, desktop
import test, intake preflight (≤400 files, rejects `.xls`), backed-up SQLite migrations,
`apps/engine/outcomes.py` per-file outcomes, durable intake manifest, parser failure handling,
period-scoped summaries, warning badges in UI. Not done: locked release dependencies
(`requirements.in` / `requirements.lock.txt`), release-mode Tesseract enforcement, third-party
license inventory (`THIRD_PARTY_LICENSES.md`), CI workflow, release gate script.

**#2 Stage 8 concerns.** (a) Invoice date extractor bug — values like `ACME/26-27/0142` produce bad
dates, so the matcher now treats unparseable dates as agreeing on GSTIN+invoice+amount; two bills
with the same number in different months could wrongly pair. (b) 2B `match_status` is filled
in-memory only; stored `ExtractedRow` payloads stay empty. (c) The tray renders even when all counts
are 0; row-click crop was left out; no live pywebview click-through test.

**#3 Admin/Auth.** Deployed to Supabase `ovcddryhcqgzmafutrha` with `verify_jwt: true`. Functions:
`check-quota`, `record-usage`, `heartbeat`, `admin-list-orgs`, `admin-update-plan`. Admin seed is
placeholder only — real founder emails must be inserted manually. `admin-list-orgs` lacks usage
history/device detail, so User Detail is partial. Docker was unavailable, so local `supabase start`
and live function smoke tests were skipped. Task 12 (manual end-to-end on the real project) is the
remaining gate.

**#4 Founder admin.** 18 commits on `codex/founder-admin-updates` (schema, founder authorization,
audit, dashboard). Not an ancestor of `main`; `supabase/migrations/20260911100000_founder_firm_admin.sql`
does not exist on `main`. Task 9 (apply migrations, upsert the two founder emails, deploy
`admin-get-org` / `admin-update-org` / `admin-list-audit` / `sync-firm`, smoke-test both founders)
has no evidence.

**#7/#8 Document processing.** The 2026-09-15 set is documentation-only so far (commit `249c864`).
Prerequisite per the index: a **real anonymised corpus** before any accuracy claim. The PDF plan also
records that `onnxruntime` is missing and RapidOCR is dead (`pdf_extract` / `ocr.py`).

---

## 6. Open bugs and defects

### 6.1 Owner bug list — `bugs-to-fix.md`

| # | Bug | Status |
|---|---|---|
| 1 | Bank statement → Excel parsing (wrapped/page-break rows, running-balance repair) | **Done** — locked at `c517216` |
| 2 | "Restart" clears only the data, without restarting the app | Open |
| 3 | Persist firm / folder / client names so re-opening does not ask again | Open |
| 4 | Improve scanned PDFs and alternate bank layouts/formats | Open |
| 5 | Modernize UI: results dumped all at once; present progressively | Open (Practice Desk shell is in progress) |
| 6 | Collect and save a separate profile per client | Open |
| 7 | More polished, reviewable citations (NotebookLM-style) | Open |
| 8 | In-app file preview pane (like the Codex app) | Open |

### 6.2 Audit findings — `AUDIT-FINDINGS-2026-08-16.md`

Addressed by Release 0 (do not re-open):

- P0 launch blocker: `on_zone_drop` function with a comments-only body → fixed (executable no-op).
- P0 false success: non-bank parsers could fail while job became `done` → fixed via per-file outcomes.
- P1 `.xls` unreliable → removed from picker/suffixes with guidance to export `.xlsx`/`.csv`.
- P1 folder import silently stopped at 400 → now both accepts new files and fails visibly when an intake exceeds 400.
- P1 tests not reproducible → suite and generators committed; `requirements-dev.txt` added.

Still open:

| Severity | Finding |
|---|---|
| P1 | **Tesseract bundling optional in release.** Build should fail if `tesseract.exe` / `tessdata\eng.traineddata` are missing; assert assets in installer output. |
| P1 | **Dependencies not locked.** `>=` ranges can drift; keep a locked release set (`requirements.in` + `requirements.lock.txt`). |
| P1 | **WebView2 not verified on clean Windows.** Test Windows 10/11 fresh VM; document or bootstrap the runtime. |
| P1 | **No CI.** Need dependency install → compile check → unit tests → PyInstaller build → launch smoke. |
| P1 | **No clean-machine smoke test** of the real installer (full checklist in the audit file). |
| P2 | **Invoice heuristics fragile.** Ambiguous GSTIN/date/total picks; prefer explicit labels, flag ambiguity, widen real-invoice testing, keep crops. |
| P2 | **Tally parsing intentionally simplistic.** Multiple ledger allocations/taxes/inventory not fully handled; mark unsupported structures for review. |
| P2 | **GSTR covers selected schemas only.** Maintain fixtures by form/version; fail visibly on unknown structures; never emit a partial Excel silently. |

### 6.3 Design open items — `DESIGN.md`

1. **Tie animation replays on inspector re-render** — `tie-sweep` / `tie-chip` fire on unrelated updates instead of only when the tied line changes.
2. **Truncation at ≤1360px** — the longest intake filename and two reconcile supplier names ellipsize by 8–13px (names only; figures/IDs/status never clip).

### 6.4 Prototype known non-blocking edge cases — `PROTOTYPE-BUILD-LOG-2026-08-17-18.md`

- Narrow source-disappearance race can show `copy_failed` instead of `source_missing`.
- Nested bank-password metadata can omit the Unlock action (still never reports false success).
- Parser warnings are persisted but not all appear in the file row or affect completion tone.
- Concurrent first access to the global engine/session factory has a small publication race outside sequential desktop startup.
- Files >100 MB show a generic copy failure instead of a specific size-limit message.
- A migrated historical job can stay `done` while its migrated file starts `unclassified` until reprocessed.

---

## 7. Features to add (backlog)

Order roughly by cost/value. "Gate" means a stage/phase gate already defines it.

### Near term (reliability first)

- **Release 0 tasks 6–7:** locked deps, release-mode Tesseract gate, license inventory, CI, release gate script.
- **Finish Release Control Plane + Desktop Self-Update:** draft → publish → withdraw releases; signed update check with HTTPS + hostname allowlist + SHA-256 + atomic rename; mandatory releases block new processing. Authenticode code-signing when a certificate exists.
- **Merge `codex/founder-admin-updates`** and complete Task 9 deployment/smoke.
- **Admin/Auth Task 12:** manual end-to-end on the live Supabase + Netlify deployment; real founder seed emails; richer User Detail (usage history, devices); license-key UI and device-limit enforcement (Phase 2); CSV export; email notifications.
- **Parser hardening (#7) and PDF foundation (#8)** in the index's recommended first cut: PDF Workstreams 1–3 plus backend tasks 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 5.1, 5.2, 4.1.
- Fix Stage 8 concerns: date extraction, persisted match_status, tray empty-state, row-click crop.

### Owner experience (bugs list)

- One-click **Restart that clears data only** (no app restart).
- Persist firm / folder / client names; **per-client profiles** (type, industry, GST registered, banks, books, broker).
- Progressive **results workflow** instead of dumping everything at once (Practice Desk).
- **In-app file preview pane**; **NotebookLM-style citations** with better source review.
- Keep adding **bank profiles** from real samples (Axis, Kotak, Yes Bank, …); see `docs/ADDING-A-BANK.md`.

### Product depth (post-pilot)

- **Completeness / gap detection:** known accounts × missing months (definite), 2B entries with no invoice document (probable), unusual activity (informational). Avoid false alarms.
- **Bank ↔ invoice reconciliation scoring:** exact amount +50, date ≤7 days +20, name similarity +20, correct direction +10; 90–100 auto-match, 70–89 likely, 40–69 possible, <40 no match. Later, one-to-many / many-to-one.
- **Cross-document inconsistency flags:** books vs bank vs GSTR-1 / GSTR-2B. "Possible sale missing from books", "possible GST reporting gap", "supporting document may be missing."
- **Automatic client query list** ("documents/clarifications required").
- **Capital gains parsers:** Zerodha, Groww, MF CAS, broker tax P&L → asset, dates, values, cost, gain/loss, likely STCG/LTCG, always reviewable.
- **Firm-scale job queue:** per-client/period status; fast parsers multi-worker, OCR 2–4 workers, Excel limited; **parse once → store normalized → generate reports from DB** (never reparse).
- **Optional LLM fallback layer** only for bizarre/unseen documents, after human review — never in v1.

### Conditional / evaluated later

- **PaddleOCR** (Apache-2.0) — only if accuracy, packaging, and model-weight licensing all pass.
- **ITC reconciliation product** (Tier 1 upsell), **GSTR-9 auto-filler** (Tier 2), e-way bill / 26AS — only if CAs ask twice.

### Explicitly out of scope for v1

Legal contracts, property papers, ITR PDFs, 26AS, salary slips; live GST portal login/scraping;
live Tally ODBC; mobile app; multi-firm white-label; any cloud OCR/LLM processing of client files;
payment-gateway integration; staged rollouts; per-user targeting; delta patches; automatic rollback.

### Pricing (design now, implement behind the paywall)

| Plan | Price | Behaviour |
|---|---|---|
| Starter | ₹999/mo | 100 files/month, bank + invoice only |
| Pro | ₹2,500/mo | unlimited files, all four parsers + validation |
| Suite | ₹6,000/mo | Pro + recon + future GSTR-9 (not built) — visible, gated as "coming" |

Phase 1–6: no paywall, "Pro" features hard-on. Phase 8: Razorpay + Starter quota.
Plan limits in the cloud: starter 100 / ₹999, pro unlimited / ₹2,500, suspended 0.

---

## 8. Architecture and repo map

### Stack

| Layer | Choice |
|---|---|
| Shell | Windows desktop window via **pywebview (WebView2)** |
| Desktop UI | Vanilla HTML/CSS/JS in `apps/ui/` (Practice Desk design system) |
| Engine | Python 3.12, packaged with PyInstaller |
| Engine bridge | `apps/desktop/app.py` `DesktopApi` JS bridge; local only |
| DB | SQLite + SQLAlchemy 2 + numbered migrations |
| Files | `%LOCALAPPDATA%\CAUnpacker\` (`app.db`, `files\`, `packs\`) |
| Native PDF tables | pdfplumber primary; Docling tables; pypdfium2 rendering |
| OCR | Bundled local Tesseract (`eng.traineddata`); RapidOCR currently dead |
| Excel | openpyxl |
| Installer | Inno Setup 6; bundles engine + UI + Tesseract |
| Cloud | Supabase (Auth + Postgres + Edge Functions) + Netlify (web SPA) |
| Web SPA | React 19 + Vite + TypeScript (`apps/web/`, signup/login/admin) |
| Tests | pytest (Python), plain Node scripts (UI JS) |

### Layout

```text
apps/engine/     parsers/ (bank/, invoice, gstr, tally, zoho), validators/, pack/,
                 pipeline, classifier, recon, outcomes, migrations, auth, license, wipe, preview
apps/desktop/    app.py (JS bridge), protocol.py (caunpacker://), frozen_entry.py
apps/ui/         index/shell/auth/redesign .html + .css + .js (Practice Desk)
apps/web/        React SPA (signup/login/admin) — not bundled in the app
supabase/        migrations/ + functions/ (check-quota, record-usage, heartbeat,
                 admin-list-orgs, admin-update-plan)
designs/         ca-unpacker-landing/ static landing page
docs/            ADDING-A-BANK.md, tesseract.md, superpowers/plans, superpowers/specs
installer/       Inno Setup script, FIRST-RUN.txt, SMARTSCREEN.txt
test-dump/       gitignored generated fixtures (recreated by generators)
```

### Output packs (always same names, always a Source column)

| File | When | Sheets |
|---|---|---|
| `Bank_Statement_Cleaned.xlsx` | bank files present | Transactions, Balance Check |
| `Purchase_Register_Extracted.xlsx` | invoices and/or Tally purchases | Register, Flags |
| `GSTR_2B_Formatted.xlsx` | 2B present | B2B, Flags |
| `Master_Reconciliation_Grid.xlsx` | Stage 8 | 2B vs books vs bank |

Source format: `filename.pdf#p12@x,y,w,h`. Excel is the takeaway; trust is built in the app via
click-to-crop.

### Canonical row shapes (do not invent a fifth)

- **Bank line:** date, description, cheque_ref, debit, credit, balance, account_name, account_number, ifsc, source_page, source_bbox, raw_text
- **Invoice / purchase:** supplier_name, supplier_gstin, invoice_number, invoice_date, taxable_value, cgst, sgst, igst, cess, invoice_value, hsn, place_of_supply, document_type, source
- **GSTR-2B / 1:** gstin, trade_name, invoice_number, invoice_date, invoice_value, taxable, igst, cgst, sgst, cess, itc_availability
- **Tally / Zoho:** voucher_type, voucher_number, date, party_name, gstin, taxable, tax_breakup, ledger, amount, source

### Data model (SQLite)

`Firm`, `User` (unused in v1), `Client`, `Period`, `Job` (queued|routing|parsing|validating|packing|done|failed),
`File` (detected_kind + outcome + reason + rows + parser provenance), `ExtractedRow` (payload_json + source + flags),
`DataPack` (bank/purchase/gstr2b/master xlsx keys).

Per-file outcomes: `processed` | `needs_review` | `failed` | `unclassified`.
Job states: `done` | `done_with_warnings` | `failed`.

---

## 9. Commands

Run Python from the repo root.

```powershell
start.bat                                             # create .venv, install requirements, run app
.venv\Scripts\python.exe -m apps.desktop              # run app directly
.venv\Scripts\python.exe -m pytest apps -q            # full Python suite (266 tests)
.venv\Scripts\python.exe -m pytest apps/engine/tests/test_stage3_bank.py -q
node apps/ui/tests/status-summary.test.js             # UI JS tests (plain node scripts)
cd apps/web; npm install; npm run build               # web SPA (tsc -b && vite build)
build_installer.bat                                   # PyInstaller + Inno Setup 6 -> dist\CAUnpacker-Setup.exe
```

**Gotchas**

- **Never freeze `apps/desktop/__main__.py`.** Entry is `apps/desktop/frozen_entry.py`.
- Runtime data lives in `%LOCALAPPDATA%\CAUnpacker\`, not the repo. `library.lock` enforces one writer.
- `apps/config.json` holds the tracked production Supabase URL/anon key; `.env` overrides for `start.bat`.
- `pyrightconfig.json` covers `apps/` and `scratch/` only; pyright is not in `.venv` by default.
- Adding a bank format = edit `apps/engine/parsers/bank/profiles.py` (see `docs/ADDING-A-BANK.md`).

---

## 10. Risks and open decisions

| Risk | Mitigation |
|---|---|
| Every bank PDF is a different layout | Bank **profiles**, not one mega-parser; add a profile per real sample |
| CAs refuse to trust AI numbers | Source crop is core, not polish; never silent-fix |
| OCR on bad phone photos | Accept "needs review"; no fake 95% on garbage scans |
| Scope explosion (recon, GSTR-9, live Tally) | Stage gates; keep closed list closed |
| Silent wrong output | 2026-09-15 honesty contract + per-file outcomes; harden parsers |
| Password PDFs / huge statements | Job queue + password prompt + page cap with a clear error |
| Legal: storing client financials | Files never leave the PC; Delete-client wipes disk; say it on first run |
| "Just install this .exe" friction | One installer; bundle Tesseract; no Docker; no Python on PATH |
| Windows Defender flags PyInstaller | Code-sign before paid rollout; submit to Microsoft if needed |
| OneDrive / file-in-use | Default library is LocalAppData; detect sync folders and warn |
| Two articles, two PCs | Out of v1; shared-folder library with lock is Stage 10 |
| Dependency/version drift | Lock release deps; re-run license inventory on every upgrade |
| Three.js-class maintenance debt (unmerged branches) | Merge or delete `codex/founder-admin-updates`, `new-and-updated-ui-design`, `pdf-parsing-fix` deliberately |

**Open decisions with current defaults**

| Decision | Default |
|---|---|
| Platform | Windows 10/11 desktop, local processing |
| Shell | pywebview (WebView2) + local UI + Python engine |
| First banks | HDFC, ICICI, SBI (then Axis, Kotak) |
| First auth | None locally; cloud account for quota/license only |
| OCR | Bundled Tesseract; PaddleOCR conditional; no cloud OCR |
| Recon in v1 | No — Stage 8 only, deeper recon later |
| Billing | Razorpay; files stay local |
| Admin mutation path | Edge Function proxy with service role (preferred over a DB admin role) |
| PDF architecture (2026-09-15) | Hybrid (pdfplumber + Docling) rather than Docling-centric |
| Determinism vs new IR (2026-09-15) | Extend existing dataclasses rather than a new intermediate representation |

---

## 11. Definition of done for "real firm ready"

The product is externally shippable when **all** of the following hold:

1. The exact release installer installs on a clean Windows machine (no Python/Tesseract/dev tools) and completes Stages 1–7 with representative files.
2. No parser failure is hidden: every recognised file that failed, needs review, or is unclassified is visible in the UI, and the job never reports clean success.
3. Locked dependencies, license inventory, and a CI gate (compile → tests → build → smoke) run on every release.
4. Anonymised real-bank/invoice/GSTR corpus is scored; digital-bank row accept rate ≥95%.
5. Delete-client wipes DB rows **and** disk files; a second machine on a shared library cannot corrupt SQLite.
6. SmartScreen story is known (signed, or a written workaround for the first firms).

---

## 12. What to do next (recommended order)

1. **Decide the branch tangle.** Merge or retire `codex/founder-admin-updates`, `new-and-updated-ui-design`, `pdf-parsing-fix`; commit the pending `apps/web` changes.
2. **Finish Release 0 (tasks 6–7):** lock dependencies, make release builds fail without Tesseract, add license inventory + CI.
3. **Get a real anonymised corpus** (one client dump, uncleaned). Score it. This unblocks all accuracy work.
4. **Do the index's first cut:** PDF Workstreams 1–3 plus backend tasks 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 5.1, 5.2, 4.1.
5. **Fix the Stage 8 concerns** while the parser work is fresh.
6. **Deploy Founder Admin (Task 9)** and **Admin/Auth Task 12** manual E2E.
7. **Then** pick one owner-experience bug (restart, persistence, per-client profiles, preview pane) to ship next.
8. **Only after pilot evidence:** release control plane + self-update, then completeness detection, capital gains, bulk queue, billing enforcement.

Measure success by **staff minutes saved per client**, not feature count.

---

## Source documents

This master file supersedes the following. Keep them for detail; update this file when they change.

| Document | Role |
|---|---|
| `BUILD-PLAN.md` | Whole-product spec: product, platform, stack, pipeline, parsers, phases, risks |
| `STAGES.md` | Build-order gate list + gate log |
| `PRODUCT-VISION-CHAT-SUMMARY-2026-08-17.md` | Vision: gap detection, scoring, cross-document checks, capital gains, privacy posture |
| `PROTOTYPE-BUILD-LOG-2026-08-17-18.md` | Release 0 prototype build, outcomes engine, edge cases |
| `AUDIT-FINDINGS-2026-08-16.md` | Code-level audit: P0/P1/P2 findings and clean-machine checklist |
| `bugs-to-fix.md` | Owner bug list (items 1–8) |
| `WORK-DONE-2026-09-04.md` | Session log: bank wrap/page-break fix |
| `PRODUCT.md` | Product schema: users, purpose, positioning, brand, principles |
| `DESIGN.md` | Practice Desk desktop UI design system + open items |
| `designs/ca-unpacker-landing/DESIGN.md` | Landing page tokens and voice rules |
| `docs/tesseract.md` | Local OCR discovery order |
| `docs/ADDING-A-BANK.md` | How to add a bank profile from a real sample |
| `THIRD-PARTY-LICENSING-NOTES.md` | Open-source/license compliance checklist |
| `docs/superpowers/specs/*` | Full product design, admin/auth design, founder-admin/billing/update design |
| `docs/superpowers/plans/*` | Release 0, Stage 8, admin auth phase 1, desktop update, founder admin, release control plane, backend parser fixes, PDF parser, processing index |
| `README.md` / `AGENTS.md` | Install/run instructions and repo conventions |

**Maintenance rule:** one direction doc, this one. New findings get a row here first, detail
elsewhere second.
