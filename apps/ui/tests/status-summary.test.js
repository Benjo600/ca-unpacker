"use strict";

const assert = require("node:assert/strict");
const {
  summarizeJobStatus,
  isReviewOutcome,
} = require("../status-summary.js");

const warnings = summarizeJobStatus({
  status: "done_with_warnings",
  outcome_counts: { processed: 2, needs_review: 1, failed: 0, unclassified: 1 },
});
assert.deepEqual(warnings, {
  tone: "warning",
  label: "Completed with warnings",
  text: "Completed with warnings: 2 processed, 1 needs review, 1 unclassified.",
});

const clean = summarizeJobStatus({
  status: "done",
  outcome_counts: { processed: 2, needs_review: 0, failed: 0, unclassified: 0 },
});
assert.equal(clean.tone, "success");
assert.equal(clean.label, "Completed");

const failed = summarizeJobStatus({
  status: "failed",
  outcome_counts: { processed: 1, needs_review: 0, failed: 1, unclassified: 0 },
});
assert.equal(failed.tone, "failure");
assert.equal(failed.text, "Processing failed: 1 processed, 1 failed.");

assert.equal(isReviewOutcome("needs_review"), true);
assert.equal(isReviewOutcome("failed"), true);
assert.equal(isReviewOutcome("unclassified"), true);
assert.equal(isReviewOutcome("processed"), false);

console.log("status-summary behavior tests passed");
