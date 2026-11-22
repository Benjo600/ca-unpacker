# Launch-readiness findings — real-user pass (22 Nov 2026)

> **Status 22 Nov, later the same day — first fix batch shipped (uncommitted).**
> Fixed and verified in the running app:
>
> - **#1 duplicate import.** Files whose bytes are already in the period are now
>   skipped at intake, never stored twice. The import summary names them
>   ("7 files were already in this period and were not imported again: …").
>   Re-dropping the whole `07-mixed-client-month` folder left the pack at
>   **16 rows**, not 32, and did not touch the plan quota. New migration v7
>   (`jobs.intake_duplicate_names_json`) records what was skipped; the job
>   payload carries `skipped_duplicates`. Tests: `test_ingestion_integrity.py`.
> - **#3 reconciliation landing.** The Control Centre now opens scoped to the
>   newest period that has a run instead of the lifetime "All clients / all
>   years" aggregate. Filters stay one click away.
> - **#4 client delete** uses the app's own dialog (`Delete <client>?` with a
>   red Delete client / Keep client), matching the wipe dialog.
> - **#6 help on every screen.** "Help / How to use" now opens a five-step
>   checklist modal on any pane (and hides the inline step card while open).
> - **#8 period names.** Only a real month + 4-digit year is accepted and it is
>   normalised (`october-2026` → `Oct 2026`), so one month cannot exist twice.
>   Periods can also be **deleted** now (client and other months untouched,
>   output folder removed). Tests: `test_period_names.py`.
> - **#9 jargon.** `gstr_2b`/`invoice` reasons are now plain sentences; flag
>   chips read "Currency not stated", "Total does not equal taxable + tax", …;
>   the reconciliation pack cover uses labels, not keys; the wipe dialog no
>   longer mentions `test-dump`.
> - **#10 warnings.** Pack warnings are a real list: message on one line, every
>   sample on its own indented line. The "reason for each one is listed here"
>   promise now holds.
> - **#11 "1 rows"** → "1 row" everywhere (Reports, Document Workspace).
> - **#16** the reconcile run modal labels periods with "no documents yet" and
>   defaults to one that has documents.
>
> Still open: **#2** (same bill in two sources still reads as extra
> "credit without support" — needs a candidate hint in `recon_engine`), **#5**
> (no in-app purchase path), plus the P2 polish list below.

Tester: acted as a CA running one client month through the app end to end.
Build: `main` @ 70aa957, launched from `.venv` against the real library in
`%LOCALAPPDATA%\CAUnpacker` (schema migrated v4 -> v6 cleanly).
Driven with the `computer` MCP (Cua driver). Test data: `test-dump/07-mixed-client-month`
(6 files: bank PDF, invoice PDF, Tally XML, GSTR-2B JSON, junk DOCX, broken JSON).

Everything below was reproduced on screen. Severity is my call as a target user,
not a code-quality judgement.

---

## P0 — money/data integrity

### 1. Re-importing the same folder silently doubles every figure

Repro: Acme Traders -> Oct 2026 -> Add folder -> `07-mixed-client-month`, twice.

| | first import | second import |
|---|---|---|
| status line | 4 processed, 1 review, 1 failed, 1 unclassified | 8 processed, 2 review, 2 failed, 2 unclassified |
| Bank_Statement_Cleaned.xlsx | 7 rows | 14 rows |
| Purchase_Register_Extracted.xlsx | 2 rows | 4 rows |
| GSTR_2B_Formatted.xlsx | 1 row | 2 rows |
| plank quota (rail) | 54 / 100 | 61 / 100 |

The pack folder is overwritten in place, so the good 16-row pack is replaced by a
32-row pack that double-counts the same bank lines and the same purchases. The only
trace is `classify_reason = "duplicate content of ... (identical bytes)"` in the DB;
nothing in the status strip, the file table or the pack says "these are the same bytes".
`dump.py:631` deliberately ingests and flags rather than dropping — that principle is
fine, but the *money* must not silently double. Needs at minimum: a pre-ingest
"this folder is already in this period" gate, and an explicit banner + separate
column in the pack when duplicates exist.

### 2. The same bill from two sources becomes extra "unsupported credit"

