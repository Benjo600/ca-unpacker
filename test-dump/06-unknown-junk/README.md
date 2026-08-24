# 06 — Unknown and unreadable

These should stay in the CA’s face. The job must not look finished.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `meeting_notes.docx` | Unknown | Word file. No parser. | Needs review. Set a type only if you really know it. `Needs_Review.xlsx` status unknown. |
| `random_scan.jpg` | Unknown (or invoice if OCR sees GST words) | Tiny JPEG with no invoice text. | Needs review. Must **not** invent a purchase row. |
| `invoice_photo.png` | Unknown / unreadable invoice | 1×1 PNG. No OCR table. | No purchase Excel row. Needs review. |
| `random_email_print.pdf` | Unknown | PDF with meeting notes, not a bank or invoice. | Needs review. No bank/purchase pack from this file alone. |
