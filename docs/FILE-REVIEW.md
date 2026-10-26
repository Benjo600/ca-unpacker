# Client file review

Each period pack carries a `File_Review.xlsx` and a File review card in the dump
tray. It answers two questions the other sheets do not:

1. **Is this client's file complete for their profession?** — the checklist.
2. **Do the documents agree with each other?** — the cross-checks.

It runs only for clients with a profile, and only when the period produced at
least one other output. It never posts anything and never concludes anything:
every line states what was seen, why it is there, and what the CA should do.

## The checklist

Each profession pack lists the documents a clean monthly file usually contains,
graded **essential** or **recommended**. Curated packs exist for `doctor`,
`trader_wholesale` / `trader_retail`, `consultant` and `contractor`; every other
profession (including custom) gets the generic pack. GST-registered clients
additionally get GSTR-1 / 2B / 3B as essentials.

Statuses, per item:

| Status | Meaning |
| --- | --- |
| `verified` | A document of that type was added and rows were extracted from it this period. |
| `attached` | A file of that type is in the pack but nothing could be read from it — or the document type is only recognisable by file name (TDS certificates, rent agreements, salary registers, stock statements, labour agreements). File-name matches always say so. |
| `missing` | Nothing of that type is in the period. If unknown files sit in Needs review, the evidence line says so. |

Escalation: a recommended document becomes **essential** for the period when the
treatment checks or the money rows make it the cross-check — e.g. a 194I rent
flag upgrades the rent agreement, and a salary payment in the bank rows upgrades
the salary register.

## The cross-checks

Run only when both sides are present in the pack (absence is the checklist's
job, not a false alarm):

| Check | Compares |
| --- | --- |
| `review_purchases_vs_2b` | Purchase register total vs GSTR-2B total (tolerance 0.5% of the larger side; review-level beyond 10% or ₹1 lakh). Samples come from the reconciliation grid when one exists. |
| `review_sales_vs_gstr1` | Books sales vs GSTR-1 outward total. |
| `check_sales_vs_bank` | Bank credits vs booked sales, as a prompt only (outside 0.5x–2x). |
| `check_supplier_gstin_conflict` | Same supplier name under two GSTINs, or one GSTIN under two names. |
| `check_duplicate_invoice` | Same supplier + bill number repeated inside one register. |
| `check_statement_gap` | A hole of 25+ days between bank transaction dates. |
| `check_cash_payments` / `check_cash_receipts` | Cash-word bank rows at or above ₹10,000 (payments) / ₹2,00,000 (single receipts). |

## Readiness

`ready` — nothing missing-essential and no cross-check findings.
`check` — a recommended document is missing, a document is attached-but-unread,
or a check-level finding exists.
`gaps` — an essential document is missing or a review-level finding exists.

## Engine flow

```
resolve_profile(client)
        ↓
evaluate_file_review(profile, files, rows from every source, treatment flags)
        ↓
File_Review.xlsx + pack_summary.json["file_review"]
        ↓
desktop get_period_pack → File review card above the treatment card
```

After editing a profile, old packs keep their old review until re-parsed, the
same as treatment notes.

## Tests

- `apps/engine/tests/test_file_review.py` — catalog shape, checklist statuses,
  GST gating, escalations, every cross-check, readiness, and two end-to-end
  pack tests.
