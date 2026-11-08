# Reconciliation

The Reconciliation page reads the rows already extracted by the Document Workspace.
It never writes back to a source file or accounting export. Each comparison is
calculated on demand for one client period.

## Supported comparisons

| Workflow | Left dataset | Right dataset | Required processed inputs |
| --- | --- | --- | --- |
| GSTR-2B vs purchase invoices | GSTR-2B JSON | Invoice PDFs/images | At least one GSTR-2B row and one extracted invoice header |
| GSTR-2B vs purchase register | GSTR-2B JSON | Purchase rows from Tally/Zoho | GSTR-2B JSON and a Tally/Zoho export with `Voucher Type = Purchase` (or a Zoho bill export) |
| Purchase invoices vs purchase register | Invoice PDFs/images | Purchase rows from Tally/Zoho | Invoice files and the purchase register export |
| Bank statement vs accounting ledger | Bank statement PDF/Excel/image | Tally payment, receipt, contra or bank vouchers | Bank statement and a Tally day book containing those voucher types |

If either side has no rows, the page shows the missing input instead of a result.
There is no synthetic or demo data.

## Matching rules

### GST / purchase comparisons

1. A pair is **matched** only when GSTIN and invoice number agree, the invoice
   totals agree within ₹1, and tax and taxable values agree within ₹1. Dates may
   differ by up to 30 days.
2. The same key with a different total is **amount mismatch**. The row keeps both
   values and the difference.
3. A tax, taxable-value or date difference on an otherwise matching key becomes
   **review required**.
4. A shared invoice-number prefix (with the same GSTIN), an exact reference
   where one side has no GSTIN or a different GSTIN, or party + amount +
   nearby date without a shared reference only becomes **review required**,
   never an automatic match.
5. Repeated keys are **duplicate candidates**. They are not paired arbitrarily.
6. Remaining rows are shown as **only in** the left or right dataset.

### Bank vs accounting ledger

1. A voucher reference found in the bank narration plus an agreeing amount is a
   match. A reference with a different amount is an amount mismatch.
2. Without a reference, matching amount + nearby date + party-name overlap is
   **review required** only.
3. Similar amounts alone never produce a match.
4. Multiple plausible ledger entries become a review row rather than a guess.

## Source inspection

Each result row can be opened to see both extracted records. From there the user
can open the original stored file or request a rendered page crop (for PDFs and
images). Source files are opened read-only.

---

# Reconciliation Control Centre (persisted engine)

The 2026 upgrade adds a persisted, explainable reconciliation platform on top of
the same extracted rows. The legacy comparison cards above remain for backward
compatibility and for the existing GSTR Excel pack.

## Architecture

| Layer | Module | Responsibility |
| --- | --- | --- |
| Matching engine | `apps/engine/recon_engine.py` | Pure, offline matching. No database or UI imports. Deterministic proposals with evidence, confidence, tolerances and explanations. |
| Workflow catalogue and datasets | `apps/engine/recon_datasets.py` | Maps stored source types to the seven workflows, financial-year derivation, source-file metadata. |
| Persistence and decisions | `apps/engine/recon_service.py` | Runs, rule snapshots, matches, exceptions, links, audit events, manual decisions, comparison and filters. |
| Exports | `apps/engine/recon_report.py` | Excel evidence pack and PDF executive summary from the persisted snapshot. |
| Desktop bridge | `apps/desktop/app.py` | `get_recon_*`, `start_recon_run`, `recon_decide`, `recon_update_exception`, export and audit methods. |
| Desktop UI | `apps/ui/recon-centre.js` / `.css` | Control Centre, Workbench, Exception Management Centre, Run History, Rules. |

## Data model

Additive tables are created by the existing schema initializer with
`metadata.create_all` (check-first, no drops or rewrites):

- `recon_rule_sets` — versioned rule configurations.
- `recon_runs` — one immutable run header with client/period/workflow,
  source file ids, rules snapshot, counts, totals, checks, status and actor.
- `recon_matches` — one proposal/decision row with classification, confidence,
  matched fields, differences, tolerances, allocations, candidate records,
  full source-record payloads and decision metadata.
- `recon_record_links` — run/side/row index for re-matching and allocation
  validation.
- `recon_exceptions` — category, status, severity, amount, assignee, evidence
  and resolution reason.
- `recon_audit_events` — actor, timestamp, action, previous/new status, reason,
  record references and evidence references.