The fixture has one ₹11,800 purchase in Tally (`PUR-88`) and in the invoice PDF
(`ACME/26-27/0142`), plus GSTR-2B. Result on the Document Workspace money strip:

- ON THE PORTAL (2B) ₹11,800 · IN THE BOOKS ₹23,600 · DIFFERENCE ₹-11,800 ·
  CREDIT WITHOUT SUPPORT ₹11,800

A CA reads "₹11,800 of credit without support" for a bill that is legitimately in
both books and portal. There is no "this looks like the same bill under a different
number" hint, and the purchase register export carries the two rows separately.

### 3. Reconciliation Control Centre opens on a meaningless, alarming aggregate

Default filters are *All clients / All financial years / All accounting periods*, so
the landing view is a lifetime stat block:

- MATCH RATE **0.0%** (large, olive) · UNMATCHED 13 · DUPLICATE 166 ·
  REQUIRES INVESTIGATION **179** · UNRESOLVED EXCEPTION VALUE **₹40,96,770.02**

Eleven metrics + 7 filters + 5 tabs before any work is selected. Open on the last
worked period (or on nothing) instead, and defer the lifetime totals to Run History.

---

## P1 — will be read as "not finished"

### 4. Client delete uses the embedded browser's confirm

`Delete` on a client row raises the WebView2 dialog titled **"This page says"** with
blue OK / Cancel. It sits next to the app's own carefully worded "Wipe this PC's app
folder?" modal, so the native one looks like a different, unfinished product.

### 5. There is no way to buy or upgrade in the app

Licence modal: "Starter is ₹999 for 100 files a month. Pro is ₹2,500 unlimited. ...
Suite (₹6,000) is coming." and a single "Licence key / Paste the key we sent" field.
No price table, no purchase link, no "how do I get a key". A new CA who installs the
app has no path to paying inside it.

Also: the modal's key field is an underline-only input inside a boxed form system, and
the grid leaves a large empty cell next to Activate.

### 6. "Help / How to use" does nothing on Dashboard, Reconciliation and Reports

It calls `reopenGuide()`, which only re-shows the inline step card, and `syncGuide()`
hides that card unless one of the three Documents panes is visible. On the other three
screens the click is silent. There is no manual, FAQ or support link anywhere.

### 7. The guide card is context-blind

Shown to an account that already has 8 clients and 6 periods: **"HOW TO USE — Step 3
of 5 — Open that client — Click the client row you just added."** It is driven by
counts, not by what the user is doing, and it floats over the client table.

### 8. Period names take anything, and can never be fixed

Typed on one client: `Oct 2026`, `Oct-26`, `13 2026`, `January 2026` — all accepted,
no normalisation, no duplicate-month detection (only an exact-string duplicate is
caught). Consequence: the same month exists twice, and garbage periods flow into the
dashboard, the Reports list and the "Run reconciliation" period dropdown. There is no
rename or delete for a period anywhere in the UI or engine (`periods.py` only has
create/list/get/tolerances) — the only way out is deleting the whole client.

### 9. Developer vocabulary in user-facing text

- `GSTR-2B_broken.json: recognised as **gstr_2b** but no rows extracted · Tax_Invoice_header_only.pdf:
  recognised as **invoice** but no line items`
- flag chip in the invoice table: **`currency_unknown`** (also written into the pack's
  Flags column)
- wipe dialog: "...and the **test-dump** samples are not touched"
- pack cover sheet rows: `matched`, `books_only`, `portal_only` (raw keys, no labels)
- Needs-Review.xlsx reason column carries the same raw strings.

### 10. The warning strip is a run-on paragraph that repeats itself

Single red paragraph, repeat after the double import:

> GSTR-2B_broken.json: recognised as gstr_2b but no rows extracted · Tax_Invoice_header_only.pdf:
> recognised as invoice but no line items · GSTR-2B_broken.json: recognised as gstr_2b but no
> rows extracted · Tax_Invoice_header_only.pdf: recognised as invoice but no line items

Separately: "3 files were skipped or produced no rows. **The reason for each one is
listed here.** · GSTR-2B_broken.json · not valid JSON" — only one of the three is listed.

---

## P2 — consistency / polish

