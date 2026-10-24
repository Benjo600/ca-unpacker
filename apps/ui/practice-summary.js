(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAPracticeSummary = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  const STATUS_KEYS = [
    "matched",
    "amount_mismatch",
    "review_required",
    "left_only",
    "right_only",
    "duplicate",
  ];

  function labels(workflow) {
    return {
      left: (workflow && workflow.left_label) || "Left dataset",
      right: (workflow && workflow.right_label) || "Right dataset",
    };
  }

  function statusLabel(status, workflow) {
    const sides = labels(workflow);
    return {
      matched: "Matched",
      amount_mismatch: "Amount difference",
      review_required: "Review required",
      left_only: `Only in ${sides.left}`,
      right_only: `Only in ${sides.right}`,
      duplicate: "Duplicate candidate",
    }[status] || String(status || "");
  }

  function statusTone(status) {
    if (status === "matched") return "match";
    if (status === "amount_mismatch") return "mismatch";
    if (status === "review_required") return "review";
    if (status === "duplicate") return "duplicate";
    return "muted";
  }

  function focusText(record) {
    if (!record) return "";
    return [
      record.party,
      record.gstin,
      record.reference,
      record.normalized_reference,
      record.date,
      record.description,
      record.file_name,
      record.source,
      record.amount,
      record.tax,
      record.taxable,
    ]
      .filter((value) => value !== null && value !== undefined)
      .join(" ")
      .toLowerCase();
  }

  function rowSearchText(row) {
    return [
      focusText(row && row.left),
      focusText(row && row.right),
      (row && row.explanation) || "",
      (row && row.reason_code) || "",
      (row && row.status) || "",
    ]
      .join(" ")
      .toLowerCase();
  }

  function filterRows(rows, filter, query) {
    const list = Array.isArray(rows) ? rows : [];
    const needle = String(query || "").trim().toLowerCase();
    return list.filter((row) => {
      const status = row && row.status;
      if (filter === "matched" && status !== "matched") return false;
      if (filter === "review" && status !== "review_required") return false;
      if (filter === "amount_mismatch" && status !== "amount_mismatch") return false;
      if (
        filter === "unmatched" &&
        status !== "left_only" &&
        status !== "right_only"
      ) {
        return false;
      }
      if (filter === "duplicate" && status !== "duplicate") return false;
      if (needle && !rowSearchText(row).includes(needle)) return false;
      return true;
    });
  }

  function countsText(counts, workflow) {
    const values = counts || {};
    const parts = STATUS_KEYS.filter((key) => Number(values[key]) > 0).map(
      (key) => `${statusLabel(key, workflow)} ${Number(values[key])}`
    );
    return parts.length ? parts.join(" · ") : "No rows";
  }

  function openItems(counts) {
    const values = counts || {};
    return STATUS_KEYS.filter((key) => key !== "matched").reduce(
      (total, key) => total + (Number(values[key]) || 0),
      0
    );
  }

  function reviewItems(counts) {
    const values = counts || {};
    return (
      (Number(values.amount_mismatch) || 0) +
      (Number(values.review_required) || 0) +
      (Number(values.duplicate) || 0)
    );
  }

  function jobStatusLabel(status) {
    return {
      done: "Completed",
      done_with_warnings: "Completed with warnings",
      failed: "Failed",
      queued: "Queued",
      routing: "Sorting",
      parsing: "Parsing",
    }[status] || String(status || "Unknown");
  }

  return {
    STATUS_KEYS,
    countsText,
    filterRows,
    jobStatusLabel,
    openItems,
    reviewItems,
    statusLabel,
    statusTone,
  };
});
