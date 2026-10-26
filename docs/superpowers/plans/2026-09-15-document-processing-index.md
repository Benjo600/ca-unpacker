# Document Processing Hardening - Plan Index

Date: 2026-09-15

This index ties together the plans that make the CA Unpacker document-processing backend safe on
real, unpredictable documents. It records the governing contract and the order of work.

## Governing contract

No parser can guarantee correctness on open-ended layouts. The achievable and required guarantee is:

> **Every extraction is either self-verified or explicitly flagged as uncertain. Silent wrong
> output is zero.**

This aligns with the binding rules already in the repository:

- `BUILD-PLAN.md` section 10: never auto-correct a GSTIN or an amount; flags and source crops only.
- `docs/superpowers/specs/2026-08-17-ca-unpacker-full-product-design.md`: every imported file ends
  as `processed`, `needs_review`, `failed`, or `unclassified`; recognized parser failures never
  produce a clean `done`.
- `AUDIT-FINDINGS-2026-08-16.md`: silent omission is unacceptable; make failures impossible to hide.

For bank statements the contract is enforceable because the numbers self-check
(`balance[i] = balance[i-1] - debit[i] + credit[i]` plus the printed closing balance). The
extraction layer must reconstruct faithfully and prove or doubt the result.

## Document predictability

| Input | Predictability | Why |
|---|---|---|
| GSTR-1/2B/3B JSON | High | Official portal schema |
| Zoho CSV/XLSX | High | Vendor-controlled headers |
| Tally XML/zip | Medium | Structured, many voucher shapes |
| Digital bank PDFs | Medium | Endless layouts, but self-checking |
| Invoice PDFs/images | Low | Every supplier, every template |
| Scanned/photographed/handwritten | Very low | OCR noise on top of all of the above |

## Plan order

1. **Top-class PDF parser** - `2026-09-15-top-class-pdf-parser.md`
   Faithful extraction: canonical document model, one coordinate space, real table-cell
   provenance, scored table cascade, restored and per-page OCR, extraction diagnostics, and a
   corpus scorecard. This is the foundation every parser depends on.
2. **Backend document-processing fixes** - `2026-09-15-backend-document-processing-fixes.md`
   Parser-level correctness on top of that foundation: bank money/date/direction, invoice field
   selection, GSTR/Tally/Zoho faithfulness, classifier and password flow, output writer
   integrity, and pipeline honesty.

## Why this order

The parser fixes (sign handling, zero-row MATCH, phantom rows, invoice tax) are what make the
self-check trustworthy: without them the balance equation can be faked. But those fixes need a
faithful extraction layer to operate on. Build the foundation first, then the parser fixes, then
prove both against a real corpus.

## Recommended first cut

Smallest set that stops confidently wrong output:

- PDF parser: Workstreams 1-3 (model, coordinates, faithful text).
- Backend: tasks 1.1, 1.2, 1.3, 1.6, 2.1, 2.2, 5.1, 5.2, 4.1.

## Open decisions

- **Architecture:** hybrid engine policy versus Docling-centric. Recommend hybrid.
- **Model:** extend existing dataclasses versus a new IR module with an adapter. Recommend extend.
- **Table engine:** scored cascade (pdfplumber, PyMuPDF, Docling TableFormer). Recommend cascade.
- **Corpus:** real anonymized samples are required before any accuracy claim.
