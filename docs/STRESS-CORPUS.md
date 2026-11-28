# Stress corpus (fictional)

`build_corpus.py` writes a machine-generated document dump and a manifest that
records, for every file, what the engine is expected to say about it. Nothing in
it comes from a client; every name, GSTIN, account number and amount is invented
from the seed. The output folder (`stress-dump/` by default) is gitignored, so it
is never committed.

The point is **known truth by construction**: the generator wrote the rows, so it
knows the count, the totals, the balance status and the warnings the engine should
produce. `corpus_run.py` feeds the same files through the real engine and grades
the answer against that manifest — the engine is never compared with itself.

## Generate

```powershell
.venv\Scripts\python.exe build_corpus.py                       # standard, 600 files
.venv\Scripts\python.exe build_corpus.py --profile smoke --out stress-dump/corpus-smoke
.venv\Scripts\python.exe build_corpus.py --profile brutal      # 2x standard
.venv\Scripts\python.exe build_corpus.py --seed 7 --out temp/corpus7
```

- `--seed` (default `2026`) — the same seed and profile produce byte-identical
  files; a different seed produces a different dump that still satisfies the
  manifest.
- `--out` (default `stress-dump/corpus`) — the generator deletes and recreates
  only this folder. It refuses to wipe the repo root or a drive root. Note that
  the default is the same for every profile, so give the smoke build its own
  `--out` if you want to keep a standard corpus next to it.
- Standard takes about 35 seconds and 57 MB (the 50 MB junk blob is most of it).

Run the built-in contract test after changing the generator:

```powershell
.venv\Scripts\python.exe -m pytest apps/engine/tests/test_corpus_smoke.py -q
```

It builds the smoke profile twice into a temp folder and checks the manifest,
the CSV, the gallery and every hash. It takes about 17 seconds.

## What is in the standard profile

| Family | Files | What it stresses |
|---|---|---|
| `banks/` | 145 | HDFC, ICICI, SBI, Axis, Kotak layouts; six unsupported banks; Indian lakh/crore grouping; `Dr`/`Cr` suffixes; month-name dates; zero opening; wrapped narrations; duplicate rows; wrong printed closing; a jump in the running balance; multipage; scanned, rotated, low-resolution PNG; a password-protected PDF; a statement with no opening/closing; an empty statement |
| `invoices/` | 105 | 1–60 line items; CGST+SGST and IGST; exempt; discount; round-off; multipage; invalid GSTIN checksum; 5-digit HSN; totals deliberately out by 500; image-only scans; an impossible date |
| `gst/` | 45 | GSTR-2B, 1 and 3B; valid, empty, truncated and unknown-schema files; one 5,000-invoice 2B |
| `books/` | 35 | Tally XML and zip (one 5,000-voucher export), Zoho CSV and XLSX, SAP GL CSV and PDF |
| `junk/` | 70 | empty, one-byte and truncated files, wrong extensions, corrupt zip/xlsx/docx, nested zip, tar, 50 MB blob, unicode and awkward names, hidden dot-file, legacy `.xls` and `.doc`, byte-identical duplicate pairs, images with no text |
| `mixed/` | 200 | 20 client-month folders of 10 files drawn from every family above |

`brutal` doubles the bank, invoice, GST and books variants and the number of
mixed folders; the junk family stays as it is.

Every file carries an expectation in `manifest.json`:

```json
{
  "path": "banks/Icic_clean_text_001_Jul2026.pdf",
  "family": "banks",
  "kind": "bank",
  "outcome": "processed",
  "rows": 5,
  "line_items": null,
  "totals": {"debit": 3100.75, "credit": 11515.0},
  "balance_status": "match",
  "flags": [],
  "notes": "clean_text",
  "sha256": "...",
  "size": 3133
}
```

- `kind` — what the file is (bank, invoice, gstr_2b, tally, zoho, sap, unknown).
- `outcome` — `processed`, `needs_review`, `failed`, `unclassified`,
  `skipped_duplicate`, `skipped_by_name` or `rejected_selection`.
- `rows` / `line_items` — transaction, voucher or invoice-line counts.
- `totals` — `debit`/`credit` for banks and SAP, `value`/`taxable` for invoices,
  GST, Tally and Zoho.
- `balance_status` — `match`, `mismatch` or `unverified` (banks only).
- `flags` — the warning codes the file is built to trigger, e.g.
  `closing_mismatch`, `inferred_from_balance`, `gstin_checksum`, `hsn_length`.
