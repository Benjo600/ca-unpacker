# Sample dump kit

Each numbered folder is one scenario. In CA Unpacker: add a client and a period, then **Add folder** and pick **one** of these folders.

| Folder | What it is | When the job looks finished |
|---|---|---|
| `01-banks-digital` | Clean HDFC / ICICI / SBI PDFs | `done` if you dump only this folder |
| `02-banks-messy` | Longer narrations + a 90-line statement | `done` if only this folder |
| `03-invoices` | Line-item bills plus a header-only bill | `needs_review` because of `Tax_Invoice_header_only.pdf` |
| `04-gst-json` | Portal JSON plus one broken file | `needs_review` because of `GSTR-2B_broken.json` |
| `05-books-tally-zoho` | Tally XML/zip and Zoho CSV | `done` if only this folder |
| `06-unknown-junk` | Word / tiny images / notes PDF | `needs_review` |
| `07-mixed-client-month` | One messy month | `needs_review` — this is the honesty check |

Do not dump `Darshan` or other **output** folders back in. Cleaned Excels belong in the folder you chose at first launch.

Rebuild this tree:

```bat
.venv\Scripts\python.exe build_test_dump.py
```
