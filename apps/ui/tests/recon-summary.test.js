"use strict";

const assert = require("node:assert/strict");
const {
  hasRecon,
  reconCountsText,
  reconStatusLabel,
  reconInvoiceDisplay,
  filterReconRows,
  sortReconRows,
  reconReason,
  formatINR,
  reconMoneyChips,
  reconTotalsText,
  hasReconMissing,
  reconMissingText,
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

// --- search narrows rows on party, GSTIN or invoice number ---
const searchable = [
  { party: "Shakti Steels", gstin: "29AAJPS1120L1ZD", invoice_2b: "SS/778", invoice_books: "", status: "books_only" },
  { party: "Ganesh Packaging", gstin: "29AAGCG4545K1Z9", invoice_2b: "GP-2291", invoice_books: "GP2291", status: "matched" },
];
assert.equal(filterReconRows(searchable, "all", "shakti").length, 1);
assert.equal(filterReconRows(searchable, "all", "GP-2291")[0].party, "Ganesh Packaging");
assert.equal(filterReconRows(searchable, "all", "29AAJPS")[0].status, "books_only");
assert.equal(filterReconRows(searchable, "all", "   ").length, 2);
assert.equal(filterReconRows(searchable, "matched", "shakti").length, 0);

// --- exceptions sort by money, biggest first ---
const mixed = [
  { status: "amount_mismatch", amount_diff: 40, amount_2b: 23140, amount_books: 23100, party: "Royal Papers" },
  { status: "books_only", amount_diff: null, amount_2b: null, amount_books: 18240, party: "Shakti Steels" },
  { status: "portal_only", amount_diff: null, amount_2b: 6780, amount_books: null, party: "Bharath Logistics" },
  { status: "matched", amount_diff: 0, amount_2b: 118000, amount_books: 118000, party: "Anand Textiles" },
];
// --- exceptions sort by money, biggest first (matched rows stay in the list) ---
assert.deepEqual(
  sortReconRows(filterReconRows(mixed, "all", "")).map((row) => row.party),
  ["Shakti Steels", "Bharath Logistics", "Royal Papers", "Anand Textiles"]
);
assert.deepEqual(
  sortReconRows(filterReconRows(mixed, "unmatched", "")).map((row) => row.party),
  ["Shakti Steels", "Bharath Logistics"]
);

// --- reasons flow through as-is ---
assert.equal(reconReason({ reason: " amounts differ by 40.00 " }), "amounts differ by 40.00");
assert.equal(reconReason(null), "");
assert.equal(reconReason({}), "");

// --- rupees, Indian grouping ---
assert.equal(formatINR(0), "₹0.00");
assert.equal(formatINR(1180), "₹1,180.00");
assert.equal(formatINR(11800000), "₹1,18,00,000.00");
assert.equal(formatINR(-42.5), "-₹42.50");
assert.equal(formatINR("not-a-number"), "₹—");

// --- money chips: five figures, diff + credit figures clickable ---
const chips = reconMoneyChips({
  portal_total: 600,
  books_total: 300,
  gap: 300,
  credit_at_risk: 300,
  unsupported_credit: 0,
});
assert.equal(chips.length, 5);
assert.deepEqual(
  chips.map((chip) => chip.filter),
  ["all", "all", "amount_mismatch", "unmatched", "unmatched"]
);
assert.deepEqual(
  chips.map((chip) => formatINR(chip.value)),
  ["₹600.00", "₹300.00", "₹300.00", "₹300.00", "₹0.00"]
);
assert.equal(
  reconTotalsText({ portal_total: 600, books_total: 300, gap: 300, credit_at_risk: 300 }),
  "On portal ₹600.00 · In books ₹300.00 · Difference ₹300.00 · Credit at risk ₹300.00"
);

// --- missing recon explains itself ---
assert.equal(hasReconMissing({}), false);
assert.equal(hasReconMissing({ recon_missing: "no_gstr_2b" }), true);
assert.match(
  reconMissingText({ recon_missing: "no_gstr_2b" }),
  /GSTR-2B JSON is missing/
);
assert.match(
  reconMissingText({ recon_missing: "no_purchase_rows" }),
  /purchase register/
);
assert.equal(reconMissingText({ recon_missing: "something-else" }), "");
assert.equal(reconMissingText(null), "");

console.log("recon-summary behavior tests passed");
