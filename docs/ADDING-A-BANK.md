# Adding a bank profile from a CA sample

Use this when a new bank PDF lands in Needs review and the existing HDFC / ICICI / SBI / Axis / Kotak hints miss it.

## What to collect

Keep one digital (not scanned) PDF that the CA already trusts. Note:

- Filename tokens (`hdfc`, `sbi_`, bank name on the first page)
- How debit and credit are labelled (`Dr`/`Cr`, Withdrawal/Deposit)
- Whether dates are `DD-MM-YYYY` or `DD/MM/YY`
- Whether a printed opening and closing balance exist

Do not send the PDF off this PC. Copy those notes only.

## Where to change code

`apps/engine/parsers/bank/profiles.py` — add a `BankProfile`:

- `key`: short slug (`yesbank`)
- `label`: name the CA will recognise
- `hints`: lowercase fragments that appear in the filename or the first 500 characters of extracted text
- `debit_words` / `credit_words`: tokens on the amount columns

`detect_profile` checks filename first, then the header text, then falls back to a generic profile.

## After the profile exists

1. Drop the sample into a throwaway client/period.
2. Confirm rows and the balance-check sheet (match, mismatch, or could not verify).
3. If the running total breaks, keep those rows and flag them — do not drop them to force a match.
4. Add a small fixture test next to `test_bank_trust.py` if the layout is stable.

## Overrides

If classification is wrong, set the kind to bank in the dump tray and reparse. Do not invent a profile from a scanned photo until the digital form works.
