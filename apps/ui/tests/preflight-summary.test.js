"use strict";

const assert = require("node:assert/strict");
const {
  blockedHeadline,
  issueText,
  levelLabel,
  preflightBlocked,
  summaryText,
  visibleIssues,
} = require("../preflight-summary.js");

const clean = {
  ok: true,
  blocked: false,
  counts: { blocking: 0, warnings: 0 },
  blocking: [],
  warnings: [],
};
assert.equal(preflightBlocked({ preflight: clean }), false);
assert.equal(preflightBlocked({}), false);
assert.equal(preflightBlocked(null), false);
assert.equal(summaryText(clean), "");

const warned = {
  ok: true,
  blocked: false,
  counts: { blocking: 0, warnings: 2 },
  blocking: [],
  warnings: [
    {
      level: "warning",
      code: "hsn_missing",
      message: "Missing HSN code on 2 rows.",
      count: 2,
      samples: [{ file: "Batch_Jul.xlsx", row: 4, detail: "invoice PUR-1 in purchase register" }],
    },
    {
      level: "warning",
      code: "bank_unreconciled",
      message: "1 bank statement did not reconcile.",
      count: 1,
      samples: [],
    },
  ],
};
assert.equal(summaryText(warned), "2 preflight warnings");
assert.equal(visibleIssues({ preflight: warned }).length, 2);
assert.equal(
  issueText(warned.warnings[0]),
  "Missing HSN code on 2 rows. · Batch_Jul.xlsx row 4 · invoice PUR-1 in purchase register"
);
assert.equal(issueText(warned.warnings[1]), "1 bank statement did not reconcile.");
assert.equal(levelLabel("warning"), "WARNING");

const blocked = {
  ok: false,
  blocked: true,
  counts: { blocking: 1, warnings: 1 },
  blocking: [
    {
      level: "blocking",
      code: "no_usable_rows",
      message: "This period has no usable rows, so nothing was packed.",
      count: 0,
      samples: [],
    },
  ],
  warnings: warned.warnings,
};
assert.equal(preflightBlocked({ preflight: blocked }), true);
assert.equal(summaryText(blocked), "stopped · 1 blocking problem");
assert.equal(
  blockedHeadline(blocked),
  "Stopped before writing · This period has no usable rows, so nothing was packed."
);
assert.equal(visibleIssues({ preflight: blocked }).length, 3);
assert.equal(levelLabel("blocking"), "BLOCKED");
assert.equal(blockedHeadline({ blocking: [] }), "Stopped before writing. Nothing was packed.");

console.log("preflight-summary behavior tests passed");
