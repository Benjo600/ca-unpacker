"use strict";

const assert = require("node:assert/strict");
const {
  clientMatches,
  filterClients,
  documentCount,
  documentsLabel,
  latestPeriodLabel,
  filterSummary,
} = require("../clients-view.js");

const clients = [
  { id: 1, name: "Acme Traders", gstin: "27AAAAA0000A1Z5", document_count: 12, latest_period: "Oct 2026" },
  { id: 2, name: "Bharat Steel Works", gstin: "", document_count: 1, latest_period: "Sep 2026" },
  { id: 3, name: "Chandra & Sons", gstin: "29BBBBB1111B2Z6", document_count: 0, latest_period: "" },
];

// ---- name matching -------------------------------------------------------

assert.deepEqual(filterClients(clients, "").map((c) => c.id), [1, 2, 3]);
assert.deepEqual(filterClients(clients, "   ").map((c) => c.id), [1, 2, 3]);
assert.deepEqual(filterClients(clients, "acme").map((c) => c.id), [1]);
assert.deepEqual(filterClients(clients, "  ACME  ").map((c) => c.id), [1]);
assert.deepEqual(filterClients(clients, "steel work").map((c) => c.id), [2]);
// A query that matches nothing returns an empty list, not the whole list.
assert.deepEqual(filterClients(clients, "zebra"), []);
// The original list is never mutated.
assert.equal(clients.length, 3);

// ---- GSTIN matching ------------------------------------------------------

assert.deepEqual(filterClients(clients, "27AAAAA0000A1Z5").map((c) => c.id), [1]);
assert.deepEqual(filterClients(clients, "29bbb").map((c) => c.id), [3]);
// Spaces inside a typed GSTIN are ignored.
assert.deepEqual(filterClients(clients, "27 AAAA A0000A1Z5").map((c) => c.id), [1]);
// A client without a GSTIN is never matched by a GSTIN-looking query alone.
assert.equal(clientMatches(clients[1], "29BBB"), false);

// ---- counts and labels ---------------------------------------------------

assert.equal(documentCount({ document_count: 3 }), 3);
assert.equal(documentCount({ document_count: "4" }), 4);
assert.equal(documentCount({ document_count: -1 }), 0);
assert.equal(documentCount({}), 0);
assert.equal(documentCount(null), 0);

assert.equal(documentsLabel(0), "No documents");
assert.equal(documentsLabel(1), "1 document");
assert.equal(documentsLabel(7), "7 documents");

assert.equal(latestPeriodLabel({ latest_period: "Oct 2026" }), "Oct 2026");
assert.equal(latestPeriodLabel({ latest_period: "" }), "No periods yet");
assert.equal(latestPeriodLabel({}), "No periods yet");

assert.equal(filterSummary(3, 3), "3 clients");
assert.equal(filterSummary(1, 1), "1 client");
assert.equal(filterSummary(8, 2), "2 of 8 clients match");
assert.equal(filterSummary(0, 0), "0 clients");

console.log("clients-view behavior tests passed");