- `requires` — `ocr` when the file is an image; the run does not assert those
  without an OCR engine.
- `advisory` — the difference is interesting but not a failure.
- `password` — known password for the encrypted PDF (`corpus-open-2026`).

The same rows are in `manifest.csv` (open it in Excel) and `index.html`
(a gallery with one row per file).

## Run the corpus through the engine

```powershell
.venv\Scripts\python.exe corpus_run.py --out stress-dump/corpus-smoke
.venv\Scripts\python.exe corpus_run.py --limit 50
.venv\Scripts\python.exe corpus_run.py --family banks,invoices
.venv\Scripts\python.exe corpus_run.py --match broken_closing,encrypted
.venv\Scripts\python.exe corpus_run.py --no-isolate      # single process, debugging
.venv\Scripts\python.exe corpus_run.py --keep-sandbox    # inspect the throwaway library
```

`--out` defaults to `stress-dump/corpus`. `--profile` is only a label for the
report, but a mismatch with the manifest's profile prints a warning.

- Each folder in the manifest becomes one client and one period named `Jul 2026`.
- `LOCALAPPDATA` is redirected to a temp folder for the whole run, so the real
  library is never opened. `--keep-sandbox` prints where it went instead of
  deleting it.
- Every folder runs in its own child process: a parser crash is recorded as a
  finding and the rest of the corpus still runs.
- `--limit N` takes whole folders in path order until N files are selected, so
  `--limit 50` on the standard corpus is the first 50 bank files.
- `--timeout` is seconds per folder (default 900). A folder that hangs is
  reported as a hang, not a crash.
- Exit code is non-zero on any mismatch, crash or hang. Advisory differences and
  not-asserted files do not fail the run.

Reports are written next to the manifest:

- `corpus_report.csv` — one row per file: expected and actual kind, outcome,
  rows, line items, totals, balance, flags, approximate milliseconds and result.
- `corpus_report.html` — the same, split into mismatches, crashes, refused
  folders, slowest files, advisory differences and not-asserted files.

Read the top cards first. A green pass count equal to the file count is a clean
run. Otherwise start with **Mismatches**: each row shows the expected value and
what the engine produced, so a wrong parser and a wrong expectation look
different. **Crashes and hangs** carry the traceback. **Advisory differences**
are the files the manifest marks as interesting but not fatal.

## Add a family or a variant

1. Write `build_<family>(corpus: Corpus, plan=None, scale=1)` next to the others.
   Draw all randomness from `corpus.rng`, never from `random` or `datetime.now()`.
2. For every file, call `corpus.add(path, Entry(...))` with `family`, `kind`,
   `rows`, `totals`, `balance_status`, `flags` and a short `notes` string. If the
   value is not known, leave it out rather than guessing.
3. Call the new function from `build_standard` (and add a one-file slice to
   `build_smoke` if it is fast) and add the family to `FAMILIES`.
4. Rebuild, then run `corpus_run.py --family <family>` and check the new rows
   against the report.

A new variant inside an existing family is one entry in that family's `plan`
list plus a branch in its loop; the mixed folders pick up small, processed files
automatically.

## Known limits

- OCR quality is the OCR engine's, not the generator's. When two adjacent
  statement lines are detected as one block, the engine builds one row with the
  wrong amount and repairs the gap with an inferred row; the balance can still
  read `match` while the debit and credit totals are wrong. The run reports that
  as a totals mismatch — it is a parser/OCR finding, not a manifest error.
- The password-protected statement is deliberately unreadable, so it is expected
  as kind `unknown` with outcome `needs_review`; its password is in the manifest.
- The 50 MB blob and the 5,000-row exports are slow on purpose. Use `--family`
  or `--limit` while iterating.

## House rules

- The corpus is fictional. Do not copy a client document into it, and do not
  commit `stress-dump/`.
- Keep the files deterministic: fixed zip timestamps, no PDF metadata, no
  unseeded randomness, fixed document ids.
- Do not add a dependency to render PDFs or images other than the pinned ones
  (PyMuPDF, Pillow, openpyxl, pypdf).
- When the corpus exposes an app bug, record the file, the expectation and the
  traceback in the run report. Do not weaken the expectation to make the run
  green; fix the parser or mark the entry `advisory` with a note that names the
  bug.
