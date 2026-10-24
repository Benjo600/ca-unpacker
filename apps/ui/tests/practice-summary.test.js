"use strict";

const assert = require("node:assert/strict");
const {
  countsText,
  filterRows,
  jobStatusLabel,
  openItems,
  reviewItems,
  statusLabel,
  statusTone,
} = require("../practice-summary.js");

const workflow = { left_label: "GSTR-2B", right_label: "Purchase register" };

assert.equal(statusLabel("matched", workflow), "Matched");
assert.equal(statusLabel("left_only", workflow), "Only in GSTR-2B");
assert.equal(statusLabel("right_only", workflow), "Only in Purchase register");
assert.equal(statusLabel("review_required", workflow), "Review required");
assert.equal(statusTone("matched"), "match");
assert.equal(statusTone("amount_mismatch"), "mismatch");
assert.equal(statusTone("review_required"), "review");
assert.equal(statusTone("duplicate"), "duplicate");

const rows = [
  {
    status: "matched",
    left: { reference: "INV-1", party: "Acme" },
    right: { reference: "INV/1", party: "Acme Traders" },
    explanation: "Values agree.",
  },
  {
    status: "amount_mismatch",
    left: { reference: "INV-2", party: "Beta" },
    right: { reference: "INV-2" },
    explanation: "Difference is 20.00.",
  },
  {
    status: "review_required",
    left: { party: "Gamma" },
    right: { party: "Gamma" },
    explanation: "Tax differs.",
  },
  {
    status: "left_only",
    left: { reference: "ONLY-LEFT" },
    right: null,
    explanation: "No counterpart.",
  },
  {
    status: "right_only",
    left: null,
    right: { reference: "ONLY-RIGHT" },
    explanation: "No counterpart.",
  },
  {
    status: "duplicate",
    left: { reference: "DUP" },
    right: null,
    explanation: "Duplicate.",
  },
];

assert.equal(filterRows(rows, "all", "").length, 6);
assert.deepEqual(
  filterRows(rows, "matched", "").map((row) => row.status),
  ["matched"]
);
assert.deepEqual(
  filterRows(rows, "review", "").map((row) => row.status),
  ["review_required"]
);
assert.deepEqual(
  filterRows(rows, "amount_mismatch", "").map((row) => row.status),
  ["amount_mismatch"]
);
assert.deepEqual(
  filterRows(rows, "unmatched", "").map((row) => row.status),
  ["left_only", "right_only"]
);
assert.deepEqual(
  filterRows(rows, "duplicate", "").map((row) => row.status),
  ["duplicate"]
);
assert.deepEqual(
  filterRows(rows, "all", "only-right").map((row) => row.status),
  ["right_only"]
);
assert.deepEqual(
  filterRows(rows, "all", "acme").map((row) => row.status),
  ["matched"]
);

const counts = {
  matched: 4,
  amount_mismatch: 2,
  review_required: 1,
  left_only: 3,
  right_only: 1,
  duplicate: 2,
};
assert.equal(
  countsText(counts, workflow),
  "Matched 4 · Amount difference 2 · Review required 1 · Only in GSTR-2B 3 · Only in Purchase register 1 · Duplicate candidate 2"
);
assert.equal(openItems(counts), 9);
assert.equal(reviewItems(counts), 5);
assert.equal(jobStatusLabel("done_with_warnings"), "Completed with warnings");
assert.equal(jobStatusLabel("parsing"), "Parsing");

console.log("practice-summary behavior tests passed");
