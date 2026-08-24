# 01 — Digital bank statements

Clean digital PDFs (text, not scans) for HDFC, ICICI and SBI. This is the path the bank unpacker was built for.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `HDFC_Statement_Jul2026.pdf` | Bank statement | Line-by-line transactions, running balance, debit vs credit from bank wording. | `Bank_Statement_Cleaned.xlsx` with a match/mismatch cover. Job can still be needs_review if other files are mixed in. |
| `ICICI_Statement_Jul2026.pdf` | Bank statement | Same as HDFC for an ICICI layout. | Rows in the same bank Excel (one workbook per period, all bank files). |
| `SBI_Statement_Jul2026.pdf` | Bank statement | SBI debit/credit words (ATM Withdrawal, IMPS Credit). | Same bank pack. |
