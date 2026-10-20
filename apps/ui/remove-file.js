(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CARemoveFile = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function confirmMessage(file) {
    const name = (file && file.original_name) || "this file";
    return (
      `Remove ${name} from this period? ` +
      "Its rows are dropped and the Excels are rebuilt from the remaining files. " +
      "Other files in this period are not touched."
    );
  }

  // Guards are pure so the cancel and busy paths stay testable without a browser.
  function guardRemoveFile(input) {
    const options = input || {};
    const file = options.file;
    if (!file || !file.id) {
      return { action: "blocked", reason: "Pick a file to remove." };
    }
    if (options.busy) {
      return {
        action: "blocked",
        reason: "Wait for this period to finish processing first.",
      };
    }
    return { action: "ready", reason: "" };
  }

  function resolveRemoveChoice(confirmed) {
    return confirmed ? { action: "remove" } : { action: "cancel" };
  }

  return { confirmMessage, guardRemoveFile, resolveRemoveChoice };
});
