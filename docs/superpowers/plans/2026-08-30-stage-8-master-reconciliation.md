# Stage 8 — Master reconciliation grid

**Goal:** When a period has books (purchase invoices and/or Tally/Zoho purchases) plus GSTR-2B, write `Master_Reconciliation_Grid.xlsx` and show matched / unmatched / amount-mismatch in the desktop UI.

**Spec:** `STAGES.md` Stage 8, `BUILD-PLAN.md` phase 7, `PRODUCT-VISION-CHAT-SUMMARY-2026-08-17.md` bank-assist scoring.

## Global Constraints

- Client documents never leave the device. No network in recon code.
- Never silently fix GSTIN or amounts. Statuses are evidence for the CA.
- Bank vs invoice is an assist (`bank_hint` only), never a recon status.
- GSTR Match/Books-ref columns stay empty unless this period actually ran recon (Stage 6 JSON-only dumps must still have empty match columns).
- File outcomes stay `processed | needs_review | failed | unclassified`. Recon does not invent a fifth file outcome.
- Follow existing pack writers (`apps/engine/pack/`) and pipeline output keys.
- TDD: failing tests first. Do not commit unless the controller asks (controller will not ask in this pass).
- Do not dispatch subagents.

## Match rules

Exact match when all of:

1. GSTIN equal after strip + uppercase
2. Invoice number equal after `normalize_invoice_number` (strip non-alphanumeric; strip leading zeros in digit runs so `INV/001` and `INV-1` both become `INV1`)
3. Invoice date equal as calendar dates (parse common `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`)
4. Invoice value differs by at most ₹1 (`Decimal`)

Otherwise, same GSTIN + same normalized invoice + same date but amount off by more than ₹1 → `amount_mismatch`.

Same GSTIN + date + amount (₹1) but invoice numbers only “close” (one normalized form is a prefix of the other, length ≥ 3) after exact matching is done → `likely` (CA must confirm; not auto-matched).

Unmatched 2B → `portal_only`. Unmatched books purchases → `books_only`.

One-to-one greedy: each books row and each 2B row used at most once. Prefer exact over amount_mismatch over likely.

**Books side:** purchase invoice rows plus Tally/Zoho rows classified as purchase (`_as_register_row` shape). Do not put GSTR-1 sales into this grid.

**Bank assist (optional):** for each recon row, if bank lines exist, score: exact amount +50, date within 7 days +20, party/narration name overlap +20, debit for a purchase +10. If score ≥ 70, set `bank_hint` to a short string (date, amount, narration snippet). Never change `status` from this.

## Output Excel

`Master_Reconciliation_Grid.xlsx` in the period output folder.

Sheets:

- **Cover** — counts: matched, books_only, portal_only, amount_mismatch, likely; note that bank hints are not matches
- **Grid** — one row per recon row
- **Unmatched** — books_only + portal_only + amount_mismatch (+ likely)

Grid columns: Status, GSTIN, Party, Invoice no (2B), Invoice no (books), Date (2B), Date (books), Amount (2B), Amount (books), Amount diff, Bank hint, Source (2B), Source (books)

Statuses as written: `matched`, `books_only`, `portal_only`, `amount_mismatch`, `likely`

## Pack API (`pack.recon` and output key `master`)

When recon runs, append:

```json
{
  "key": "master",
  "label": "Master_Reconciliation_Grid.xlsx",
  "path": "<abs>",
  "rows": <grid row count>,
  "status": "ready"
}
```

And `summary["recon"]` / `pack.recon`:

```json
{
  "counts": {
    "matched": 0,
    "books_only": 0,
    "portal_only": 0,
    "amount_mismatch": 0,
    "likely": 0
  },
  "rows": [ { "status": "matched", "gstin": "...", "party": "...", "invoice_2b": "...", "invoice_books": "...", "date_2b": "...", "date_books": "...", "amount_2b": 0, "amount_books": 0, "amount_diff": 0, "bank_hint": "", "source_2b": "...", "source_books": "..." } ]
}
```

`pack_dict` must pass `recon` through so the UI can render without opening Excel.

When recon runs, set 2B row `match_status` / `books_ref` before `write_gstr_2b`. Cover note may say matches were filled. JSON-only jobs leave them empty.

## Tasks

### Task 1 — Engine matcher, Excel, pipeline, tests

Files: `apps/engine/recon.py` (new), `apps/engine/pack/recon_xlsx.py` (new), `apps/engine/pipeline.py`, `apps/engine/pack/gstr_xlsx.py` (only cover note when matches filled — optional), `apps/engine/tests/test_recon.py`, `apps/engine/tests/test_stage8_gate.py`, `STAGES.md` (Stage 8 gate checkboxes / current stage line only if tests pass)

Do not edit `apps/ui/**`.

### Task 2 — Desktop unmatched tray

Files: `apps/ui/index.html`, `apps/ui/app.js`, `apps/ui/styles.css`, `apps/ui/tests/` (small node test for count copy if you extract a helper)

Do not edit `apps/engine/**`.

Render `#recon-block` when `pack.recon` exists. Show counts. Filter chips: All / matched / unmatched (books_only+portal_only) / amount-mismatch / likely. Table of rows. Hide when no recon. Update GSTR preview note to: empty until recon, or “Match columns filled in GSTR Excel when a master grid exists.”
