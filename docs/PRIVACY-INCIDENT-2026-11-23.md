# Client documents in a public repository — incident note

**Date:** 23 Nov 2026
**Status:** files removed and history rewritten; one follow-up step remains (see
[Still open](#still-open))

## What happened

Two real business documents were committed to this public repository and
shipped in its history:

| File | What it contained |
|---|---|
| `testy stss.pdf` (repo root) | A real Kotak Mahindra bank statement — account holder name, account number, branch, and every transaction with payee names and UPI references |
| `apps/engine/tests/fixtures/invoices/flpk.pdf` | A real marketplace tax invoice — supplier legal name, GSTIN, PAN, CIN, registered and ship-from addresses, buyer name and address, order id, invoice numbers, device IMEI/serial |

The invoice was a deliberate test fixture: it reproduces a real marketplace
layout that the invoice parser has to handle. The statement was a scratch file
that landed at the repo root during debugging. Neither was reviewed for
personal data before it went up, and there is no test or lint that would have
caught it.

This matters more than a normal code leak. The product's promise is that a
client's files never leave their PC. A client document sitting in a public
repository contradicts that promise in a way a customer would be entitled to be
angry about.

## What was done

1. **Removed both files from the repository** and rewrote the history so no
   commit contains them. Verified: `git log --all -- <path>` is empty for each,
   and the current history returns 404 for both paths.
2. **Rebuilt the invoice fixture** rather than deleting it, so the parser
   regression it guards still runs:
   - `apps/engine/tests/fixtures/invoices/build_marketplace_fixture.py` rebuilds
     the file from a source PDF by redacting each identifying string in place
     and drawing a fictional replacement at the same coordinates.
   - Layout, column positions, amounts and tax split are unchanged; every
     identity field is fictional. The parser returns the same values it did for
     the real invoice.
   - The generator refuses to write an output file that still contains any of
     the original strings.
3. **Blocked the obvious repeat.** Root-level `*.pdf`, `*.docx`, `*.xlsx` and
   `build_log.txt` are gitignored, so a scratch document dropped at the repo
   root cannot be committed by accident.
4. **Encrypted the access token at rest**, like the refresh token already was.
   Older installs migrate themselves on first read.
5. **Stopped shipping the UI test scripts** inside the installer.

## Still open

A force-push removes the files from the branch, not from GitHub's object
store. The pre-rewrite commits are unreachable but were still being served when
this was written, so the old copy of the statement remained downloadable by
anyone holding an old commit id.

Two ways to close it, pick one:

- **Make the repository private.** Immediate and complete for the public. Also
  the sensible default for source that is sold as a product.
- **Ask GitHub Support to purge unreachable objects** for this repository. Keeps
  the repository public; takes days.

Do not treat this note as closed until one of those is done.

## Rules this establishes

- **Never commit a client document.** Not as a fixture, not as an example, not
  "just for a minute". If a parser needs a real-world layout to stay honest,
  anonymise it with the generator and commit the anonymised output.
- **Anonymise by redaction, not by rebuilding.** Rebuilding a page from
  extracted text loses the ruling lines and column geometry that the table
  parser depends on, which quietly weakens the very test the fixture exists
  for.
- **Check the fixture, not the intent.** Run the generator: it fails if any
  original string survives. A hand-checked "looks fine" is how this happened.
- **A scratch file at the repo root is a leak waiting to happen.** Work from a
  directory outside the repository, or rely on the ignore rules.
