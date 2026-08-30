# CA Unpacker Full Product Design

## Goal

Evolve CA Unpacker into a modular, local-first preparation tool while preserving the working Stage 1–7 parsers and the invariant that every imported file is explicitly accounted for.

## Binding Product Rules

- Every imported file ends as `processed`, `needs_review`, `failed`, or `unclassified`.
- A job may be `done`, `done_with_warnings`, or `failed`; recognized parser failures can never produce clean `done`.
- Original client files remain immutable and client document contents never leave the device.
- `.xlsx` and `.csv` are supported spreadsheet inputs; legacy `.xls` is unsupported.
- Tesseract is the mandatory local OCR baseline. PaddleOCR remains conditional on accuracy, packaging, and license gates.
- SQLite, Python, pywebview, and Excel outputs remain the product foundation.
- Software presents evidence and exceptions; the CA retains professional judgment.

## Delivery Sequence

1. Trust and release foundation.
2. Controlled CA pilot workspace.
3. Master reconciliation.
4. Completeness detection and client queries.
5. Parser profiles and capital gains.
6. Firm-scale queue and privacy-preserving commercial foundation.
7. Conditional OCR evaluation.

Each release must pass its automated and clean-machine gates before the next release is treated as externally shippable. Pricing, payment providers, and quota enforcement remain deferred until after pilot evidence.

