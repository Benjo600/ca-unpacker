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
  };

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
    return [
      `Matched ${Number(n.matched) || 0}`,
      `Only in books ${Number(n.books_only) || 0}`,
      `Only in 2B ${Number(n.portal_only) || 0}`,
      `Amount mismatch ${Number(n.amount_mismatch) || 0}`,
      `Likely ${Number(n.likely) || 0}`,
    ].join(" · ");
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

  function filterReconRows(rows, filter) {
    const list = rows || [];
    if (filter === "matched") return list.filter((row) => row.status === "matched");
    if (filter === "unmatched") {
      return list.filter((row) => row.status === "books_only" || row.status === "portal_only");
    }
    if (filter === "amount_mismatch") return list.filter((row) => row.status === "amount_mismatch");
    if (filter === "likely") return list.filter((row) => row.status === "likely");
    return list.slice();
  }

  function gstrPreviewNote(reconPresent) {
    if (reconPresent) {
      return "Open the GSTR Excel for the full register. Match columns filled in GSTR Excel when a master grid exists.";
    }
    return "Open the GSTR Excel for the full register. Match columns stay empty until reconciliation.";
  }

  return {
    hasRecon,
    reconCountsText,
    reconStatusLabel,
    reconInvoiceDisplay,
    filterReconRows,
    gstrPreviewNote,
  };
});
