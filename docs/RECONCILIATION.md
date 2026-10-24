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
