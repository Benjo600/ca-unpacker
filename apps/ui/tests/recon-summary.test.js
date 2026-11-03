"use strict";

const assert = require("node:assert/strict");
const {
  DECISION_REASONS,
  decisionLabel,
  decisionReasonLabel,
  decisionCountsText,
  decisionMoneyText,
  isDecidedRow,
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

// --- ready-made decision reasons, in the shipped order ---
assert.deepEqual(
  DECISION_REASONS.map((reason) => reason.code),
  ["rate_difference", "credit_note_pending", "supplier_not_filed", "wrong_gstin", "other"]
);
assert.deepEqual(
  DECISION_REASONS.map((reason) => reason.label),
  ["Rate difference", "Credit note pending", "Supplier has not filed", "Wrong GSTIN", "Something else"]
);
assert.equal(decisionReasonLabel("wrong_gstin"), "Wrong GSTIN");
assert.equal(decisionReasonLabel("nope"), "");

// --- decision labels ---
assert.equal(decisionLabel("accepted"), "Accepted");
assert.equal(decisionLabel("rejected"), "Rejected");
assert.equal(decisionLabel("noted"), "Noted");
assert.equal(decisionLabel(""), "Not decided");
assert.equal(decisionLabel(null), "Not decided");
assert.equal(decisionLabel("something-else"), "Not decided");

// --- who still owes a decision ---
assert.equal(isDecidedRow({ decision: "accepted" }), true);
assert.equal(isDecidedRow({ decision: "noted" }), true);
assert.equal(isDecidedRow({ decision: "" }), false);
assert.equal(isDecidedRow({ decision: "   " }), false);
assert.equal(isDecidedRow({}), false);
assert.equal(isDecidedRow(null), false);

// --- decision counts line ---
assert.equal(
  decisionCountsText({
    counts: { accepted: 3, rejected: 1, noted: 2, undecided: 5, new: 1, exceptions: 6 },
  }),
  "Accepted 3 · Rejected 1 · Noted 2 · Still to decide 5 · New 1"
);
assert.equal(
  decisionCountsText({ counts: { accepted: 0, rejected: 0, noted: 0, undecided: 0, new: 0 } }),
  "Accepted 0 · Rejected 0 · Noted 0 · Still to decide 0"
);
assert.equal(
  decisionCountsText({ counts: { accepted: 0, rejected: 0, noted: 0, undecided: 0, new: 4 } }),
  "Accepted 0 · Rejected 0 · Noted 0 · Still to decide 0 · New 4"
);
assert.equal(
  decisionCountsText(null),
  "Accepted 0 · Rejected 0 · Noted 0 · Still to decide 0"
);

// --- money already decided vs money still at stake ---
assert.equal(
  decisionMoneyText({
    money: { accepted: 1000, rejected: 500, noted: 500, undecided: 2000, at_stake: 4000 },
  }),
  "Decided ₹2,000.00 of ₹4,000.00 still worth deciding"
);
assert.equal(
  decisionMoneyText({ money: { accepted: 0, rejected: 0, noted: 0, at_stake: 0 } }),
  "Decided ₹0.00 · nothing still worth deciding"
);
assert.match(decisionMoneyText(null), /^Decided ₹0\.00/);

// --- to_do and decided filters ---
const decisionRows = [
  { status: "amount_mismatch", invoice_2b: "A-1", needs_decision: true, decision: "" },
  { status: "books_only", invoice_2b: "A-2", needs_decision: true, decision: "accepted" },
  { status: "portal_only", invoice_2b: "A-3", needs_decision: true, decision: "rejected" },
  { status: "matched", invoice_2b: "A-4", needs_decision: false, decision: "" },
  { status: "likely", invoice_2b: "A-5", needs_decision: true, decision: "noted" },
  { status: "matched", invoice_2b: "A-6", needs_decision: false, decision: "" },
];
assert.deepEqual(
  filterReconRows(decisionRows, "to_do").map((row) => row.invoice_2b),
  ["A-1"]
);
assert.deepEqual(
  filterReconRows(decisionRows, "decided").map((row) => row.invoice_2b),
  ["A-2", "A-3", "A-5"]
);
assert.deepEqual(
  filterReconRows(decisionRows, "decided", "a-3").map((row) => row.invoice_2b),
  ["A-3"]
);
assert.equal(filterReconRows(decisionRows, "to_do", "a-4").length, 0);
assert.equal(filterReconRows(decisionRows, "all").length, 6);
// A-1 is amount_mismatch, which the older "unmatched" view does not include.
assert.deepEqual(
  filterReconRows(decisionRows, "unmatched").map((row) => row.invoice_2b),
  ["A-2", "A-3"]
);

console.log("recon-summary behavior tests passed");
