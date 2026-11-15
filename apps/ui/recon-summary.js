(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAReconSummary = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  const STATUS_LABELS = {
    matched: "Matched",
    books_only: "Only in books",
    portal_only: "Only in 2B",
    amount_mismatch: "Amount mismatch",
    likely: "Likely (confirm)",
    tax_mismatch: "Tax differs",
    duplicate: "Duplicate",
    split_merged: "Split or merged",
    credit_note: "Credit note",
  };

  // Every status that is not a clean match. "unmatched" means all of these.
  const UNMATCHED_STATUSES = [
    "books_only",
    "portal_only",
    "amount_mismatch",
    "likely",
    "tax_mismatch",
    "duplicate",
    "split_merged",
    "credit_note",
  ];

  const DECISION_REASONS = [
    { code: "rate_difference", label: "Rate difference" },
    { code: "credit_note_pending", label: "Credit note pending" },
    { code: "supplier_not_filed", label: "Supplier has not filed" },
    { code: "wrong_gstin", label: "Wrong GSTIN" },
    { code: "other", label: "Something else" },
  ];

  const DECISION_LABELS = {
    accepted: "Accepted",
    rejected: "Rejected",
    noted: "Noted",
  };

  function decisionLabel(value) {
    const key = value == null ? "" : String(value).trim();
    return DECISION_LABELS[key] || "Not decided";
  }

  function isDecidedRow(row) {
    if (!row) return false;
    const decision = row.decision == null ? "" : String(row.decision).trim();
    return decision !== "";
  }

  function decisionReasonLabel(code) {
    const key = code == null ? "" : String(code).trim();
    for (const reason of DECISION_REASONS) {
      if (reason.code === key) return reason.label;
    }
    return "";
  }

  function decisionCountsText(decisions) {
    const counts = (decisions && decisions.counts) || {};
    const parts = [
      `Accepted ${Number(counts.accepted) || 0}`,
      `Rejected ${Number(counts.rejected) || 0}`,
      `Noted ${Number(counts.noted) || 0}`,
      `Still to decide ${Number(counts.undecided) || 0}`,
    ];
    const fresh = Number(counts.new) || 0;
    if (fresh > 0) parts.push(`New ${fresh}`);
    return parts.join(" · ");
  }

  function decisionMoneyText(decisions) {
    const money = (decisions && decisions.money) || {};
    const decided =
      (Number(money.accepted) || 0) + (Number(money.rejected) || 0) + (Number(money.noted) || 0);
    const atStake = Number(money.at_stake) || 0;
    if (atStake <= 0) return `Decided ${formatINR(decided)} · nothing still worth deciding`;
    return `Decided ${formatINR(decided)} of ${formatINR(atStake)} still worth deciding`;
  }

  function hasRecon(pack) {
    const recon = pack && pack.recon;
    if (!recon) return false;
    const counts = recon.counts;
    const rows = recon.rows;
    if (counts && typeof counts === "object") return true;
    return Array.isArray(rows) && rows.length > 0;
  }

  function reconCountsText(counts) {
    const n = counts || {};
    const parts = [
      `Matched ${Number(n.matched) || 0}`,
      `Only in books ${Number(n.books_only) || 0}`,
      `Only in 2B ${Number(n.portal_only) || 0}`,
      `Amount mismatch ${Number(n.amount_mismatch) || 0}`,
      `Likely ${Number(n.likely) || 0}`,
    ];
    const extras = [
      { key: "tax_mismatch", label: "Tax differs" },
      { key: "duplicate", label: "Duplicate" },
      { key: "split_merged", label: "Split or merged" },
      { key: "credit_note", label: "Credit notes" },
    ];
    for (const extra of extras) {
      const value = Number(n[extra.key]) || 0;
      if (value > 0) parts.push(`${extra.label} ${value}`);
    }
    return parts.join(" · ");
  }

  function toleranceText(tolerances) {
    const n = tolerances || {};
    const days = Number(n.days);
    const amount = Number(n.amount);
    const dayWord = Number.isFinite(days) && days > 0 ? `Dates ±${days} days` : "Dates same day";
    return `${dayWord} · Amounts ${formatINR(amount)}`;
  }

  function reconStatusLabel(status) {
    return STATUS_LABELS[status] || String(status || "");
  }

  function reconInvoiceDisplay(row) {
    const twoB = row && row.invoice_2b != null ? String(row.invoice_2b).trim() : "";
    if (twoB) return twoB;
    const books = row && row.invoice_books != null ? String(row.invoice_books).trim() : "";
    return books;
  }

  function filterReconRows(rows, filter, search) {
    let list = rows || [];
    if (filter === "matched") list = list.filter((row) => row.status === "matched");
    else if (filter === "unmatched") {
      list = list.filter((row) => UNMATCHED_STATUSES.includes(row.status));
    } else if (
      filter === "amount_mismatch" ||
      filter === "likely" ||
      filter === "tax_mismatch" ||
      filter === "duplicate" ||
      filter === "split_merged" ||
      filter === "credit_note"
    ) {
      list = list.filter((row) => row.status === filter);
    } else if (filter === "to_do") list = list.filter((row) => row.needs_decision === true && !isDecidedRow(row));
    else if (filter === "decided") list = list.filter((row) => isDecidedRow(row));
    const needle = String(search || "").trim().toLowerCase();
    if (!needle) return list.slice();
    return list.filter((row) => {
      const hay = [row.party, row.gstin, row.invoice_2b, row.invoice_books]
        .map((value) => (value == null ? "" : String(value).toLowerCase()))
        .join(" ");
      return hay.includes(needle);
    });
  }

  function rowMoneySize(row) {
    const value = Number(row && (row.amount_diff ?? row.amount_2b ?? row.amount_books));
    if (!Number.isFinite(value)) return -1;
    return Math.abs(value);
  }

  function sortReconRows(rows) {
    return (rows || []).slice().sort((left, right) => {
      const a = rowMoneySize(left);
      const b = rowMoneySize(right);
      if (a !== b) return b - a;
      return String(left.party || "").localeCompare(String(right.party || ""));
    });
  }

  function reconReason(row) {
    const reason = row && row.reason != null ? String(row.reason).trim() : "";
    return reason;
  }

  function formatINR(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "₹—";
    const sign = number < 0 ? "-" : "";
    const [intPart, decPart] = Math.abs(number).toFixed(2).split(".");
    let grouped;
    if (intPart.length <= 3) {
      grouped = intPart;
    } else {
      const head = intPart.slice(0, -3);
      const tail = intPart.slice(-3);
      const rest = [];
      let work = head;
      while (work.length > 2) {
        rest.unshift(work.slice(-2));
        work = work.slice(0, -2);
      }
      if (work) rest.unshift(work);
      grouped = rest.join(",") + "," + tail;
    }
    return sign + "₹" + grouped + "." + decPart;
  }

  function reconMoneyChips(totals) {
    const n = totals || {};
    return [
      { label: "On portal (2B)", value: n.portal_total, filter: "all" },
      { label: "In books", value: n.books_total, filter: "all" },
      { label: "Difference", value: n.gap, filter: "amount_mismatch" },
      { label: "Credit at risk (2B only)", value: n.credit_at_risk, filter: "unmatched" },
      { label: "Credit without support", value: n.unsupported_credit, filter: "unmatched" },
    ];
  }

  function reconTotalsText(totals) {
    const n = totals || {};
    return [
      `On portal ${formatINR(n.portal_total)}`,
      `In books ${formatINR(n.books_total)}`,
      `Difference ${formatINR(n.gap)}`,
      `Credit at risk ${formatINR(n.credit_at_risk)}`,
    ].join(" · ");
  }

  function hasReconMissing(pack) {
    return Boolean(pack && pack.recon_missing);
  }

  function reconMissingText(pack) {
    const code = pack && pack.recon_missing;
    if (code === "no_gstr_2b") {
      return "No reconciliation ran: the GSTR-2B JSON is missing for this month. Drop the portal download in and re-run.";
    }
    if (code === "no_purchase_rows") {
      return "No reconciliation ran: no purchase register (bills, Tally or Zoho) was found this month.";
    }
    return "";
  }

  function gstrPreviewNote(reconPresent) {
    if (reconPresent) {
      return "Open the GSTR Excel for the full register. Match columns filled in GSTR Excel when a master grid exists.";
    }
    return "Open the GSTR Excel for the full register. Match columns stay empty until reconciliation.";
  }

  return {
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
    toleranceText,
    filterReconRows,
    sortReconRows,
    reconReason,
    formatINR,
    reconMoneyChips,
    reconTotalsText,
    hasReconMissing,
    reconMissingText,
    gstrPreviewNote,
  };
});
