(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CAUpdateState = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  const STATUSES = [
    "idle",
    "checking",
    "available",
    "downloading",
    "ready",
    "installing",
    "error",
  ];
  const POLLING_STATUSES = ["checking", "downloading", "installing"];

  function progressPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.max(0, Math.min(100, Math.round(number * 100)));
  }

  function notesLines(notes) {
    if (notes === null || notes === undefined) return [];
    return String(notes)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  function normalizeStatus(status) {
    const value = String(status === null || status === undefined ? "" : status).trim();
    return STATUSES.indexOf(value) >= 0 ? value : "idle";
  }

  function viewModelForUpdateState(update) {
    const data = update && typeof update === "object" ? update : {};
    const status = normalizeStatus(data.status);
    const version = data.version === null || data.version === undefined
      ? ""
      : String(data.version).trim();
    const title = data.title === null || data.title === undefined
      ? ""
      : String(data.title).trim();
    const notes = data.notes === null || data.notes === undefined
      ? ""
      : String(data.notes);
    const mandatory = Boolean(data.mandatory);
    const error = status === "error"
      ? (data.error === null || data.error === undefined ? "" : String(data.error).trim())
      : "";

    const view = {
      visible: status !== "idle",
      status,
      version,
      title,
      notes,
      mandatory,
      progressText: "",
      error,
      canCheck: false,
      canDownload: false,
      canCancel: false,
      canInstall: false,
      canRetry: false,
      canLater: false,
      banner: "",
    };

    if (status === "checking") {
      view.progressText = "Checking for updates…";
    } else if (status === "available") {
      view.canDownload = true;
      view.canLater = !mandatory;
      view.progressText = version
        ? `Update ${version} is ready to download.`
        : "An update is ready to download.";
    } else if (status === "downloading") {
      view.canCancel = true;
      view.progressText = `Downloading ${progressPercent(data.progress)}%`;
    } else if (status === "ready") {
      view.canInstall = true;
      view.canLater = !mandatory;
      view.progressText = "Downloaded and verified. Ready to install.";
    } else if (status === "installing") {
      view.progressText = "Installing and restarting…";
    } else if (status === "error") {
      view.canRetry = true;
    } else {
      view.canCheck = true;
    }

    if (mandatory && status !== "installing") {
      view.banner = "A required update must be installed before processing more files.";
    }

    return view;
  }

  return {
    STATUSES,
    POLLING_STATUSES,
    viewModelForUpdateState,
    progressPercent,
    notesLines,
  };
});
