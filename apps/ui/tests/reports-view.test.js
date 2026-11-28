"use strict";

const assert = require("node:assert/strict");
const {
  sortNewestFirst,
  packMatches,
  anyFilterActive,
  filterPacks,
  groupByClient,
  clientOptions,
  kindOptions,
  packStatusLabel,
  outputKeys,
} = require("../reports-view.js");

const packs = [
  {
    client_name: "Acme Traders",
    period_label: "Sep 2026",
    row_count: 7,
    created_at: "2026-09-10T10:00:00Z",
    outputs: [
      { key: "bank", label: "Bank statement", rows: 7, status: "ready" },
      { key: "purchase", label: "Purchase register", rows: 2, status: "ready" },
    ],
  },
  {
    client_name: "Acme Traders",
    period_label: "Oct 2026",
    row_count: 16,
    created_at: "2026-10-12T10:00:00Z",
    outputs: [{ key: "bank", label: "Bank statement", rows: 16, status: "ready" }],
  },
  {
    client_name: "Bharat Steel Works",
    period_label: "Oct 2026",
    row_count: 1,
    created_at: "2026-11-01T10:00:00Z",
    outputs: [
      { key: "gstr_2b", label: "GSTR-2B formatted", rows: 1, status: "skipped" },
    ],
  },
];

// ---- order ---------------------------------------------------------------

assert.deepEqual(
  sortNewestFirst(packs).map((pack) => pack.period_label),
  ["Oct 2026", "Oct 2026", "Sep 2026"]
);
assert.equal(sortNewestFirst(packs)[0].client_name, "Bharat Steel Works");
// Undated packs sort last instead of crashing.
assert.equal(sortNewestFirst([{ created_at: "" }, packs[2]])[0], packs[2]);

// ---- filters -------------------------------------------------------------

assert.equal(anyFilterActive({}), false);
assert.equal(anyFilterActive({ client: "", kind: "" }), false);
assert.equal(anyFilterActive({ client: "Acme Traders" }), true);

assert.equal(packMatches(packs[0], {}), true);
assert.equal(packMatches(packs[0], { client: "Acme Traders" }), true);
assert.equal(packMatches(packs[0], { client: "Bharat Steel Works" }), false);
// A pack type matches when any of its outputs uses that key.
assert.equal(packMatches(packs[0], { kind: "purchase" }), true);
assert.equal(packMatches(packs[0], { kind: "bank" }), true);
assert.equal(packMatches(packs[0], { kind: "gstr_2b" }), false);
// Both filters together are an AND.
assert.equal(filterPacks(packs, { client: "Acme Traders", kind: "bank" }).length, 2);
assert.equal(filterPacks(packs, { client: "Acme Traders", kind: "gstr_2b" }).length, 0);

// ---- grouping ------------------------------------------------------------

const groups = groupByClient(packs);
assert.deepEqual(groups.map((group) => group.name), [
  "Bharat Steel Works",
  "Acme Traders",
]);
assert.deepEqual(
  groups[1].packs.map((pack) => pack.period_label),
  ["Oct 2026", "Sep 2026"]
);
// A pack with no client name still groups instead of vanishing.
assert.equal(groupByClient([{ period_label: "Oct 2026" }])[0].name, "Client");

// ---- dropdown options ----------------------------------------------------

assert.deepEqual(clientOptions(packs), [
  { value: "Acme Traders", label: "Acme Traders" },
  { value: "Bharat Steel Works", label: "Bharat Steel Works" },
]);
assert.deepEqual(kindOptions(packs), [
  { value: "bank", label: "Bank statement" },
  { value: "gstr_2b", label: "GSTR-2B formatted" },
  { value: "purchase", label: "Purchase register" },
]);
// A key with no label is still readable.
assert.deepEqual(kindOptions([{ outputs: [{ key: "needs_review" }] }]), [
  { value: "needs_review", label: "Needs review" },
]);

// ---- labels --------------------------------------------------------------

assert.equal(packStatusLabel("ready"), "");
assert.equal(packStatusLabel(""), "");
assert.equal(packStatusLabel("skipped"), "Not written");
assert.equal(packStatusLabel("missing"), "File missing");
assert.equal(packStatusLabel("brand_new"), "Brand new");

assert.deepEqual(outputKeys(packs[1]), ["bank"]);

console.log("reports-view behavior tests passed");