Run payloads are stored on the match row, so deleting or re-parsing a source
row later does not rewrite historical results.

## Matching rules

- Exact and normalised references: case, spaces, punctuation and leading zeros
  are normalised; original display values are preserved.
- GSTIN, party name, date, taxable value, IGST/CGST/SGST/cess and invoice total
  are compared where readable.
- Amount and date tolerances are configurable and every applied tolerance is
  written into the match explanation.
- Reference-based bank matching extracts UTR, cheque, invoice/payment and
  narration references.
- One-to-many and many-to-one proposals carry explicit allocations and always
  require review.
- Partial settlements calculate the outstanding balance and are proposals, not
  confirmed matches.
- Duplicates are surfaced before matching and are never paired arbitrarily.
- Reversal/credit-note candidates require opposing amounts plus a document or
  direction signal; the explanation states that opposite amounts alone are not
  proof.
- Currencies are never converted. A mismatch is a review item.
- A record is allocated at most once per run. Manual split/aggregation
  decisions validate that every selected record appears once and that no pair
  is allocated twice.
- Place-of-supply differences are flagged when both documents carry a state
  code. ITC flags are displayed, never concluded by the system.

Confidence is a weighted score over the fields that could actually be compared.
Exact/strong evidence can auto-confirm; probable, partial, allocation,
duplicate and reversal proposals remain review items.

## Workflows

1. GSTR-2B vs Purchase Register — GSTIN, invoice, dates, taxable value, tax
   components, duplicate/review items. No ITC eligibility conclusion.
2. GSTR-2B vs Purchase Invoices — portal vs extracted PDF invoice evidence with
   page/coordinate traceability.
3. Purchase Invoices vs Purchase Register — missing postings, missing source
   invoices, duplicates and value/tax differences.
4. GSTR-1 vs Sales Register — customer GSTIN, invoice, date, value, tax and
   place of supply where available.
5. Bank Statement vs Accounting Ledger — UTR/cheque/narration references,
   partial payments, splits, bank charges/interest, unpresented-cheque hints and
   closing-balance checks (only claimed when both closings exist).
6. Vendor Statement vs Purchase Ledger — vendor statements can be imported as
   `vendor_statement` XLSX/CSV/PDF tables; missing documents, credit notes and
   outstanding balances remain visible.
7. General Ledger vs Sub-ledger — grouped opening/movement/closing balance
   comparison. A balance is only reported reconciled when both sides carry a
   closing balance.

## Operating notes

- Rules are saved as new versions. Each run snapshots the exact rule set and
  engine version used.
- Re-running always creates a new run; previous runs and decisions are kept.
- Every manual action requires a reason and writes an audit event.
- Exports are written to the period output folder under `Reconciliation/`.
- Large result sets are paginated by the API (default 100 rows) and rendered in
  a scrollable table; matching runs on a background thread with progress and
  cooperative cancellation.

## Tests

```powershell
& '.\.venv\Scripts\python.exe' -m pytest apps/engine/tests/test_recon_engine_v2.py -q
& '.\.venv\Scripts\python.exe' -m pytest apps/engine/tests/test_recon_service.py apps/engine/tests/test_recon_schema.py apps/engine/tests/test_vendor_statement.py -q
& '.\.venv\Scripts\python.exe' -m pytest apps/desktop/tests -q
node --test apps/ui/tests/*.test.js
```

The tests cover normalisation, exact/fuzzy/tolerance matching, one-to-many,
many-to-one, partial payments, duplicates, reversals, ambiguity, currency
mismatches, bank references, manual decisions, exception lifecycle, audit,
restart persistence, historical integrity, rules snapshots, real Excel/PDF
exports, all seven workflows and the existing application suite.

## Screenshots

- `recon-screenshots/01-control-centre.png` — persisted Control Centre.
- `recon-screenshots/02-recent-runs-and-exceptions.png` — history and outstanding exceptions.
- `recon-screenshots/03-workbench.png` — Workbench opened from a real run.
- `recon-screenshots/04-match-investigation.png` — field evidence, tolerances and source records.
- `recon-screenshots/05-exception-investigation.png` — exception decisions, notes and evidence.
- `recon-screenshots/06-rules-and-configuration.png` — versioned rule snapshots.
- `recon-screenshots/07-run-history.png` — historical runs and comparison selection.
- `recon-screenshots/08-run-reconciliation.png` — run progress and dataset availability.
- `recon-screenshots/09-exception-queue.png` — exception management queue.
