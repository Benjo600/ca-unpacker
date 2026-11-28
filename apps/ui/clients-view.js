(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAClientsView = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  // The client list used to be a bare scroll of rows. These helpers keep the
  // search, the document count and the latest month in one place so the
  // rendering code stays about layout only.

  function text(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function normalize(value) {
    return text(value).trim().toLowerCase();
  }

  // A client matches when the typed text appears in the name or in the GSTIN.
  // GSTINs are stored without spaces, so spaces in the query are ignored there.
  function clientMatches(client, query) {
    const needle = normalize(query);
    if (!needle) return true;
    if (!client) return false;
    const name = normalize(client.name);
    const gstin = normalize(client.gstin);
    if (name.includes(needle)) return true;
    const compact = needle.replace(/\s+/g, "");
    return Boolean(gstin) && gstin.includes(compact);
  }

  function filterClients(clients, query) {
    const list = Array.isArray(clients) ? clients : [];
    if (!normalize(query)) return list.slice();
    return list.filter((client) => clientMatches(client, query));
  }

  function documentCount(client) {
    const value = Number(client && client.document_count);
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
  }

  function documentsLabel(count) {
    const n = Number(count) || 0;
    if (n <= 0) return "No documents";
    return `${n} ${n === 1 ? "document" : "documents"}`;
  }

  function latestPeriodLabel(client) {
    const label = text(client && client.latest_period).trim();
    return label || "No periods yet";
  }

  // "8 clients" when everything is shown, "2 of 8 clients" while filtering.
  function filterSummary(total, shown) {
    const count = Math.max(0, Number(total) || 0);
    const visible = Math.max(0, Number(shown) || 0);
    if (visible >= count) return `${count} ${count === 1 ? "client" : "clients"}`;
    return `${visible} of ${count} clients match`;
  }

  return {
    clientMatches,
    filterClients,
    documentCount,
    documentsLabel,
    latestPeriodLabel,
    filterSummary,
  };
});
