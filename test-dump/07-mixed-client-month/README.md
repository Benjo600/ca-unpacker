# 07 — Mixed client month (dump this one to see honesty)

A realistic tray: bank + good invoice + thin invoice + GSTR JSON + Tally + junk + broken JSON. Add **this whole folder** to one period.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `HDFC_Statement_Jul2026.pdf` | Bank statement | Digital HDFC. | `Bank_Statement_Cleaned.xlsx` written. |
| `Tax_Invoice_Acme.pdf` | Invoice | Line-item tax invoice. | `Purchase_Register_Extracted.xlsx` Invoices + Line items. |
| `Tax_Invoice_header_only.pdf` | Invoice | No item table. | Needs review — not a fake purchase row. |
| `GSTR-2B_July.json` | GSTR-2B | Valid JSON. | `GSTR_2B_Formatted.xlsx`. |
| `GSTR-2B_broken.json` | GSTR-2B | Broken JSON. | Needs review. |
| `Tally_Daybook.xml` | Tally | Daybook XML. | Books / purchase / sales sheets. |
| `meeting_notes.docx` | Unknown | Word notes. | Needs review. |

**Period job status:** `needs_review` (not done) because of the header-only invoice, broken JSON, and Word file.
**Still on disk:** bank Excel, purchase Excel for Acme, GSTR-2B Excel, Tally sheets, and `Needs_Review.xlsx` listing the failures.
