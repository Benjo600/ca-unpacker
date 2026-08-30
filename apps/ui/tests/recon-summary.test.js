"use strict";

const assert = require("node:assert/strict");
const {
  hasRecon,
  reconCountsText,
  reconStatusLabel,
  reconInvoiceDisplay,
  filterReconRows,
  gstrPreviewNote,
} = require("../recon-summary.js");

assert.equal(hasRecon(null), false);
assert.equal(hasRecon({}), false);
assert.equal(hasRecon({ recon: null }), false);
assert.equal(hasRecon({ recon: {} }), false);
assert.equal(hasRecon({ recon: { rows: [] } }), false);
assert.equal(
  hasRecon({
    recon: {
      counts: {
        matched: 0,
        books_only: 0,
        portal_only: 0,
        amount_mismatch: 0,
        likely: 0,
      },
      rows: [],
    },
  }),
  true
);
assert.equal(
  hasRecon({ recon: { rows: [{ status: "matched" }] } }),
  true
);

assert.equal(
  reconCountsText({
    matched: 3,
    books_only: 1,
    portal_only: 2,
    amount_mismatch: 1,
    likely: 0,
  }),
  "Matched 3 · Only in books 1 · Only in 2B 2 · Amount mismatch 1 · Likely 0"
);

assert.equal(reconStatusLabel("matched"), "Matched");
assert.equal(reconStatusLabel("books_only"), "Only in books");
assert.equal(reconStatusLabel("portal_only"), "Only in 2B");
assert.equal(reconStatusLabel("amount_mismatch"), "Amount mismatch");
assert.equal(reconStatusLabel("likely"), "Likely (confirm)");

assert.equal(reconInvoiceDisplay({ invoice_2b: "2B-9", invoice_books: "BK-1" }), "2B-9");
assert.equal(reconInvoiceDisplay({ invoice_2b: "", invoice_books: "BK-1" }), "BK-1");
assert.equal(reconInvoiceDisplay({ invoice_books: "BK-1" }), "BK-1");

const rows = [
  { status: "matched" },
  { status: "books_only" },
  { status: "portal_only" },
  { status: "amount_mismatch" },
  { status: "likely" },
];
assert.equal(filterReconRows(rows, "all").length, 5);
assert.deepEqual(
  filterReconRows(rows, "matched").map((row) => row.status),
  ["matched"]
);
assert.deepEqual(
  filterReconRows(rows, "unmatched").map((row) => row.status),
  ["books_only", "portal_only"]
);
assert.deepEqual(
  filterReconRows(rows, "amount_mismatch").map((row) => row.status),
  ["amount_mismatch"]
);
assert.deepEqual(
  filterReconRows(rows, "likely").map((row) => row.status),
  ["likely"]
);

assert.equal(
  gstrPreviewNote(false),
  "Open the GSTR Excel for the full register. Match columns stay empty until reconciliation."
);
assert.equal(
  gstrPreviewNote(true),
  "Open the GSTR Excel for the full register. Match columns filled in GSTR Excel when a master grid exists."
);

console.log("recon-summary behavior tests passed");
