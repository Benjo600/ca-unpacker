# CA Unpacker — Product Vision Summary

Date: 2026-08-17

## What the product really is

CA Unpacker should not try to replace a CA, Tally, ClearTax, Winman, or similar accounting/compliance tools.

Its job is to solve the messy pre-accounting stage:

**Client dump → identify → organize → extract → normalize → validate → detect gaps → reconcile → produce CA-ready working files**

The problem being targeted is that CA firms often spend substantial time before actual filing/accounting begins: opening bank statements manually, copying transactions, organizing invoices, cleaning Excel, checking GST files, finding missing documents, jumping between multiple tools, and preparing usable working papers.

The opportunity is to consolidate that preparation stage into one desktop tool.

## Example workflow

A businessman sends the CA:

- Bank statements
- GST invoices
- GSTR-1 / GSTR-2B / GSTR-3B
- Tally or Zoho exports
- Capital gains statements
- Broker reports
- Random PDFs/images

CA Unpacker creates a client workspace such as:

```text
Rajesh Enterprises/
├── ORIGINAL_CLIENT_DUMP/
└── FY 2025-26/
    ├── Banks/
    ├── Purchase Invoices/
    ├── Sales Invoices/
    ├── GST/
    ├── Capital Gains/
    ├── Books/
    ├── Needs Review/
    ├── Outputs/
    └── README.md
```

The original files remain untouched.

The app inventories every file so that, conceptually:

> 286 files entered → all 286 must be accounted for.

It then classifies, extracts and normalizes the data and can create outputs such as:

```text
Bank_Transactions.xlsx
Purchase_Register.xlsx
Sales_Register.xlsx
GST_Reconciliation.xlsx
Capital_Gains_Working.xlsx
Exceptions.xlsx
```

The generated `README.md` can summarize what was received, processed, missing, failed and flagged.

## Does it need an LLM?

No. The core product can work without an LLM or any LLM API key.

Most of the work can be deterministic Python:

- PDF parsing
- OCR
- Excel/CSV reading
- JSON/XML parsing
- Regex
- Known document templates
- Fuzzy matching
- Mathematical checks
- Reconciliation
- Confidence scoring
- Anomaly detection
- SQLite history
- Folder organization

For example, a document containing labels such as:

```text
HDFC BANK
Account Statement
Opening Balance
Debit
Credit
Balance
```

can be classified as an HDFC bank statement without an LLM.

Likewise, an invoice containing a GSTIN, invoice number, taxable value, CGST/SGST and total can be recognized using patterns and validation logic.

A future optional LLM layer could be used only as a fallback for bizarre or unseen documents:

```text
Known parser
   ↓
Validation
   ↓
Confidence
   ↓
If uncertain → Human review
   ↓
Optional LLM later
```

This preserves privacy and reliability.

## What if every client's documents are different?

The app should not assume every document looks identical.

Instead, it should build a growing parser/profile library:

```text
HDFC format A
HDFC format B
SBI format A
ICICI format A
Zerodha format A
Groww format A
GST invoice variants
...
```

As real users expose new layouts, support can be added.

Unknown files should never be silently guessed. They should go to:

> **Needs Review / Unclassified**

A CA can classify them manually.

The principle is:

> 93% confidently automated + 7% clearly flagged is better than pretending 100% worked.

## Client-specific logic

Different professions/businesses behave differently, so the app should not apply identical accounting assumptions to everyone.

Example client profile:

```text
Client: Rajesh Enterprises
Type: Proprietorship
Industry: Wholesale trader
GST registered: Yes
Banks: HDFC + SBI
Books: Tally
Broker: Zerodha
```

Another:

```text
Client: Dr Mehta
Type: Professional
Profession: Doctor
GST registered: No
```

Different rule packs can apply to different client types.

However, the app should avoid making professional judgments such as:

> “₹50,000 credit = business income.”

Instead it should say:

> “₹50,000 bank credit found. Possible matching invoice identified.”

The CA decides whether it is income, loan, capital introduction, refund, own-account transfer, investment proceeds, rent, reimbursement, etc.

**Software finds evidence. CA makes accounting/tax judgments.**

## Gap detection

