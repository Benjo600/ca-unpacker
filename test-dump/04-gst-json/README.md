# 04 — GST portal JSON

Official JSON downloads only. GST **PDFs** are not unpacked. This is a reshape (JSON → Excel), not OCR.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `GSTR-2B_July.json` | GSTR-2B | One B2B from Acme Traders, invoice ACME/26-27/0142. Match columns stay empty. | `GSTR_2B_Formatted.xlsx` B2B sheet. No recon. |
| `GSTR-2B_July_busy.json` | GSTR-2B | Two B2B parties plus one credit note. | B2B sheet plus CDN sheet when present. |
| `GSTR1_July.json` | GSTR-1 | Outward B2B BN/101 and an HSN summary. | `GSTR_1_Formatted.xlsx`. |
| `GSTR3B_July.json` | GSTR-3B | Summary outward taxable 50000. | `GSTR_3B_Formatted.xlsx`. |
| `GSTR-2B_broken.json` | GSTR-2B (filename) | Not valid JSON. | Zero rows. File in Needs review. Job `needs_review`. `Needs_Review.xlsx` status no rows. |
