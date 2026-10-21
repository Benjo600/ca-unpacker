# Synthetic SAP report fixtures

These files are **synthetic test fixtures written by this project**. They are
**not genuine SAP exports**, were not produced by SAP software, and contain no
real company, vendor, customer or employee data. The names and amounts are
invented solely to exercise CA Unpacker's SAP report parser.

The layouts approximate common SAP ALV / Fiori **flat-file** exports (headers
followed by rows, optional title rows, optional totals rows). They are not a
specification of SAP's proprietary formats. Real exports may use different
column labels, multi-line headers, technical field names, hierarchy rows,
currency translation columns, or PDF layouts.

Files:

- `synthetic_gl_line_items.csv` — general ledger line items
- `synthetic_journal_entries.csv` — balanced journal entry pairs
- `synthetic_trial_balance.csv` — opening/debit/credit/closing trial balance
  with a consistent totals row
- `synthetic_vendor_ledger.csv` — vendor account line items
- `synthetic_customer_ledger.csv` — customer account line items
- `synthetic_ap_aging.csv` — accounts payable aging buckets
- `synthetic_ar_aging.csv` — accounts receivable aging buckets
- `synthetic_other_ledger.csv` — SAP ledger headers without a report title

XLSX and positioned PDF fixtures are generated in temporary folders by
`apps/engine/tests/fixtures_sap.py` so the repository does not need to store
binary test files.

When a genuine SAP export is available, keep it out of the repository unless
it has been anonymised, and compare its layout with these fixtures.