The software should not merely ask:

> Did parsing work?

It should ask:

> **Do I have evidence that the data is complete and trustworthy?**

There can be multiple levels.

### Definitely missing

Client has a known SBI account. Statements found:

```text
Apr ✅
May ✅
Jun ✅
Jul ✅
Aug ✅
Sep ❌
Oct ✅
...
Mar ✅
```

CA Unpacker can confidently say:

> 🔴 SBI September statement appears missing.

### Probably missing

GSTR-2B contains 96 purchase invoices, but only 12 purchase invoice documents were uploaded.

> 🟠 84 GSTR-2B entries currently have no corresponding invoice document.

### Merely unusual

The client normally sends around 100 invoices per month, but this month sends 20. If GSTR-2B and bank activity are also dramatically lower, the app may say:

> 🟡 Activity is unusually low, but there is currently no strong evidence documents are missing.

This avoids false alarms.

## Where previous history comes from

CA Unpacker stores its own metadata/results in local SQLite.

Example:

```text
April
Purchase invoices: 96

May
Purchase invoices: 104

June
Purchase invoices: 91
```

If August has 14, Python can calculate that the drop is unusual.

For brand-new clients there is no history yet, so the software relies more on:

- Known accounts
- Missing months
- GSTR evidence
- Books data
- Required document types
- Cross-document evidence

A CA could also import previous-year files to build a baseline immediately.

This is normal database/statistical logic, not AI learning.

## Bank reconciliation idea

After converting bank statements into Excel, CA Unpacker can compare transactions with other documents.

Example bank transaction:

```text
04-Apr
ABC Traders
₹59,000 credit
```

If there is no corresponding sales invoice:

> ⚠️ Unmatched bank receipt — ₹59,000.

If there is a matching invoice, the system can score the match:

```text
Exact amount                   +50
Date within 7 days             +20
Name similarity                +20
Correct debit/credit direction +10
```

Then:

```text
90–100 → auto-match
70–89 → likely
40–69 → possible
<40 → don't match
```

Later it can support one invoice → multiple payments and one payment → multiple invoices.

This is reconciliation mathematics, not an LLM problem.

## Cross-document inconsistencies

The strongest value may come from comparing several independent sources.

Example:

```text
GSTR-1 invoice     ✅
Bank receipt       ✅
Tally sales entry  ❌
```

Flag:

> Possible sale missing from books.

Or:

```text
Books sale       ✅
Bank receipt     ✅
GSTR-1           ❌
```

Flag:

> Possible GST reporting gap.

Or:

```text
GSTR-2B purchase    ✅
Purchase invoice    ❌
Books entry         ❌
Bank payment        ?
```

Flag:

> Supporting documents / books entry may be missing.

The system does not decide guilt or tax treatment; it directs the CA to what requires investigation.

## Automatic client query list

CA Unpacker could eventually prepare:

```text
DOCUMENTS / CLARIFICATIONS REQUIRED

1. SBI September statement missing.

2. ₹74,500 paid to Star Consultants on 15-May.
   Supporting invoice not identified.

3. ₹2,40,000 received from Rahul Enterprises.
   No corresponding sales invoice identified.

4. 12 recurring HDFC loan EMI payments detected.
   Loan statement / interest certificate not found.
```

This can reduce CA ↔ client back-and-forth.

## Capital gains

Broker statements can have their own parsers for sources such as:

- Zerodha
- Groww
- Mutual fund CAS
- Broker tax P&L

Possible output fields:

```text
Asset
Sale date
Purchase date
Sale value
Cost
Gain/loss
Possible STCG/LTCG
Source document
```

Tax-sensitive classifications should remain reviewable by the CA.

## Bulk processing for CA firms

Because CA firms handle many clients, the tool should eventually use a job queue:

```text
ABC Pvt Ltd — April — Processing
XYZ Traders — April — Queued
Sharma & Co — Q1 — Review needed
```

Possible worker model:

```text
Fast parsers: multiple workers
OCR: only 2–4 workers
Excel generation: limited workers
```

Do not simply spawn dozens of threads.

The preferred model is:

**parse once → store normalized data → generate reports from database**

