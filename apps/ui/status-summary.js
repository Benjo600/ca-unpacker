(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAStatusSummary = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  const OUTCOMES = ["processed", "needs_review", "failed", "unclassified"];
  const REVIEW_OUTCOMES = new Set(["needs_review", "failed", "unclassified"]);

  function outcomeCounts(counts) {
    const normalized = {};
    for (const outcome of OUTCOMES) normalized[outcome] = Number(counts && counts[outcome]) || 0;
    return normalized;
  }

  function outcomeLabel(outcome) {
    return {
      processed: "Processed",
      needs_review: "Needs review",
      failed: "Failed",
      unclassified: "Unclassified",
    }[outcome] || "Unclassified";
  }

  function isReviewOutcome(outcome) {
    return REVIEW_OUTCOMES.has(outcome);
  }

  function countsText(counts) {
    return OUTCOMES
      .filter((outcome) => counts[outcome] > 0)
      .map((outcome) => `${counts[outcome]} ${outcomeLabel(outcome).toLowerCase()}`)
      .join(", ");
  }

  function summarizeJobStatus(job) {
    const counts = outcomeCounts(job && job.outcome_counts);
    const countSummary = countsText(counts) || "no files";
    if (job && job.status === "done") {
      return { tone: "success", label: "Completed", text: `Completed: ${countSummary}.` };
    }
    if (job && job.status === "done_with_warnings") {
      return {
        tone: "warning",
        label: "Completed with warnings",
        text: `Completed with warnings: ${countSummary}.`,
      };
    }
    if (job && job.status === "failed") {
      return {
        tone: "failure",
        label: "Processing failed",
        text: `Processing failed: ${countSummary}.`,
      };
    }
    return { tone: "progress", label: "Processing", text: "Processing files…" };
  }

  function summarizeFiles(files) {
    const counts = outcomeCounts();
    for (const file of files || []) {
      const outcome = OUTCOMES.includes(file.parse_outcome) ? file.parse_outcome : "unclassified";
      counts[outcome] += 1;
    }
    if (!(files || []).length) return { tone: "neutral", label: "No files", text: "0 files" };
    const hasWarnings = counts.needs_review || counts.unclassified || counts.failed;
    const status = !hasWarnings
      ? "done"
      : counts.failed && !counts.processed && !counts.needs_review && !counts.unclassified
        ? "failed"
        : "done_with_warnings";
    return summarizeJobStatus({ status, outcome_counts: counts });
  }

  return { isReviewOutcome, outcomeCounts, outcomeLabel, summarizeFiles, summarizeJobStatus };
});
