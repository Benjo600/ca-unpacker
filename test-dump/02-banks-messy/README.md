# 02 — Messy bank statements

Longer digital PDFs with UPI/NEFT/IMPS narrations. Still text PDFs, not scans. The parser should keep a matching running balance.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `HDFC_MehtaTrading_Jul2026_complex.pdf` | Bank statement | ≥10 transaction lines, continuation-style vendor names. | Bank Excel; cover status **match** if opening + movements = closing. |
| `ICICI_AnitaMehta_Jul2026_complex.pdf` | Bank statement | Same, ICICI debit/credit words. | Included in the period bank pack. |
| `SBI_KiranAgencies_Jul2026_complex.pdf` | Bank statement | Same, SBI wording. | Included in the period bank pack. |
| `HDFC_MehtaTrading_Jul2026_LONG.pdf` | Bank statement | About 90 lines. Unpack should still finish and balance. | Bank Excel with ~90 rows, status match. |
