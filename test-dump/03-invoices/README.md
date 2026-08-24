# 03 — Tax invoices

Printed GST invoices. The app only writes a purchase workbook when it finds a **header plus an HSN line-item table**. It must not invent a total from the last number on the page.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `Tax_Invoice_Acme.pdf` | Invoice | One HSN line (Professional fees 998314). GSTIN checksum ok. | `Purchase_Register_Extracted.xlsx` sheets **Invoices** and **Line items**. Not needs_review. |
| `Tax_Invoice_Mehta_two_lines.pdf` | Invoice | Two HSN lines (998314 and 997331) summing to 11800. | Two line-item rows keyed by MEHTA/26-27/0881. |
| `Tax_Invoice_BadGSTIN.pdf` | Invoice | Still unpacks, but GSTIN checksum is wrong on purpose. | Purchase row exists; Flags include `gstin_checksum`; row tinted. Job can still be done if nothing else is blocked. |
| `Tax_Invoice_BadHSN.pdf` | Invoice | HSN 12345 is not 4/6/8 digits. | Purchase row with `hsn_length` flag. Not rewritten. |
| `Tax_Invoice_header_only.pdf` | Invoice | Looks like a bill but **no item table**. | No purchase row. File stays in **Needs review**. `Needs_Review.xlsx` status unreadable / no line items. Job `needs_review`. |
