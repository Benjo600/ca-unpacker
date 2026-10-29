(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAPreflightSummary = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function preflightOf(pack) {
    const preflight = pack && pack.preflight;
    return preflight && typeof preflight === "object" ? preflight : null;
  }

  function preflightBlocked(pack) {
    const preflight = preflightOf(pack);
    return Boolean(preflight && preflight.blocked);
  }

  function blockingIssues(preflight) {
    return (preflight && preflight.blocking) || [];
  }

  function warningIssues(preflight) {
    return (preflight && preflight.warnings) || [];
  }

  function plural(count, word) {
    return `${count} ${word}${count === 1 ? "" : "s"}`;
  }

  function summaryText(preflight) {
    const blocking = blockingIssues(preflight).length;
    const warnings = warningIssues(preflight).length;
    if (blocking) return `stopped · ${plural(blocking, "blocking problem")}`;
    if (warnings) return `${plural(warnings, "preflight warning")}`;
    return "";
  }

  function blockedHeadline(preflight) {
    const first = blockingIssues(preflight)[0];
    if (!first) return "Stopped before writing. Nothing was packed.";
    return `Stopped before writing · ${first.message}`;
  }

  function levelLabel(level) {
    return level === "blocking" ? "BLOCKED" : "WARNING";
  }

  function sampleText(samples) {
    const first = (samples || [])[0];
    if (!first) return "";
    let text = first.file || "";
    if (first.row) text = text ? `${text} row ${first.row}` : `row ${first.row}`;
    if (first.detail) text = text ? `${text} · ${first.detail}` : String(first.detail);
    return text;
  }

  function issueText(issue) {
    const message = (issue && issue.message) || "";
    const sample = sampleText(issue && issue.samples);
    return sample ? `${message} · ${sample}` : message;
  }

  function visibleIssues(pack) {
    const preflight = preflightOf(pack);
    if (!preflight) return [];
    return preflightBlocked(pack)
      ? blockingIssues(preflight).concat(warningIssues(preflight))
      : warningIssues(preflight);
  }

  return {
    blockedHeadline,
    blockingIssues,
    issueText,
    levelLabel,
    preflightBlocked,
    preflightOf,
    sampleText,
    summaryText,
    visibleIssues,
    warningIssues,
  };
});