11. **"1 rows"** in Reports (3x) and in the Document Workspace pack list.
12. **Three different file counts**: rail `54 / 100 files`, Dashboard `DOCUMENTS 80`,
    account panel `47 of 100 files this month` (the rail only refreshes on navigation;
    it showed 47 while the cache said 54). The definition of a "file" for quota is
    never explained.
13. **Dashboard "Needs attention" looks like it repeats rows**: `team_meeting_notes.pdf`
    and `GSTR-2B_broken.json` each appear twice with identical subtitles — they are two
    different dumps with the same filename, but nothing distinguishes them.
14. **Rail "Documents" does not go back to the client list** once you are inside a
    period; it reopens the last location, so the only way up is the "Periods" breadcrumb.
15. **"Settings — Coming soon"** is a dead label in the primary navigation, at launch.
16. **Truncated selects** in the file table: type shows `Bank s`, currency shows `INR ₹.`.
17. **Tables overflow at ~1300 px** (a normal laptop): the date column wraps
    ("2026-07-\n01") and a horizontal scrollbar appears on the transactions table.
18. **Pack filenames read like exports**: `Bank_Statement_Cleaned.xlsx`,
    `Master_Reconciliation_Grid.xlsx`, `Preflight_Report.xlsx`, `Needs_Review.xlsx`.
    "Cleaned" also fights the product promise "source accounting records are never
    modified".
19. **Currency "INR (inferred)" appears on every row** with no way to correct it.
20. **No search, filter or sort on the client list**, and no per-client document count.
    Fine at 8 clients, painful at 100.
21. **Reports has no filter, grouping or delete** — every pack ever generated is one
    long scroll, newest first.
22. **Source citation pop-up**: the page crop is over-zoomed so surrounding text is cut
    off ("Invoice Date 12/07/2026", "Place of Supply 27-Maharashtra" sliced), the matched
    value is not boxed/highlighted on the page image, and **"Open full page" opens the
    PDF in the default browser as a `data:` URL** (tab title: "data").
23. **Run reconciliation modal**: three dropdowns plus rule set and a note, with
    "Each workflow uses the same matching engine with field-specific evidence" as the
    only guidance. It pre-selects the *first* period in the list (here `Acme Traders ·
    January 2026`, which has no documents) while the helper text says "Only periods with
    processed source rows can be reconciled" — the list itself is unfiltered
    (`recon-centre.js:938` maps every period). Clicking "Run reconciliation" twice stacks
    two modals, and the offset second modal pushes its footer buttons off-screen.
24. **Accessibility**: activating the left-nav buttons through the accessibility
    interface (UIA invoke) repeatedly did nothing, while a real mouse click on the same
    button worked. Same for client rows. Worth checking with Narrator — that path is
    exactly what a screen-reader user has.
25. **After a window resize the content pane sometimes stays blank** until the next
    click triggers a repaint (seen twice after minimising and restoring).

---

## What worked well (so it doesn't get "fixed")

- Startup, migration v4 -> v6 and the second-instance guard were clean.
- Import progress ("Sorting 7…", "Reading bank PDF…") with a working **Cancel import**
  and the Add buttons disabled while busy.
- Per-file outcome chips (PROCESSED / NEEDS REVIEW / FAILED / UNCLASSIFIED) with a short
  human reason, plus a type override dropdown per file.
- Source citation pop-up with "WHAT WE READ" + Copy citation + page reference.
- Bank balance tie-out (`Opening · Stated close · Computed close`) and the
  money strip (portal vs books, credit at risk, credit without support).
- The generated workbook itself: `DD-MM-YYYY` dates, ₹ number formats, a Source column
  with `file#page`, a 27-column reconciliation grid with Status/Why/Decision.
- The wipe modal, the licence "not recognised" error, and the duplicate-period message.

## State left behind (test artefacts)

- `Acme Traders · Oct 2026` now holds the **doubled** import (14 bank rows) and its pack
  was overwritten; the pre-doubling 16-row pack is gone.
- Three junk periods on Acme Traders: `13 2026`, `Oct-26`, `January 2026` — cannot be
  deleted from the UI.
- Two throwaway clients were created and deleted again (count back to 6).