instead of repeatedly reparsing PDFs.

This makes handling 10, 50 or 200 clients much easier.

## Privacy positioning

One of the strongest differentiators can be local processing.

The product can aim for a precise claim such as:

> **Client documents are processed locally on the CA's computer and are not uploaded to our servers or third-party AI APIs.**

Architecture:

```text
Files
↓
Local Python processing
↓
Local OCR
↓
Local SQLite
↓
Local Excel outputs
```

No OpenAI/Claude/Gemini dependency is required.

Possible UI status:

```text
Processing mode:      LOCAL
LLM/API:              NONE
Document uploads:     NONE
Data storage:         THIS PC
OCR:                  LOCAL
```

Strong privacy claims should only be made once every dependency/network feature has been verified.

## Authentication while keeping privacy

Subscriptions/licensing can still exist.

The server only needs metadata such as:

```text
Firm ID
Plan
Subscription expiry
Files processed this month
Clients processed
Device count
App version
```

It does not need client names, bank transactions, GST contents, invoice data, PAN/GSTIN, or actual documents.

Conceptually:

```text
Local PC
├── financial processing
├── client data
└── documents

Internet
└── authentication/licensing/usage counter only
```

The app could transparently display:

> Files processed this month: 4,382  
> Financial/document data transmitted: NONE

## The commercial problem

The original research behind the idea is that CA staff can spend hours turning client dumps into usable formats before real accounting/filing begins.

That is the core pain to solve.

Positioning:

> **CA Unpacker converts messy client documents into structured, review-ready accounting working papers.**

It is not primarily:

- An AI accountant
- Another GST reconciliation tool
- A bank PDF converter

Its differentiation is consolidation.

Instead of:

```text
Bank converter
↓
Invoice OCR tool
↓
GST tool
↓
Tally
↓
Excel
↓
Capital gains tool
↓
Manual missing-document checks
```

CA Unpacker becomes the preparation layer connecting everything.

It does not need to replace Tally or tax filing software. It prepares the inputs for them.

## Will CAs pay?

Potentially yes, but the key metric is not feature count.

Measure:

> **staff minutes saved per client**

Example:

```text
Manual preparation:      2 hours
CA Unpacker + review:    15 minutes
Time saved:              1 hr 45 min
```

If that happens consistently across dozens of clients, the ROI becomes obvious.

The best validation is to get several real CA firms to provide one anonymized client dump exactly as they normally receive it, without cleaning it first, then measure:

- Manual time normally required
- CA Unpacker processing + review time
- What breaks
- What still requires human work

## Development cost

For an initial MVP/pilot, costs can remain very low because the core stack can use:

- Python — free
- SQLite — free
- Tesseract — free
- PyInstaller — free
- Inno Setup — free
- openpyxl — free
- GitHub — free tier
- Local processing — no cloud compute bill
- No LLM API bill

Using a coding assistant such as Cursor/Codex, an **under ₹3,000** prototype/pilot budget is plausible, potentially much less.

Costs rise later for:

- Code signing
- Authentication backend
- Domain/website
- Commercial distribution
- Testing
- Support
- Legal/privacy documentation

## Strongest product vision

The client sends chaos:

```text
Bank PDFs
Invoices
GST files
Tally
Broker reports
Scans
Excel files
Random documents
```

CA Unpacker turns it into:

```text
             CLIENT DUMP
                  ↓
              IDENTIFY
                  ↓
              ORGANIZE
                  ↓
               EXTRACT
                  ↓
              NORMALIZE
                  ↓
               VALIDATE
                  ↓
            CROSS-CHECK
                  ↓
             FIND GAPS
                  ↓
          FLAG EXCEPTIONS
                  ↓
       CA-READY WORKING PACK
                  ↓
          CA DOES THE ACTUAL
         PROFESSIONAL WORK
```

## Core product rule

> **CA Unpacker should never silently ignore something it doesn't understand.**

Every input should end up clearly classified as one of:

- Processed successfully
- Needs review
- Missing/suspected missing
- Failed/unreadable
- Unclassified

The strongest version of the idea is therefore:

**local processing + one consolidated intake + deterministic reconciliation + explicit exception handling.**
