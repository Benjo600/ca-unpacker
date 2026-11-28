"use strict";

const assert = require("node:assert/strict");
const {
  FLAG_LABELS,
  flagLabel,
  flagList,
  approvalText,
  isInferredRow,
  money,
  dash,
  formatReconMoney,
  formatWhen,
  formatFileSize,
  countLabel,
  rowsLabel,
  looksLikeGstin,
  cropCaptionValue,
  observedText,
  thresholdText,
  severityClass,
  severityLabel,
  escapeHtml,
} = require("../format.js");

// ---- money / number formatting -------------------------------------------

assert.equal(money(1234.5), "1,234.50");
assert.equal(money(0), "0.00");
assert.equal(money(null), "—");
assert.equal(money(undefined), "—");
assert.equal(money(""), "—");
assert.equal(money("not a number"), "—");
// A three-letter code switches to the currency style.
assert.ok(money(1234.5, "INR").includes("1,234.50"));
assert.ok(money(1234.5, "INR").startsWith("INR"));
assert.ok(money(1234.5, "usd").startsWith("USD"));
// Junk codes fall back to the plain decimal format.
assert.equal(money(1234.5, "rupees"), "1,234.50");
assert.equal(money(1234.5, ""), "1,234.50");

assert.equal(formatReconMoney(0), "₹0.00");
assert.equal(formatReconMoney(null), "₹0.00");
assert.equal(formatReconMoney("nope"), "₹0.00");
assert.equal(formatReconMoney(1234.5), "₹1,234.50");
assert.equal(formatReconMoney(-1234.5), "₹-1,234.50");

assert.equal(formatFileSize(0), "");
assert.equal(formatFileSize(undefined), "");
assert.equal(formatFileSize(512), "512 B");
assert.equal(formatFileSize(2048), "2.0 KB");
assert.equal(formatFileSize(20 * 1024), "20 KB");
assert.equal(formatFileSize(5 * 1024 * 1024), "5.0 MB");

assert.equal(rowsLabel(0), "0 rows");
assert.equal(rowsLabel(1), "1 row");
assert.equal(rowsLabel(3), "3 rows");
assert.equal(rowsLabel("2"), "2 rows");
assert.equal(rowsLabel(null), "0 rows");

assert.equal(countLabel(0, "file"), "0 files");
assert.equal(countLabel(1, "file"), "1 file");
assert.equal(countLabel(2, "file"), "2 files");
assert.equal(countLabel(1, "line"), "1 line");
assert.equal(countLabel(1, "person", "people"), "1 person");
assert.equal(countLabel(4, "person", "people"), "4 people");

assert.equal(dash(null), "—");
assert.equal(dash(undefined), "—");
assert.equal(dash(""), "—");
assert.equal(dash(0), "0");
assert.equal(dash("abc"), "abc");

assert.equal(looksLikeGstin("27AAPFU0939F1ZV"), true);
assert.equal(looksLikeGstin(" 27AAPFU0939F1ZV "), true);
assert.equal(looksLikeGstin("27AAPFU0939F1Z"), false);
assert.equal(looksLikeGstin(""), false);
assert.equal(looksLikeGstin(null), false);

assert.equal(cropCaptionValue("supplier_gstin", " 27AAPFU0939F1ZV "), "27AAPFU0939F1ZV");
assert.equal(cropCaptionValue("supplier_gstin", null), "—");
assert.equal(cropCaptionValue("taxable_value", "27AAPFU0939F1ZV"), "27AAPFU0939F1ZV");
assert.ok(cropCaptionValue("taxable_value", 100, "INR").includes("100.00"));
assert.equal(cropCaptionValue("taxable_value", null), "—");

assert.equal(severityClass("review"), "mismatch");
assert.equal(severityClass("check"), "unknown");
assert.equal(severityClass("info"), "mute");
assert.equal(severityLabel("review"), "Review");
assert.equal(severityLabel("check"), "Check");
assert.equal(severityLabel("info"), "Note");

assert.equal(observedText(null), "");
assert.equal(
  observedText({ count: 2, total: 100, largest: 60 }),
  "2 line(s) · total 100.00 · largest 60.00"
);
assert.equal(observedText({ sales_lines: 4 }), "4 sales line(s)");
assert.equal(thresholdText(null), "");
assert.equal(
  thresholdText({ amount: 100, enhanced: 200, basis: "turnover", rate: "18%", as_of: "2026-04-01" }),
  "100.00 · enhanced 200.00 · turnover · 18% · 2026-04-01"
);

// formatWhen is locale/timezone dependent, so only its guards are pinned.
assert.equal(formatWhen(null), "");
assert.equal(formatWhen(""), "");
assert.equal(formatWhen("not a date"), "");
assert.ok(formatWhen("2026-04-01T10:00:00Z").length > 0);

assert.equal(escapeHtml("<a & b>"), "&lt;a &amp; b&gt;");
assert.equal(escapeHtml(5), "5");

// ---- flag labels ---------------------------------------------------------

assert.equal(FLAG_LABELS.inferred_from_balance, "Inferred from balance — needs approval");
assert.equal(flagLabel("currency_unknown"), "Currency not stated");
assert.equal(flagLabel("inferred_from_balance"), "Inferred from balance — needs approval");
assert.equal(flagLabel("date_missing"), "Date missing");
assert.equal(flagLabel(" sap_export_note "), "SAP export note");
assert.equal(flagLabel("brand_new_code"), "brand new code");
assert.equal(flagLabel(""), "");
assert.equal(flagLabel(null), "");

assert.deepEqual(flagList({ flags: [" a ", "b", ""] }), ["a", "b"]);
assert.deepEqual(flagList({ validation_flags: '["x"," y"]' }), ["x", "y"]);
assert.deepEqual(flagList({ flags: "a, b;c" }), ["a", "b", "c"]);
assert.deepEqual(flagList({ flags: [] }), []);
assert.deepEqual(flagList({}), []);
assert.deepEqual(flagList(null), []);

assert.equal(approvalText({ approval: "approved" }), "Approved — released into the pack");
assert.equal(approvalText({ approval: "REJECTED" }), "Left out of the pack");
assert.equal(
  approvalText({}),
  "Inferred from the balance gap — not in the statement"
);

assert.equal(isInferredRow({ needs_approval: true }), true);
assert.equal(isInferredRow({ flags: ["inferred_from_balance"] }), true);
assert.equal(isInferredRow({ flags: ["date_missing"] }), false);
assert.equal(isInferredRow({}), false);
assert.equal(isInferredRow(null), false);
