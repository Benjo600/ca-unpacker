"use strict";

const assert = require("node:assert/strict");
const {
  viewModelForUpdateState,
  progressPercent,
  notesLines,
} = require("../update-state.js");

const REQUIRED_BANNER =
  "A required update must be installed before processing more files.";

const idle = viewModelForUpdateState(null);
assert.equal(idle.visible, false);
assert.equal(idle.status, "idle");
assert.equal(idle.canCheck, true);
assert.equal(idle.canDownload, false);
assert.equal(idle.canInstall, false);
assert.equal(idle.canRetry, false);
assert.equal(idle.canLater, false);
assert.equal(idle.banner, "");
assert.equal(idle.progressText, "");
assert.equal(idle.error, "");

const empty = viewModelForUpdateState({});
assert.equal(empty.visible, false);
assert.equal(empty.status, "idle");

const unknown = viewModelForUpdateState({ status: "nonsense" });
assert.equal(unknown.visible, false);
assert.equal(unknown.status, "idle");

const checking = viewModelForUpdateState({ status: "checking" });
assert.equal(checking.visible, true);
assert.equal(checking.status, "checking");
assert.equal(checking.canCheck, false);
assert.equal(checking.progressText, "Checking for updates…");
assert.equal(checking.banner, "");

const available = viewModelForUpdateState({
  status: "available",
  version: "1.4.2",
  title: "Faster reconciliation",
  notes: "Line one\nLine two",
});
assert.equal(available.visible, true);
assert.equal(available.status, "available");
assert.equal(available.version, "1.4.2");
assert.equal(available.title, "Faster reconciliation");
assert.equal(available.notes, "Line one\nLine two");
assert.equal(available.canDownload, true);
assert.equal(available.canLater, true);
assert.equal(available.canCheck, false);
assert.equal(available.progressText, "Update 1.4.2 is ready to download.");
assert.equal(available.banner, "");

const availableNoVersion = viewModelForUpdateState({ status: "available" });
assert.equal(availableNoVersion.progressText, "An update is ready to download.");

const availableMandatory = viewModelForUpdateState({
  status: "available",
  version: "2.0.0",
  mandatory: true,
});
assert.equal(availableMandatory.canDownload, true);
assert.equal(availableMandatory.canLater, false);
assert.equal(availableMandatory.banner, REQUIRED_BANNER);

const downloading = viewModelForUpdateState({
  status: "downloading",
  version: "1.4.2",
  progress: 0.42,
});
assert.equal(downloading.visible, true);
assert.equal(downloading.status, "downloading");
assert.equal(downloading.canCancel, true);
assert.equal(downloading.canDownload, false);
assert.equal(downloading.canInstall, false);
assert.equal(downloading.progressText, "Downloading 42%");
assert.equal(downloading.banner, "");

const downloadingMandatory = viewModelForUpdateState({
  status: "downloading",
  mandatory: true,
  progress: 0.1,
});
assert.equal(downloadingMandatory.banner, REQUIRED_BANNER);
assert.equal(downloadingMandatory.progressText, "Downloading 10%");

const ready = viewModelForUpdateState({ status: "ready", version: "1.4.2" });
assert.equal(ready.visible, true);
assert.equal(ready.status, "ready");
assert.equal(ready.canInstall, true);
assert.equal(ready.canLater, true);
assert.equal(ready.progressText, "Downloaded and verified. Ready to install.");
assert.equal(ready.banner, "");

const readyMandatory = viewModelForUpdateState({
  status: "ready",
  version: "1.4.2",
  mandatory: true,
});
assert.equal(readyMandatory.canInstall, true);
assert.equal(readyMandatory.canLater, false);
assert.equal(readyMandatory.banner, REQUIRED_BANNER);

const installing = viewModelForUpdateState({
  status: "installing",
  mandatory: true,
});
assert.equal(installing.visible, true);
assert.equal(installing.status, "installing");
assert.equal(installing.canCheck, false);
assert.equal(installing.canDownload, false);
assert.equal(installing.canCancel, false);
assert.equal(installing.canInstall, false);
assert.equal(installing.canRetry, false);
assert.equal(installing.canLater, false);
assert.equal(installing.progressText, "Installing and restarting…");
assert.equal(installing.banner, "");

const failed = viewModelForUpdateState({
  status: "error",
  error: "  Could not reach the update server.  ",
});
assert.equal(failed.visible, true);
assert.equal(failed.status, "error");
assert.equal(failed.canRetry, true);
assert.equal(failed.canCheck, false);
assert.equal(failed.error, "Could not reach the update server.");
assert.equal(failed.banner, "");

const failedMandatory = viewModelForUpdateState({
  status: "error",
  error: "Network down",
  mandatory: true,
});
assert.equal(failedMandatory.banner, REQUIRED_BANNER);

assert.equal(progressPercent(0), 0);
assert.equal(progressPercent(0.456), 46);
assert.equal(progressPercent(0.999), 100);
assert.equal(progressPercent(1), 100);
assert.equal(progressPercent(1.5), 100);
assert.equal(progressPercent(-0.4), 0);
assert.equal(progressPercent(-2), 0);
assert.equal(progressPercent("0.25"), 25);
assert.equal(progressPercent(null), 0);
assert.equal(progressPercent(undefined), 0);
assert.equal(progressPercent("not a number"), 0);

assert.deepEqual(notesLines("Line one\n\n  Line two  \r\n"), ["Line one", "Line two"]);
assert.deepEqual(notesLines("   \n\t\n"), []);
assert.deepEqual(notesLines(null), []);
assert.deepEqual(notesLines(undefined), []);
assert.deepEqual(notesLines(42), ["42"]);

console.log("update-state behavior tests passed");
