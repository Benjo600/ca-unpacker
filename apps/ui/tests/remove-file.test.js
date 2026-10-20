"use strict";

const assert = require("node:assert/strict");
const { confirmMessage, guardRemoveFile, resolveRemoveChoice } = require("../remove-file.js");

const file = { id: 7, original_name: "HDFC_Statement_A.pdf" };

// Cancelling must not remove anything.
assert.deepEqual(resolveRemoveChoice(true), { action: "remove" });
assert.deepEqual(resolveRemoveChoice(false), { action: "cancel" });

// A confirm dialog names the file and says other files are safe.
const copy = confirmMessage(file);
assert.ok(copy.includes("HDFC_Statement_A.pdf"), copy);
assert.ok(copy.toLowerCase().includes("other files in this period are not touched"), copy);

// Guards: ready only when a real file is chosen and nothing is processing.
assert.deepEqual(guardRemoveFile({ file, busy: false }), { action: "ready", reason: "" });

const busy = guardRemoveFile({ file, busy: true });
assert.equal(busy.action, "blocked");
assert.ok(busy.reason.toLowerCase().includes("finish processing"), busy.reason);

assert.equal(guardRemoveFile({ file: null, busy: false }).action, "blocked");
assert.equal(guardRemoveFile({ file: { original_name: "no-id.pdf" }, busy: false }).action, "blocked");
assert.equal(guardRemoveFile(undefined).action, "blocked");

console.log("remove-file behavior tests passed");
