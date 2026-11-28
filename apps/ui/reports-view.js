(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAReportsView = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  // Reports is one long list of every pack ever written. These helpers filter
  // it by client and pack type and group it as client -> period, newest first.

  function text(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function packTime(pack) {
    const when = Date.parse(text(pack && pack.created_at));
    return Number.isFinite(when) ? when : 0;
  }

  function sortNewestFirst(packs) {
    return (Array.isArray(packs) ? packs.slice() : []).sort(
      (left, right) => packTime(right) - packTime(left)
    );
  }

  function outputKeys(pack) {
    return (pack && pack.outputs ? pack.outputs : [])
      .map((output) => text(output && output.key))
      .filter(Boolean);
  }

  function packTypeLabel(pack, key) {
    const outputs = (pack && pack.outputs) || [];
    const match = outputs.find((output) => text(output && output.key) === key);
    return match ? text(match.label) || key : key;
  }

  function clientName(pack) {
    return text(pack && pack.client_name).trim() || "Client";
  }

  function packMatches(pack, filters) {
    const active = filters || {};
    const client = text(active.client).trim();
    if (client && clientName(pack) !== client) return false;
    const kind = text(active.kind).trim();
    if (kind && outputKeys(pack).indexOf(kind) === -1) return false;
    return true;
  }

  function anyFilterActive(filters) {
    const active = filters || {};
    return Boolean(text(active.client).trim() || text(active.kind).trim());
  }

  function filterPacks(packs, filters) {
    const list = Array.isArray(packs) ? packs : [];
    return sortNewestFirst(list.filter((pack) => packMatches(pack, filters)));
  }

  // One group per client, clients ordered by their newest pack, periods inside
  // a client also newest first.
  function groupByClient(packs) {
    const groups = new Map();
    for (const pack of sortNewestFirst(packs)) {
      const name = clientName(pack);
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(pack);
    }
    return Array.from(groups.entries()).map(([name, items]) => ({
      name,
      packs: items,
    }));
  }

  function clientOptions(packs) {
    const names = new Set();
    for (const pack of Array.isArray(packs) ? packs : []) {
      names.add(clientName(pack));
    }
    return Array.from(names)
      .sort((left, right) => left.localeCompare(right))
      .map((name) => ({ value: name, label: name }));
  }

  function kindOptions(packs) {
    const labels = new Map();
    for (const pack of Array.isArray(packs) ? packs : []) {
      for (const output of (pack && pack.outputs) || []) {
        const key = text(output && output.key);
        if (!key || labels.has(key)) continue;
        labels.set(key, text(output.label) || prettifyKey(key));
      }
    }
    return Array.from(labels.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.label.localeCompare(right.label));
  }

  function prettifyKey(key) {
    const words = text(key).replace(/[_-]+/g, " ").trim();
    if (!words) return "";
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  // The summary stores a machine status; a CA should not read "skipped".
  const STATUS_LABELS = {
    ready: "Ready",
    written: "Written",
    skipped: "Not written",
    missing: "File missing",
    failed: "Could not be written",
    stale: "Out of date",
  };

  function packStatusLabel(status) {
    const key = text(status).trim().toLowerCase();
    if (!key || key === "ready") return "";
    if (STATUS_LABELS[key]) return STATUS_LABELS[key];
    return prettifyKey(key);
  }

  return {
    packTime,
    sortNewestFirst,
    packMatches,
    anyFilterActive,
    filterPacks,
    groupByClient,
    clientOptions,
    kindOptions,
    packStatusLabel,
    outputKeys,
    clientName,
  };
});
