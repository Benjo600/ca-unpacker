# 05 — Tally and Zoho exports

Only structured exports. A Tally **print PDF** or a screenshot will not unpack. Live Tally ODBC is out of scope.

Dump **this folder** onto one period in CA Unpacker (Add folder). Do not dump the parent `test-dump` tree if you want a clean per-type check.

| File | Kind the app should detect | What should happen | Pack / review |
|---|---|---|---|
| `Tally_Daybook.xml` | Tally | Single purchase voucher PUR-88 (Acme Traders, 11800). | Purchase/books register with PUR-88. |
| `Tally_Daybook_busy.xml` | Tally | PUR-88, PUR-91 and sales SAL-10 in one daybook. | Purchase and sales registers both written. |
| `Tally_Backup.zip` | Tally | Zip of the simple PUR-88 daybook. | Same as Tally_Daybook.xml. Dumping both XML and this zip duplicates PUR-88. |
| `Tally_Backup_busy.zip` | Tally | Zip of the busy daybook. | Same as Tally_Daybook_busy.xml. |
| `Zoho_Books_Invoices.csv` | Zoho | One sales invoice INV-204. | Sales register INV-204, value 5900. |
| `Zoho_Books_Invoices_busy.csv` | Zoho | INV-204 plus INV-218. | Two sales rows. |
