const loginEl = document.getElementById("login");
const welcomeEl = document.getElementById("welcome");
const setupEl = document.getElementById("setup");
const deskEl = document.getElementById("desk");
const firmNameEl = document.getElementById("firm-name");
const libraryPathEl = document.getElementById("library-path");
const setupErrorEl = document.getElementById("setup-error");
const saveFirmBtn = document.getElementById("save-firm");
const firmLabelEl = document.getElementById("firm-label");
const navLabelEl = document.getElementById("nav-label");
const clientCountEl = document.getElementById("client-count");
const clientListEl = document.getElementById("client-list");
const emptyEl = document.getElementById("empty");
const addForm = document.getElementById("add-form");
const clientNameEl = document.getElementById("client-name");
const clientGstinEl = document.getElementById("client-gstin");
const deskErrorEl = document.getElementById("desk-error");
const paneClients = document.getElementById("pane-clients");
const panePeriods = document.getElementById("pane-periods");
const paneDump = document.getElementById("pane-dump");
const periodClientNameEl = document.getElementById("period-client-name");
const periodForm = document.getElementById("period-form");
const periodLabelEl = document.getElementById("period-label");
const periodErrorEl = document.getElementById("period-error");
const periodListEl = document.getElementById("period-list");
const periodEmptyEl = document.getElementById("period-empty");
const dumpTitleEl = document.getElementById("dump-title");
const dumpEyebrowEl = document.getElementById("dump-eyebrow");
const dumpStatusEl = document.getElementById("dump-status");
const dumpErrorEl = document.getElementById("dump-error");
const dropZone = document.getElementById("drop-zone");
const addFilesBtn = document.getElementById("add-files");
const addFolderBtn = document.getElementById("add-folder");
const fileListEl = document.getElementById("file-list");
const fileEmptyEl = document.getElementById("file-empty");
const reviewBlock = document.getElementById("review-block");
const reviewListEl = document.getElementById("review-list");
const reviewPackNoteEl = document.getElementById("review-pack-note");
const packBlock = document.getElementById("pack-block");
const packMetaEl = document.getElementById("pack-meta");
const packFilesEl = document.getElementById("pack-files");
const reconBlock = document.getElementById("recon-block");
const reconCountsEl = document.getElementById("recon-counts");
const reconTableEl = document.getElementById("recon-table");
const reconFiltersEl = document.getElementById("recon-filters");
const previewBlock = document.getElementById("preview-block");
const previewListEl = document.getElementById("preview-list");
const scanNoteEl = document.getElementById("scan-note");
const cropModal = document.getElementById("crop-modal");
const cropCaptionEl = document.getElementById("crop-caption");
const cropImageEl = document.getElementById("crop-image");
const unlockModal = document.getElementById("unlock-modal");
const unlockFilenameEl = document.getElementById("unlock-filename");
const unlockPasswordEl = document.getElementById("unlock-password");
const unlockErrorEl = document.getElementById("unlock-error");
const authGateEl = document.getElementById("auth-gate");
const quotaBannerEl = document.getElementById("profile");
const quotaTextEl = document.getElementById("quota-text");
const profileButtonEl = document.getElementById("profile-button");
const profilePanelEl = document.getElementById("profile-panel");
const profileInitialEl = document.getElementById("profile-initial");
const profileEmailEl = document.getElementById("profile-email");
const profilePlanEl = document.getElementById("profile-plan");
const profileMeterEl = document.getElementById("profile-meter");
const profileMeterFillEl = document.getElementById("profile-meter-fill");
const authErrorEl = document.getElementById("auth-error");
const authNoticeEl = document.getElementById("auth-notice");

// Preview Workspace Elements
const folderPreviewSection = document.getElementById("folder-preview-section");
const filePreviewPane = document.getElementById("file-preview-pane");
const previewSplitContainer = document.getElementById("preview-split-container");
const btnTogglePreview = document.getElementById("btn-toggle-preview");
const btnExpandPreview = document.getElementById("btn-expand-preview");
const previewFolderPathEl = document.getElementById("preview-folder-path");
const sourcePeriodCountEl = document.getElementById("source-period-count");
const tabSourcePeriod = document.getElementById("tab-source-period");
const tabSourceOutput = document.getElementById("tab-source-output");
const tabSourceBrowse = document.getElementById("tab-source-browse");
const previewTypeBadge = document.getElementById("preview-type-badge");
const previewFileName = document.getElementById("preview-file-name");
const previewFileSize = document.getElementById("preview-file-size");
const previewFileCounter = document.getElementById("preview-file-counter");
const btnPrevFile = document.getElementById("preview-prev-file");
const btnNextFile = document.getElementById("preview-next-file");
const btnOpenExternal = document.getElementById("preview-open-external");
const pdfControls = document.getElementById("pdf-controls");
const pdfPrevPage = document.getElementById("pdf-prev-page");
const pdfNextPage = document.getElementById("pdf-next-page");
const pdfPageIndicator = document.getElementById("pdf-page-indicator");
const pdfZoomOut = document.getElementById("pdf-zoom-out");
const pdfZoomIn = document.getElementById("pdf-zoom-in");
const pdfZoomLevel = document.getElementById("pdf-zoom-level");
const pdfFitWidth = document.getElementById("pdf-fit-width");
const pdfToggleText = document.getElementById("pdf-toggle-text");
const sheetTabsContainer = document.getElementById("sheet-tabs-container");
const previewContentViewport = document.getElementById("preview-content-viewport");
const previewPlaceholder = document.getElementById("preview-placeholder");
const pdfViewer = document.getElementById("pdf-viewer");
const pdfPageWrapper = document.getElementById("pdf-page-wrapper");
const pdfPageImg = document.getElementById("pdf-page-img");
const pdfTextLayer = document.getElementById("pdf-text-layer");
const spreadsheetViewer = document.getElementById("spreadsheet-viewer");
const spreadsheetInfo = document.getElementById("spreadsheet-info");
const spreadsheetFilter = document.getElementById("spreadsheet-filter");
const spreadsheetTableContainer = document.getElementById("spreadsheet-table-container");
const codeViewer = document.getElementById("code-viewer");
const codeMetaBar = document.getElementById("code-meta-bar");
const codeContent = document.getElementById("code-content");
const imageViewer = document.getElementById("image-viewer");
const imagePreviewImg = document.getElementById("image-preview-img");
const imageMetaBar = document.getElementById("image-meta-bar");
const previewPasswordViewer = document.getElementById("preview-password-viewer");
const previewUnlockForm = document.getElementById("preview-unlock-form");
const previewUnlockPwd = document.getElementById("preview-unlock-pwd");
const previewUnlockErr = document.getElementById("preview-unlock-err");
const binaryViewer = document.getElementById("binary-viewer");
const binaryFileTitle = document.getElementById("binary-file-title");
const binaryFileDesc = document.getElementById("binary-file-desc");
const binaryOpenBtn = document.getElementById("binary-open-btn");
const previewLoadingOverlay = document.getElementById("preview-loading-overlay");

// Preview Workspace State
let currentFolderSource = "period"; // "period" | "output" | "browse"
let currentFolderFiles = [];
let selectedFileIndex = -1;
let selectedFile = null;
let currentPdfPage = 1;
let totalPdfPages = 1;
let currentPdfZoom = 1.0;
let isPdfTextMode = false;
let currentSpreadsheet = null;
let isPreviewPaneOpen = true;
let isPreviewFullscreen = false;
let customFolderPath = "";
let previewReqCounter = 0;

let currentClient = null;
let currentPeriod = null;
let kindOptions = [];
let pollTimer = null;
let activeJobId = null;
let lastFileCount = 0;
let lastFiles = [];
let lastPreviewFiles = [];
let packVisible = false;
let packHasBank = false;
let packOpenKey = "";
let lastPack = null;
let reconFilter = "all";
let unlockFile = null;
let tesseractChecked = false;
let tesseractFound = true;
let guideDismissed = false;
let lastGuideHighlight = null;
let lastPeriodCount = 0;
let authState = null;
let devMode = false;
let lastAppState = null;
let uiSessionActive = false;
let navHistory = [];
let navIndex = -1;
let navSilent = false;
let navBusy = false;

const UI_SESSION_KEY = "caUnpackerUiSession";
const UI_REMEMBER_KEY = "caUnpackerRememberUser";

function desktopApi() {
  return (window.pywebview && window.pywebview.api) || null;
}

function showError(el, message) {
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = message;
}

function showPane(name) {
  paneClients.classList.toggle("hidden", name !== "clients");
  panePeriods.classList.toggle("hidden", name !== "periods");
  paneDump.classList.toggle("hidden", name !== "dump");
  if (name === "clients") navLabelEl.textContent = "Clients";
  if (name === "periods") navLabelEl.textContent = "Periods";
  if (name === "dump") navLabelEl.textContent = "Dump tray";
  updateDeskContext(name);
}

function updateDeskContext(pane) {
  const el = document.getElementById("desk-context");
  if (!el) return;
  const current = pane || currentDeskPane();
  const parts = ["Clients"];
  if (current === "periods" || current === "dump") {
    const clientName =
      (currentClient && currentClient.name) ||
      (periodClientNameEl && periodClientNameEl.textContent) ||
      (dumpEyebrowEl && dumpEyebrowEl.textContent);
    if (clientName && clientName !== "Dump tray") parts.push(clientName);
  }
  if (current === "dump") {
    const periodLabel =
      (currentPeriod && currentPeriod.label) ||
      (dumpTitleEl && dumpTitleEl.textContent);
    if (periodLabel) parts.push(periodLabel);
  }
  el.textContent = parts.join(" / ");
}

function currentDeskPane() {
  if (paneDump && !paneDump.classList.contains("hidden")) return "dump";
  if (panePeriods && !panePeriods.classList.contains("hidden")) return "periods";
  return "clients";
}

function navEntryKey(entry) {
  if (!entry) return "";
  return `${entry.pane}:${entry.clientId || ""}:${entry.periodId || ""}`;
}

function currentNavEntry() {
  const pane = currentDeskPane();
  const entry = { pane };
  if (pane === "periods" && currentClient) entry.clientId = currentClient.id;
  if (pane === "dump") {
    if (currentClient) entry.clientId = currentClient.id;
    if (currentPeriod) entry.periodId = currentPeriod.id;
  }
  return entry;
}

function updateNavButtons() {
  const backBtn = document.getElementById("nav-back");
  const forwardBtn = document.getElementById("nav-forward");
  if (backBtn) backBtn.disabled = navBusy || navIndex <= 0;
  if (forwardBtn) forwardBtn.disabled = navBusy || navIndex < 0 || navIndex >= navHistory.length - 1;
}

function recordNav(entry) {
  if (navSilent || !entry) return;
  const last = navHistory[navIndex];
  if (last && navEntryKey(last) === navEntryKey(entry)) {
    updateNavButtons();
    return;
  }
  navHistory = navHistory.slice(0, navIndex + 1);
  navHistory.push(entry);
  navIndex = navHistory.length - 1;
  updateNavButtons();
}

async function applyNavEntry(entry) {
  if (!entry) return;
  if (entry.pane === "clients") {
    const api = desktopApi();
    let state = lastAppState;
    if (api && api.get_state) state = await api.get_state();
    if (state) showDesk(state);
    return;
  }
  if (entry.pane === "periods" && entry.clientId) {
    await openClient(entry.clientId);
    return;
  }
  if (entry.pane === "dump" && entry.periodId) {
    await openPeriod(entry.periodId);
  }
}

async function goNavBack() {
  if (navBusy || navIndex <= 0) return;
  navBusy = true;
  updateNavButtons();
  navSilent = true;
  navIndex -= 1;
  try {
    await applyNavEntry(navHistory[navIndex]);
  } finally {
    navSilent = false;
    navBusy = false;
    updateNavButtons();
  }
}

async function goNavForward() {
  if (navBusy || navIndex < 0 || navIndex >= navHistory.length - 1) return;
  navBusy = true;
  updateNavButtons();
  navSilent = true;
  navIndex += 1;
  try {
    await applyNavEntry(navHistory[navIndex]);
  } finally {
    navSilent = false;
    navBusy = false;
    updateNavButtons();
  }
}

async function refreshCurrentView() {
  if (navBusy || !deskIsVisible()) return;
  navBusy = true;
  updateNavButtons();
  navSilent = true;
  try {
    const pane = currentDeskPane();
    if (pane === "dump" && currentPeriod) {
      await openPeriod(currentPeriod.id);
    } else if (pane === "periods" && currentClient) {
      await openClient(currentClient.id);
    } else {
      const api = desktopApi();
      let state = lastAppState;
      if (api && api.get_state) state = await api.get_state();
      if (state) {
        lastAppState = state;
        firmLabelEl.textContent = state.firm ? state.firm.name : "";
        setOutputLabel(state.output_path || "");
        setPathWarnings(state.path_warnings || []);
        renderLicense(state.license);
        renderClients(state.clients || []);
        syncGuide();
      }
    }
  } finally {
    navSilent = false;
    navBusy = false;
    updateNavButtons();
  }
}

function isTypingTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  return Boolean(el.isContentEditable);
}

function showScreen(name) {
  if (loginEl) loginEl.classList.toggle("hidden", name !== "login");
  setupEl.classList.toggle("hidden", name !== "setup");
  if (welcomeEl) welcomeEl.classList.toggle("hidden", name !== "welcome");
  deskEl.classList.toggle("hidden", name !== "desk");
}

function firmIsConfigured(state) {
  return Boolean(state && state.firm && state.output_path);
}

function setUiSession() {
  uiSessionActive = true;
  try {
    sessionStorage.setItem(UI_SESSION_KEY, "1");
  } catch {
    /* sessionStorage is optional in this host */
  }
}

function restoreLoginForm() {
  const userEl = document.getElementById("login-user");
  const rememberEl = document.getElementById("login-remember");
  if (!userEl) return;
  try {
    const saved = localStorage.getItem(UI_REMEMBER_KEY) || "";
    if (saved) {
      userEl.value = saved;
      if (rememberEl) rememberEl.checked = true;
    }
  } catch {
    /* localStorage is optional in this host */
  }
}

function persistRememberedUser() {
  const userEl = document.getElementById("login-user");
  const rememberEl = document.getElementById("login-remember");
  try {
    if (rememberEl && rememberEl.checked && userEl && userEl.value) {
      localStorage.setItem(UI_REMEMBER_KEY, userEl.value);
    } else {
      localStorage.removeItem(UI_REMEMBER_KEY);
    }
  } catch {
    /* localStorage is optional in this host */
  }
}

function fillWelcome(state) {
  const firmEl = document.getElementById("welcome-firm");
  if (firmEl) {
    firmEl.textContent = (state && state.firm && state.firm.name) || "CA Unpacker";
  }

  const licenseRow = document.getElementById("welcome-license-row");
  const licenseEl = document.getElementById("welcome-license");
  const license = state && state.license;
  if (licenseRow && licenseEl) {
    let text = "";
    if (license && license.plan_label) {
      if (license.file_limit == null) {
        text = `${license.plan_label} · unlimited files`;
      } else {
        text = `${license.plan_label} · ${license.files_used}/${license.file_limit} files this month`;
      }
    }
    licenseEl.textContent = text;
    licenseRow.hidden = !text;
  }

  const outputRow = document.getElementById("welcome-output-row");
  const outputEl = document.getElementById("welcome-output");
  const outputPath = (state && state.output_path) || "";
  if (outputRow && outputEl) {
    outputEl.textContent = outputPath;
    outputRow.hidden = !outputPath;
  }
}

function routeAfterLogin(state) {
  lastAppState = state;
  if (firmIsConfigured(state)) {
    fillWelcome(state);
    showScreen("welcome");
    syncGuide();
    return;
  }
  showSetup(state);
}

function renderClients(clients) {
  clientListEl.innerHTML = "";
  clientCountEl.textContent = String(clients.length);
  emptyEl.classList.toggle("hidden", clients.length > 0);
  for (const client of clients) {
    const row = document.createElement("div");
    row.className = "client-row";
    row.tabIndex = 0;

    // Entity cluster with avatar badge (Origin UI / 21st.dev style)
    const cluster = document.createElement("div");
    cluster.className = "client-entity-cluster";

    const badge = document.createElement("span");
    badge.className = "client-avatar-badge";
    const initials = (client.name || "CL")
      .split(/\s+/)
      .map((w) => w[0])
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toUpperCase();
    badge.textContent = initials || "CL";

    const name = document.createElement("span");
    name.className = "name";
    name.textContent = client.name;
    cluster.append(badge, name);

    // GSTIN
    const gstin = document.createElement("span");
    gstin.className = "gstin font-mono";
    gstin.textContent = client.gstin || "—";

    // Status Pill with live emerald pulse
    const status = document.createElement("span");
    status.className = "table-status-pill";
    const dot = document.createElement("span");
    dot.className = "pulse-dot";
    const statusText = document.createTextNode(" Active");
    status.append(dot, statusText);

    // Action cluster
    const actions = document.createElement("div");
    actions.className = "row-action-cluster";

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "row-open-trigger";
    openBtn.textContent = "Open →";

    const del = document.createElement("button");
    del.type = "button";
    del.className = "row-delete";
    del.textContent = "Delete";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteClientRow(client);
    });

    actions.append(openBtn, del);
    row.append(cluster, gstin, status, actions);

    row.addEventListener("click", () => openClient(client.id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") openClient(client.id);
    });
    clientListEl.append(row);
  }
}

function renderPeriods(periods) {
  periodListEl.innerHTML = "";
  periodEmptyEl.classList.toggle("hidden", periods.length > 0);
  for (const period of periods) {
    const row = document.createElement("div");
    row.className = "period-row";
    row.tabIndex = 0;
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = period.label;
    const hint = document.createElement("span");
    hint.className = "period-action";
    hint.textContent = "Open dump tray";
    row.append(name, hint);
    row.addEventListener("click", () => openPeriod(period.id));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") openPeriod(period.id);
    });
    periodListEl.append(row);
  }
}

function kindSelect(file, compact) {
  const select = document.createElement("select");
  select.className = "kind-pick";
  for (const kind of kindOptions) {
    const option = document.createElement("option");
    option.value = kind.id;
    option.textContent = kind.label;
    if (kind.id === file.kind) option.selected = true;
    select.append(option);
  }
  select.addEventListener("change", async () => {
    const api = desktopApi();
    if (!api || !api.override_kind) return;
    const result = await api.override_kind(file.id, select.value);
    if (!result.ok) {
      showError(dumpErrorEl, result.error);
      return;
    }
    if (!currentPeriod) return;
    if (api.reparse_period) {
      const r = await api.reparse_period(currentPeriod.id);
      if (r.ok && r.job_id) {
        activeJobId = r.job_id;
        setDumpBusy(true);
        pollJob(r.job_id);
      } else {
        await openPeriod(currentPeriod.id);
      }
    } else {
      await openPeriod(currentPeriod.id);
    }
  });
  if (compact && file.kind !== "unknown") {
    const wrap = document.createElement("div");
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = file.kind_label;
    wrap.append(pill);
    return wrap;
  }
  return select;
}

function setDumpBusy(busy) {
  const authLocked = !devMode && authState && !authState.signed_in;
  addFilesBtn.disabled = busy || authLocked;
  addFolderBtn.disabled = busy || authLocked;
}

function setDumpStatus(summary) {
  dumpStatusEl.textContent = summary.text;
  dumpStatusEl.classList.remove("status-success", "status-warning", "status-failure");
  if (summary.tone === "success") dumpStatusEl.classList.add("status-success");
  if (summary.tone === "warning") dumpStatusEl.classList.add("status-warning");
  if (summary.tone === "failure") dumpStatusEl.classList.add("status-failure");
}

function reviewFiles(files) {
  return (files || []).filter((file) => file.needs_review);
}

function updateReviewNote() {
  const hasUnclassifiedFile = lastFiles.some((file) =>
    file.parse_outcome === "unclassified" || file.kind === "unknown"
  );
  const show = (hasUnclassifiedFile && !packVisible) || reviewFiles(lastFiles).length > 0;
  if (reviewPackNoteEl) reviewPackNoteEl.hidden = !show;
}

function fileNeedsPassword(file) {
  if (!file) return false;
  if (file.needs_password) return true;
  return (file.classify_reason || "").toLowerCase().includes("password");
}

function getFileExt(filename) {
  if (!filename) return "";
  const parts = String(filename).split(".");
  return parts.length > 1 ? "." + parts.pop().toLowerCase() : "";
}

function getFileExtBadge(filename) {
  const ext = getFileExt(filename);
  if (ext === ".pdf") return "PDF";
  if (ext === ".xlsx" || ext === ".xls") return "XLSX";
  if (ext === ".csv") return "CSV";
  if (ext === ".json") return "JSON";
  if (ext === ".xml") return "XML";
  if ([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"].includes(ext)) return "IMG";
  if ([".txt", ".log", ".md", ".py", ".sql"].includes(ext)) return "TXT";
  if (ext === ".docx") return "DOCX";
  return ext ? ext.replace(".", "").toUpperCase() : "FILE";
}

function appendFileRow(container, file, className, globalIndex) {
  const row = document.createElement("div");
  row.className = className;
  if (globalIndex != null) {
    row.setAttribute("data-file-index", String(globalIndex));
    if (globalIndex === selectedFileIndex) {
      row.classList.add("selected");
    }
  }

  const details = document.createElement("div");
  details.className = "file-details";

  const badge = document.createElement("span");
  const extTag = getFileExtBadge(file.original_name || file.name || "");
  badge.className = `file-ext-badge ext-${extTag.toLowerCase()}`;
  badge.textContent = extTag;

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = file.original_name || file.name || "Untitled";
  name.title = file.parse_reason_message || file.classify_reason || file.path || "";

  const outcome = document.createElement("span");
  const outcomeName = window.CAStatusSummary ? window.CAStatusSummary.outcomeLabel(file.parse_outcome) : (file.parse_outcome || "file");
  outcome.className = `pill outcome-${file.parse_outcome || "unclassified"}`;
  outcome.textContent = outcomeName;
  outcome.setAttribute("aria-label", `Outcome: ${outcomeName}`);

  details.append(badge, name, outcome);

  if (file.parse_outcome === "processed" && Number.isFinite(Number(file.parse_row_count))) {
    const rows = document.createElement("span");
    const count = Number(file.parse_row_count);
    rows.className = "file-meta";
    rows.textContent = `${count} ${count === 1 ? "row" : "rows"}`;
    details.append(rows);
  } else if (file.size_formatted || file.size) {
    const sizeSpan = document.createElement("span");
    sizeSpan.className = "file-meta font-mono";
    sizeSpan.textContent = file.size_formatted || (file.size ? (file.size > 1024*1024 ? (file.size/(1024*1024)).toFixed(1) + " MB" : (file.size/1024).toFixed(1) + " KB") : "");
    details.append(sizeSpan);
  }

  const reasonLine = document.createElement("p");
  reasonLine.className = "file-reason";
  reasonLine.textContent = file.parse_reason_message || file.classify_reason || "";
  if (reasonLine.textContent) details.append(reasonLine);

  const actions = document.createElement("div");
  actions.className = "file-actions";

  const previewBtn = document.createElement("button");
  previewBtn.type = "button";
  previewBtn.className = "tool-btn preview-item-btn";
  previewBtn.textContent = "Preview";
  previewBtn.title = "Preview file contents";
  previewBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    if (globalIndex != null) selectFileByIndex(globalIndex);
  });
  actions.append(previewBtn);

  if (fileNeedsPassword(file)) {
    const unlock = document.createElement("button");
    unlock.type = "button";
    unlock.className = "text-btn unlock-btn";
    unlock.textContent = "Unlock";
    unlock.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openUnlockModal(file);
    });
    actions.append(unlock);
  }

  if (file.id != null) {
    actions.append(kindSelect(file, false));
  }

  row.append(details, actions);

  row.addEventListener("click", () => {
    if (globalIndex != null) selectFileByIndex(globalIndex);
  });

  container.append(row);
}

function renderFiles(files) {
  lastFiles = files || [];
  lastFileCount = lastFiles.length;
  if (sourcePeriodCountEl) {
    sourcePeriodCountEl.textContent = String(lastFileCount);
  }

  if (currentFolderSource === "period") {
    currentFolderFiles = lastFiles;
    if (previewFolderPathEl && currentPeriod) {
      previewFolderPathEl.textContent = `Period: ${currentPeriod.label || ""}`;
      previewFolderPathEl.title = `Stored period intake files: ${currentPeriod.label || ""}`;
    }
  }

  renderActiveFolderList();
  updateScanNote();
}

function renderActiveFolderList() {
  const review = currentFolderFiles.filter((file) =>
    window.CAStatusSummary && window.CAStatusSummary.isReviewOutcome(file.parse_outcome)
  );
  const rest = currentFolderFiles.filter((file) =>
    !(window.CAStatusSummary && window.CAStatusSummary.isReviewOutcome(file.parse_outcome))
  );

  reviewBlock.classList.toggle("hidden", review.length === 0);
  updateReviewNote();
  reviewListEl.innerHTML = "";
  for (const file of review) {
    const idx = currentFolderFiles.indexOf(file);
    appendFileRow(reviewListEl, file, "review-row", idx);
  }

  fileListEl.innerHTML = "";
  fileEmptyEl.classList.toggle("hidden", currentFolderFiles.length > 0);
  for (const file of rest) {
    const idx = currentFolderFiles.indexOf(file);
    appendFileRow(fileListEl, file, "file-row", idx);
  }

  // Update preview selection
  if (currentFolderFiles.length > 0) {
    if (selectedFileIndex < 0 || selectedFileIndex >= currentFolderFiles.length) {
      selectFileByIndex(0, false);
    } else {
      selectFileByIndex(selectedFileIndex, false);
    }
  } else {
    selectedFileIndex = -1;
    selectedFile = null;
    updatePreviewToolbar();
    showPreviewPlaceholder();
  }
}

function updatePreviewToolbar() {
  if (!selectedFile) {
    if (previewFileName) previewFileName.textContent = "No file selected";
    if (previewFileSize) previewFileSize.textContent = "";
    if (previewTypeBadge) {
      previewTypeBadge.textContent = "NONE";
      previewTypeBadge.className = "file-type-badge";
    }
    if (previewFileCounter) previewFileCounter.textContent = "0/0";
    if (pdfControls) pdfControls.classList.add("hidden");
    if (sheetTabsContainer) sheetTabsContainer.classList.add("hidden");
    if (btnOpenExternal) btnOpenExternal.disabled = true;
    return;
  }

  if (btnOpenExternal) btnOpenExternal.disabled = false;
  const name = selectedFile.original_name || selectedFile.name || "Document";
  if (previewFileName) {
    previewFileName.textContent = name;
    previewFileName.title = name;
  }
  const size = selectedFile.size_formatted || (selectedFile.size ? (selectedFile.size > 1024*1024 ? (selectedFile.size/(1024*1024)).toFixed(1) + " MB" : (selectedFile.size/1024).toFixed(1) + " KB") : "");
  if (previewFileSize) previewFileSize.textContent = size;
  const badge = getFileExtBadge(name);
  if (previewTypeBadge) {
    previewTypeBadge.textContent = badge;
    previewTypeBadge.className = `file-type-badge ext-${badge.toLowerCase()}`;
  }
  const total = currentFolderFiles.length;
  if (previewFileCounter) {
    previewFileCounter.textContent = `${selectedFileIndex >= 0 ? selectedFileIndex + 1 : 0}/${total}`;
  }
}

async function selectFileByIndex(index, forceScroll = true) {
  if (!currentFolderFiles.length) {
    selectedFileIndex = -1;
    selectedFile = null;
    updatePreviewToolbar();
    showPreviewPlaceholder();
    return;
  }
  const clamped = Math.max(0, Math.min(index, currentFolderFiles.length - 1));
  selectedFileIndex = clamped;
  selectedFile = currentFolderFiles[clamped];
  currentPdfPage = 1;
  isPdfTextMode = false;

  const allRows = document.querySelectorAll(".file-row, .review-row");
  allRows.forEach((row) => row.classList.remove("selected"));
  const activeRow = document.querySelector(`[data-file-index="${clamped}"]`);
  if (activeRow) {
    activeRow.classList.add("selected");
    if (forceScroll) {
      activeRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  updatePreviewToolbar();
  await loadSelectedFilePreview();
}

function showPreviewPlaceholder(msg) {
  hideAllPreviewViewers();
  if (previewPlaceholder) {
    previewPlaceholder.classList.remove("hidden");
    const txt = previewPlaceholder.querySelector(".preview-placeholder-text");
    if (txt) {
      txt.textContent = msg || "Select any file from the folder to preview its contents";
    }
  }
}

function hideAllPreviewViewers() {
  if (previewPlaceholder) previewPlaceholder.classList.add("hidden");
  if (pdfViewer) pdfViewer.classList.add("hidden");
  if (spreadsheetViewer) spreadsheetViewer.classList.add("hidden");
  if (codeViewer) codeViewer.classList.add("hidden");
  if (imageViewer) imageViewer.classList.add("hidden");
  if (previewPasswordViewer) previewPasswordViewer.classList.add("hidden");
  if (binaryViewer) binaryViewer.classList.add("hidden");
  if (pdfControls) pdfControls.classList.add("hidden");
  if (sheetTabsContainer) sheetTabsContainer.classList.add("hidden");
}

async function loadSelectedFilePreview(sheetName = null, passwordOverride = null) {
  if (!selectedFile) return;
  const reqId = ++previewReqCounter;
  if (previewLoadingOverlay) previewLoadingOverlay.classList.remove("hidden");

  try {
    const api = desktopApi();
    if (!api || !api.get_file_preview) {
      if (previewLoadingOverlay) previewLoadingOverlay.classList.add("hidden");
      return;
    }

    const fileId = selectedFile.id != null ? selectedFile.id : null;
    const filePath = selectedFile.path || null;
    const page = currentPdfPage || 1;

    const data = await api.get_file_preview(
      fileId,
      filePath,
      page,
      sheetName,
      passwordOverride
    );

    if (reqId !== previewReqCounter) return;

    hideAllPreviewViewers();

    if (!data.ok) {
      if (data.needs_password) {
        if (previewPasswordViewer) {
          previewPasswordViewer.classList.remove("hidden");
          if (previewUnlockPwd) {
            previewUnlockPwd.value = "";
            previewUnlockPwd.focus();
          }
          if (previewUnlockErr) previewUnlockErr.hidden = true;
        }
      } else {
        showPreviewPlaceholder(data.error || "Could not load preview");
      }
      return;
    }

    if (data.type === "pdf") {
      renderPdfView(data);
    } else if (data.type === "spreadsheet") {
      renderSpreadsheetView(data);
    } else if (data.type === "json" || data.type === "xml" || data.type === "text") {
      renderCodeView(data);
    } else if (data.type === "image") {
      renderImageView(data);
    } else {
      renderBinaryView(data);
    }
  } catch (err) {
    if (reqId === previewReqCounter) {
      showPreviewPlaceholder("Preview failed: " + err.message);
    }
  } finally {
    if (reqId === previewReqCounter && previewLoadingOverlay) {
      previewLoadingOverlay.classList.add("hidden");
    }
  }
}

function renderPdfView(data) {
  currentPdfPage = data.page || 1;
  totalPdfPages = data.total_pages || 1;

  if (pdfControls) pdfControls.classList.remove("hidden");
  if (pdfPageIndicator) pdfPageIndicator.textContent = `${currentPdfPage} / ${totalPdfPages}`;
  if (pdfPrevPage) pdfPrevPage.disabled = currentPdfPage <= 1;
  if (pdfNextPage) pdfNextPage.disabled = currentPdfPage >= totalPdfPages;

  if (pdfPageImg && data.image_data) {
    pdfPageImg.src = data.image_data;
  }
  if (pdfTextLayer) {
    pdfTextLayer.textContent = data.text || "(No selectable text on this page)";
  }

  applyPdfZoom();
  updatePdfViewMode();
  if (pdfViewer) pdfViewer.classList.remove("hidden");
}

function applyPdfZoom() {
  if (pdfPageWrapper) {
    pdfPageWrapper.style.transform = `scale(${currentPdfZoom})`;
  }
  if (pdfZoomLevel) {
    pdfZoomLevel.textContent = `${Math.round(currentPdfZoom * 100)}%`;
  }
}

function updatePdfViewMode() {
  if (isPdfTextMode) {
    if (pdfPageWrapper) pdfPageWrapper.classList.add("hidden");
    if (pdfTextLayer) pdfTextLayer.classList.remove("hidden");
    if (pdfToggleText) {
      pdfToggleText.classList.add("active");
      pdfToggleText.textContent = "Visual";
    }
  } else {
    if (pdfPageWrapper) pdfPageWrapper.classList.remove("hidden");
    if (pdfTextLayer) pdfTextLayer.classList.add("hidden");
    if (pdfToggleText) {
      pdfToggleText.classList.remove("active");
      pdfToggleText.textContent = "Text";
    }
  }
}

function renderSpreadsheetView(data) {
  currentSpreadsheet = data;
  if (spreadsheetInfo) {
    spreadsheetInfo.textContent = `${data.total_rows || 0} rows · ${data.columns ? data.columns.length : 0} columns${data.truncated ? ' (first 250 shown)' : ''}`;
  }

  if (sheetTabsContainer) {
    sheetTabsContainer.innerHTML = "";
    if (data.sheets && data.sheets.length > 1) {
      sheetTabsContainer.classList.remove("hidden");
      data.sheets.forEach((sheet) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `sheet-tab-btn ${sheet === data.active_sheet ? "active" : ""}`;
        btn.textContent = sheet;
        btn.addEventListener("click", () => {
          loadSelectedFilePreview(sheet);
        });
        sheetTabsContainer.appendChild(btn);
      });
    } else {
      sheetTabsContainer.classList.add("hidden");
    }
  }

  if (spreadsheetFilter) spreadsheetFilter.value = "";
  renderSpreadsheetRows(data.columns || [], data.rows || []);
  if (spreadsheetViewer) spreadsheetViewer.classList.remove("hidden");
}

function renderSpreadsheetRows(columns, rows, filter = "") {
  if (!spreadsheetTableContainer) return;
  spreadsheetTableContainer.innerHTML = "";

  const q = (filter || "").toLowerCase().trim();
  const filtered = q
    ? rows.filter((r) => r.some((c) => String(c).toLowerCase().includes(q)))
    : rows;

  const table = document.createElement("table");
  table.className = "preview-grid-table";

  const thead = document.createElement("thead");
  const trHead = document.createElement("tr");

  const thIdx = document.createElement("th");
  thIdx.textContent = "#";
  thIdx.style.width = "40px";
  trHead.appendChild(thIdx);

  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    trHead.appendChild(th);
  });
  thead.appendChild(trHead);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  filtered.forEach((r, idx) => {
    const tr = document.createElement("tr");
    const tdIdx = document.createElement("td");
    tdIdx.textContent = idx + 1;
    tdIdx.style.color = "var(--term-text-dim)";
    tr.appendChild(tdIdx);

    r.forEach((cell) => {
      const td = document.createElement("td");
      td.textContent = cell !== "" ? cell : "—";
      const isNum = cell !== "" && !isNaN(Number(String(cell).replace(/,/g, "")));
      if (isNum) td.className = "num";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  spreadsheetTableContainer.appendChild(table);
}

function renderCodeView(data) {
  if (codeContent) {
    const codeNode = codeContent.querySelector("code") || codeContent;
    codeNode.textContent = data.content || "";
  }
  if (codeMetaBar) {
    const label = data.type === "json" ? "JSON Document" : data.type === "xml" ? "XML Document" : "Text Document";
    const extra = data.meta && data.meta.key_count != null ? ` · ${data.meta.key_count} keys` : (data.line_count ? ` · ${data.line_count} lines` : "");
    codeMetaBar.textContent = `${label} · ${data.size_formatted || ""}${extra}`;
  }
  if (codeViewer) codeViewer.classList.remove("hidden");
}

function renderImageView(data) {
  if (imagePreviewImg && data.image_data) {
    imagePreviewImg.src = data.image_data;
  }
  if (imageMetaBar) {
    imageMetaBar.textContent = `${data.format || "Image"} · ${data.width} × ${data.height} px · ${data.size_formatted || ""}`;
  }
  if (imageViewer) imageViewer.classList.remove("hidden");
}

function renderBinaryView(data) {
  if (binaryFileTitle) binaryFileTitle.textContent = data.filename || "File";
  if (binaryFileDesc) {
    binaryFileDesc.textContent = `${data.detected_kind ? data.detected_kind.toUpperCase() : "Binary Asset"} · ${data.size_formatted || ""}`;
  }
  if (binaryViewer) binaryViewer.classList.remove("hidden");
}

function togglePreviewPane() {
  isPreviewPaneOpen = !isPreviewPaneOpen;
  if (previewSplitContainer) {
    previewSplitContainer.classList.toggle("preview-collapsed", !isPreviewPaneOpen);
  }
  if (btnTogglePreview) {
    btnTogglePreview.classList.toggle("active", isPreviewPaneOpen);
  }
}

function togglePreviewFullscreen() {
  isPreviewFullscreen = !isPreviewFullscreen;
  if (folderPreviewSection) {
    folderPreviewSection.classList.toggle("expanded-fullscreen", isPreviewFullscreen);
  }
  if (btnExpandPreview) {
    btnExpandPreview.classList.toggle("active", isPreviewFullscreen);
    btnExpandPreview.textContent = isPreviewFullscreen ? "Exit" : "Expand";
  }
}

async function switchFolderSource(source) {
  currentFolderSource = source;
  if (tabSourcePeriod) tabSourcePeriod.classList.toggle("active", source === "period");
  if (tabSourceOutput) tabSourceOutput.classList.toggle("active", source === "output");
  if (tabSourceBrowse) tabSourceBrowse.classList.toggle("active", source === "browse");

  const api = desktopApi();
  if (!api) return;

  if (source === "period") {
    currentFolderFiles = lastFiles;
    if (previewFolderPathEl && currentPeriod) {
      previewFolderPathEl.textContent = `Period: ${currentPeriod.label || ""}`;
      previewFolderPathEl.title = `Stored period intake files`;
    }
    renderActiveFolderList();
    return;
  }

  if (source === "output") {
    if (!currentPeriod) {
      showPreviewPlaceholder("Open a period first to view output workpapers.");
      return;
    }
    const outRes = api.get_period_output_path
      ? await api.get_period_output_path(currentPeriod.id)
      : null;
    const path = outRes && outRes.ok ? outRes.path : null;
    if (!path) {
      showPreviewPlaceholder("Output folder not initialized or no workpapers generated yet.");
      return;
    }
    if (previewFolderPathEl) {
      previewFolderPathEl.textContent = path;
      previewFolderPathEl.title = path;
    }
    const listRes = await api.list_folder_files(path);
    if (listRes && listRes.ok) {
      currentFolderFiles = listRes.files || [];
      renderActiveFolderList();
    } else {
      showPreviewPlaceholder("No output pack files found in folder.");
    }
    return;
  }

  if (source === "browse") {
    const picked = await api.pick_folder();
    if (!picked || !picked.ok || !picked.paths || !picked.paths.length) {
      // Revert to period source if cancelled
      switchFolderSource("period");
      return;
    }
    const folder = picked.paths[0];
    customFolderPath = folder;
    if (previewFolderPathEl) {
      previewFolderPathEl.textContent = folder;
      previewFolderPathEl.title = folder;
    }
    const listRes = await api.list_folder_files(folder);
    if (listRes && listRes.ok) {
      currentFolderFiles = listRes.files || [];
      renderActiveFolderList();
    } else {
      showPreviewPlaceholder("Could not read files from selected folder.");
    }
  }
}

function initFilePreview() {
  if (btnTogglePreview) {
    btnTogglePreview.addEventListener("click", togglePreviewPane);
  }
  if (btnExpandPreview) {
    btnExpandPreview.addEventListener("click", togglePreviewFullscreen);
  }

  if (tabSourcePeriod) {
    tabSourcePeriod.addEventListener("click", () => switchFolderSource("period"));
  }
  if (tabSourceOutput) {
    tabSourceOutput.addEventListener("click", () => switchFolderSource("output"));
  }
  if (tabSourceBrowse) {
    tabSourceBrowse.addEventListener("click", () => switchFolderSource("browse"));
  }

  if (btnPrevFile) {
    btnPrevFile.addEventListener("click", () => {
      if (selectedFileIndex > 0) selectFileByIndex(selectedFileIndex - 1);
    });
  }
  if (btnNextFile) {
    btnNextFile.addEventListener("click", () => {
      if (selectedFileIndex < currentFolderFiles.length - 1) selectFileByIndex(selectedFileIndex + 1);
    });
  }

  if (btnOpenExternal) {
    btnOpenExternal.addEventListener("click", async () => {
      if (!selectedFile) return;
      const api = desktopApi();
      if (!api || !api.open_file_in_os) return;
      const path = selectedFile.path || (selectedFile.id != null ? null : null);
      if (path) {
        await api.open_file_in_os(path);
      } else if (selectedFile.id != null && api.get_file_preview) {
        // Fetch path via preview
        const p = await api.get_file_preview(selectedFile.id);
        if (p && p.path) await api.open_file_in_os(p.path);
      }
    });
  }

  if (pdfPrevPage) {
    pdfPrevPage.addEventListener("click", () => {
      if (currentPdfPage > 1) {
        currentPdfPage--;
        loadSelectedFilePreview();
      }
    });
  }
  if (pdfNextPage) {
    pdfNextPage.addEventListener("click", () => {
      if (currentPdfPage < totalPdfPages) {
        currentPdfPage++;
        loadSelectedFilePreview();
      }
    });
  }
  if (pdfZoomIn) {
    pdfZoomIn.addEventListener("click", () => {
      currentPdfZoom = Math.min(2.5, currentPdfZoom + 0.25);
      applyPdfZoom();
    });
  }
  if (pdfZoomOut) {
    pdfZoomOut.addEventListener("click", () => {
      currentPdfZoom = Math.max(0.5, currentPdfZoom - 0.25);
      applyPdfZoom();
    });
  }
  if (pdfFitWidth) {
    pdfFitWidth.addEventListener("click", () => {
      currentPdfZoom = 1.0;
      applyPdfZoom();
    });
  }
  if (pdfToggleText) {
    pdfToggleText.addEventListener("click", () => {
      isPdfTextMode = !isPdfTextMode;
      updatePdfViewMode();
    });
  }

  if (spreadsheetFilter) {
    spreadsheetFilter.addEventListener("input", (e) => {
      if (currentSpreadsheet) {
        renderSpreadsheetRows(currentSpreadsheet.columns || [], currentSpreadsheet.rows || [], e.target.value);
      }
    });
  }

  if (previewUnlockForm) {
    previewUnlockForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pwd = (previewUnlockPwd.value || "").trim();
      if (!pwd) return;
      if (selectedFile && selectedFile.id != null) {
        const api = desktopApi();
        if (api && api.set_file_password) {
          await api.set_file_password(selectedFile.id, pwd);
        }
      }
      await loadSelectedFilePreview(null, pwd);
    });
  }

  if (binaryOpenBtn) {
    binaryOpenBtn.addEventListener("click", () => {
      if (btnOpenExternal) btnOpenExternal.click();
    });
  }

  // Global keyboard navigation
  window.addEventListener("keydown", (e) => {
    const isInput = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);

    if (e.key === "Escape") {
      if (isPreviewFullscreen) {
        togglePreviewFullscreen();
        e.preventDefault();
        return;
      }
    }

    if (e.altKey && (e.key === "p" || e.key === "P")) {
      togglePreviewPane();
      e.preventDefault();
      return;
    }

    if (e.altKey && (e.key === "f" || e.key === "F")) {
      togglePreviewFullscreen();
      e.preventDefault();
      return;
    }

    if (!isInput && isPreviewPaneOpen) {
      if (e.key === "ArrowUp" || e.key === "k") {
        if (selectedFileIndex > 0) {
          selectFileByIndex(selectedFileIndex - 1);
          e.preventDefault();
        }
      } else if (e.key === "ArrowDown" || e.key === "j") {
        if (selectedFileIndex < currentFolderFiles.length - 1) {
          selectFileByIndex(selectedFileIndex + 1);
          e.preventDefault();
        }
      } else if (e.key === "ArrowLeft" && totalPdfPages > 1) {
        if (currentPdfPage > 1) {
          currentPdfPage--;
          loadSelectedFilePreview();
          e.preventDefault();
        }
      } else if (e.key === "ArrowRight" && totalPdfPages > 1) {
        if (currentPdfPage < totalPdfPages) {
          currentPdfPage++;
          loadSelectedFilePreview();
          e.preventDefault();
        }
      }
    }
  });
}

function setOutputLabel(path) {
  const label = document.getElementById("output-label");
  const field = document.getElementById("output-path");
  if (field && path) field.value = path;
  if (label) label.textContent = path ? path : "No output folder";
}

function setPathWarnings(warnings) {
  const text = (warnings || []).join(" ");
  for (const id of ["path-warnings", "desk-path-warnings"]) {
    const node = document.getElementById(id);
    if (!node) continue;
    node.textContent = text;
    node.hidden = !text;
  }
}

function renderLicense(license) {
  const el = document.getElementById("license-label");
  const nameEl = document.getElementById("license-plan-name");
  if (!el) return;
  if (!license) {
    el.textContent = "";
    if (nameEl) nameEl.textContent = "";
    return;
  }
  if (nameEl) nameEl.textContent = license.plan_label || "";
  if (license.file_limit == null) {
    el.textContent = "Unlimited files";
  } else {
    el.textContent = `${license.files_used} / ${license.file_limit} files`;
  }
  const copy = document.getElementById("license-copy");
  if (copy) {
    copy.textContent =
      "Starter is ₹999 for 100 files a month. Pro is ₹2,500 unlimited. All four modules. Suite (₹6,000) is coming. Client files never leave this PC.";
  }
}

function closeProfilePanel() {
  if (!profilePanelEl || !profileButtonEl) return;
  profilePanelEl.hidden = true;
  profileButtonEl.setAttribute("aria-expanded", "false");
}

function renderQuotaBanner(state) {
  if (!quotaBannerEl || !quotaTextEl) return;
  const auth = state || authState;
  if (!auth || !auth.signed_in) {
    quotaBannerEl.classList.add("hidden");
    closeProfilePanel();
    document.body.classList.remove("auth-signed-in");
    return;
  }
  document.body.classList.add("auth-signed-in");
  quotaBannerEl.classList.remove("hidden");

  const email = auth.email || "";
  if (profileInitialEl) {
    profileInitialEl.textContent = email.trim().charAt(0) || "·";
  }
  if (profileButtonEl) {
    profileButtonEl.title = email ? `Account — ${email}` : "Account";
  }
  if (profileEmailEl) profileEmailEl.textContent = email;

  const offline = auth.offline ? " · offline" : "";
  if (profilePlanEl) {
    profilePlanEl.textContent = `${auth.plan || "pro"} plan${offline}`;
  }

  const used = Number(auth.files_used || 0);
  const limit = auth.file_limit;
  if (limit == null) {
    quotaTextEl.textContent = "Unlimited files this month";
    if (profileMeterEl) profileMeterEl.hidden = true;
  } else {
    quotaTextEl.textContent = `${used} of ${limit} files this month`;
    if (profileMeterEl && profileMeterFillEl) {
      profileMeterEl.hidden = false;
      const ratio = limit > 0 ? Math.min(1, used / limit) : 0;
      profileMeterFillEl.style.width = `${Math.round(ratio * 100)}%`;
      profileMeterFillEl.classList.toggle("near-limit", ratio >= 0.8 && ratio < 1);
      profileMeterFillEl.classList.toggle("at-limit", ratio >= 1);
    }
  }
}

function setAuthLocked(locked) {
  document.body.classList.toggle("auth-locked", Boolean(locked));
  if (authGateEl) authGateEl.classList.toggle("hidden", !locked);
  if (dropZone) dropZone.classList.toggle("disabled", Boolean(locked));
  setDumpBusy(Boolean(activeJobId));
}

function applyDevMode(license) {
  devMode = Boolean(license && license.auth_mode === "dev");
  for (const node of document.querySelectorAll(".dev-only")) {
    node.classList.toggle("hidden", !devMode);
  }
}

async function refreshAuthState() {
  const api = desktopApi();
  if (!api || !api.get_auth_state) return null;
  const prevSigned = Boolean(authState && authState.signed_in);
  try {
    authState = await api.get_auth_state();
  } catch {
    authState = { signed_in: false };
  }
  const locked = !devMode && authState && !authState.signed_in;
  setAuthLocked(locked);
  renderQuotaBanner(authState);
  if (!prevSigned && authState && authState.signed_in) {
    const api2 = desktopApi();
    if (api2 && api2.get_state) {
      api2.get_state().then((s) => {
        if (s && s.firm && s.output_path) showDesk(s);
        else showSetup(s || lastAppState);
      }).catch(() => {});
    }
  }
  return authState;
}

async function ensurePostAuth() {
  try {
    await refreshAuthState();
    const api = desktopApi();
    if (api && api.get_state) {
      const state = await api.get_state();
      if (state && state.firm && state.output_path) {
        if (typeof showDesk === "function") showDesk(state);
        else if (typeof showScreen === "function") showScreen("desk");
      } else if (typeof showSetup === "function") {
        showSetup(state || {});
      }
    }
  } catch (e) {
    if (typeof refreshAuthState === "function") {
      try { await refreshAuthState(); } catch {}
    }
  }
}

function showDesk(state) {
  lastAppState = state;
  showScreen("desk");
  firmLabelEl.textContent = state.firm ? state.firm.name : "";
  setOutputLabel(state.output_path || "");
  setPathWarnings(state.path_warnings || []);
  applyDevMode(state.license);
  renderLicense(state.license);
  renderQuotaBanner(state.auth || authState);
  renderClients(state.clients || []);
  showPane("clients");
  recordNav({ pane: "clients" });
  syncGuide();
}

function showSetup(state) {
  lastAppState = state;
  showScreen("setup");
  const lib = document.getElementById("library-path");
  if (lib) lib.textContent = state.library_path || "";
  setOutputLabel(state.output_path || "");
  setPathWarnings(state.path_warnings || []);
  applyDevMode(state.license);
  renderLicense(state.license);
  renderQuotaBanner(state.auth || authState);
  if (state.firm && state.firm.name) firmNameEl.value = state.firm.name;
  firmNameEl.focus();
  syncGuide();
}

async function openClient(clientId) {
  showError(periodErrorEl, "");
  const result = await window.pywebview.api.get_client_desk(clientId);
  if (!result.ok) {
    showError(deskErrorEl, result.error);
    return;
  }
  currentClient = result.client;
  periodClientNameEl.textContent = result.client.name;
  periodLabelEl.value = result.suggested_period || "";
  renderPeriods(result.periods);
  lastPeriodCount = (result.periods || []).length;
  showPane("periods");
  recordNav({ pane: "periods", clientId: currentClient.id });
  syncGuide();
}

async function openPeriod(periodId) {
  showError(dumpErrorEl, "");
  const result = await window.pywebview.api.get_period_desk(periodId);
  if (!result.ok) {
    showError(periodErrorEl, result.error);
    return;
  }
  currentPeriod = result.period;
  kindOptions = result.kinds || [];
  dumpTitleEl.textContent = result.period.label;
  dumpEyebrowEl.textContent = result.client ? result.client.name : "Dump tray";
  renderFiles(result.files || []);
  renderPack(result.pack);
  renderPreview(result.preview);
  setDumpStatus(window.CAStatusSummary.summarizeFiles(result.files || []));
  showPane("dump");
  refreshTesseractNote();
  recordNav({
    pane: "dump",
    clientId: currentClient ? currentClient.id : result.client && result.client.id,
    periodId: currentPeriod.id,
  });
  syncGuide();
}

function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dash(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function textCell(value, className) {
  const td = document.createElement("td");
  if (className) td.className = className;
  td.textContent = dash(value);
  return td;
}

function moneyCell(value) {
  const td = document.createElement("td");
  td.className = "num";
  td.textContent = money(value);
  return td;
}

function renderPack(pack) {
  packHasBank = false;
  packOpenKey = "";
  const preflightApi = window.CAPreflightSummary;
  const blocked = Boolean(preflightApi && preflightApi.preflightBlocked(pack));
  packVisible = Boolean(pack && pack.exists);
  packBlock.classList.remove("match", "mismatch");
  packBlock.classList.toggle("blocked", blocked);
  if (!pack || (!pack.exists && !blocked)) {
    packBlock.classList.add("hidden");
    updateReviewNote();
    return;
  }
  packBlock.classList.remove("hidden");
  const packTitleEl = document.getElementById("pack-title");
  if (packTitleEl) {
    packTitleEl.textContent = blocked ? "Pack stopped before writing" : "Normalized Excel Data Pack";
  }
  const openPackBtn = document.getElementById("open-pack");
  if (openPackBtn) openPackBtn.disabled = !packVisible;
  const bankOut = (pack.outputs || []).find((out) => out.key === "bank");
  const purchaseOut = (pack.outputs || []).find((out) => out.key === "purchase");
  packHasBank = Boolean(bankOut);
  packOpenKey = bankOut ? "bank" : purchaseOut ? "purchase" : "";
  if (pack.balance_status === "match") packBlock.classList.add("match");
  if (pack.balance_status === "mismatch") packBlock.classList.add("mismatch");
  const packRows = Number(pack.row_count || 0);
  const preflightNote = preflightApi ? preflightApi.summaryText(pack.preflight) : "";
  if (blocked) {
    packMetaEl.textContent = preflightApi
      ? preflightApi.blockedHeadline(pack.preflight)
      : "Stopped before writing. Nothing was packed.";
  } else {
    packMetaEl.textContent = `Excel ready · ${packRows} ${packRows === 1 ? "row" : "rows"}${preflightNote ? " · " + preflightNote : ""}`;
  }
  packFilesEl.innerHTML = "";
  if (preflightApi) {
    for (const issue of preflightApi.visibleIssues(pack)) {
      packFilesEl.append(preflightLine(issue, preflightApi));
    }
    if (blocked && (pack.outputs || []).length) {
      const note = document.createElement("p");
      note.className = "pack-preflight-line";
      note.textContent = "The pack below is from an earlier run and was left unchanged.";
      packFilesEl.append(note);
    }
  }
  if (bankOut && !pack.balance_status) {
    const note = document.createElement("p");
    note.className = "file-flag";
    note.textContent = "Balance not checked";
    packFilesEl.append(note);
  }
  for (const out of pack.outputs || []) {
    const line = document.createElement("p");
    line.className = "file-flag";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "text-btn";
    const rowsWord = Number(out.rows) === 1 ? "row" : "rows";
    btn.textContent = `${out.label} · ${out.rows} ${rowsWord}${out.status && out.status !== "ready" ? " · " + out.status : ""}`;
    btn.addEventListener("click", async () => {
      const opened = await window.pywebview.api.open_bank_pack(currentPeriod.id, out.key);
      if (!opened.ok) showError(dumpErrorEl, opened.error);
    });
    line.append(btn);
    packFilesEl.append(line);
  }
  for (const file of pack.files || []) {
    const line = document.createElement("div");
    line.className = "file-flag";
    const head = document.createElement("div");
    head.className = "pack-file-head";
    const name = document.createElement("span");
    name.textContent = `${file.filename} · ${file.row_count} lines`;
    const chip = document.createElement("span");
    chip.className = "pill";
    if (file.status === "match") {
      chip.classList.add("match");
      chip.textContent = "MATCH";
    } else if (file.status === "mismatch") {
      chip.classList.add("mismatch");
      chip.textContent = "MISMATCH";
    } else if (file.status === "unverified") {
      chip.textContent = "COULD NOT VERIFY";
    } else {
      chip.textContent = "Balance not checked";
    }
    head.append(name, chip);
    const moneyLine = document.createElement("p");
    moneyLine.textContent = `Opening ${money(file.opening_balance)} · Stated close ${money(file.stated_closing)} · Computed close ${money(file.computed_closing)}`;
    line.append(head, moneyLine);
    packFilesEl.append(line);
  }
  updateReviewNote();
  renderRecon(pack);
}

function preflightLine(issue, preflightApi) {
  const line = document.createElement("p");
  line.className = "pack-preflight-line";
  const chip = document.createElement("span");
  chip.className = "pill";
  chip.classList.add(issue && issue.level === "blocking" ? "mismatch" : "unknown");
  chip.textContent = preflightApi.levelLabel(issue && issue.level);
  const text = document.createElement("span");
  text.textContent = preflightApi.issueText(issue);
  line.append(chip, text);
  return line;
}

function reconStatusPill(status) {
  const chip = document.createElement("span");
  chip.className = "pill";
  if (status === "matched") chip.classList.add("match");
  else if (status === "likely") chip.classList.add("mute");
  else chip.classList.add("mismatch");
  chip.textContent = window.CAReconSummary.reconStatusLabel(status);
  return chip;
}

function renderRecon(pack) {
  lastPack = pack;
  if (!reconBlock) return;
  const api = window.CAReconSummary;
  if (!api || !api.hasRecon(pack)) {
    reconBlock.classList.add("hidden");
    if (reconTableEl) reconTableEl.innerHTML = "";
    return;
  }
  reconBlock.classList.remove("hidden");
  if (reconCountsEl) reconCountsEl.textContent = api.reconCountsText(pack.recon.counts);
  if (reconFiltersEl) {
    for (const btn of reconFiltersEl.querySelectorAll("[data-recon-filter]")) {
      const active = btn.getAttribute("data-recon-filter") === reconFilter;
      btn.classList.toggle("ghost", !active);
    }
  }
  if (!reconTableEl) return;
  reconTableEl.innerHTML = "";
  const table = document.createElement("table");
  table.className = "preview-table";
  table.innerHTML =
    "<thead><tr><th>Status</th><th>Party</th><th>GSTIN</th><th>Invoice</th><th>Amount (2B)</th><th>Amount (books)</th><th>Bank hint</th></tr></thead>";
  const body = document.createElement("tbody");
  const rows = api.filterReconRows(pack.recon.rows || [], reconFilter);
  for (const row of rows) {
    const tr = document.createElement("tr");
    const statusTd = document.createElement("td");
    statusTd.append(reconStatusPill(row.status));
    const gstinTd = document.createElement("td");
    gstinTd.className = "gstin";
    gstinTd.textContent = dash(row.gstin);
    tr.append(
      statusTd,
      textCell(row.party),
      gstinTd,
      textCell(api.reconInvoiceDisplay(row)),
      moneyCell(row.amount_2b),
      moneyCell(row.amount_books),
      textCell(row.bank_hint)
    );
    body.append(tr);
  }
  table.append(body);
  reconTableEl.append(table);
}

function looksLikeGstin(value) {
  if (value === null || value === undefined || value === "") return false;
  return String(value).trim().length === 15;
}

function cropCaptionValue(field, value) {
  if (field === "supplier_gstin" || looksLikeGstin(value)) {
    const raw = value === null || value === undefined ? "" : String(value).trim();
    return raw || "—";
  }
  return money(value);
}

function flagList(row) {
  let raw = row && (row.flags != null ? row.flags : row.validation_flags);
  if (raw == null || raw === "") return [];
  if (Array.isArray(raw)) return raw.map(String).map((item) => item.trim()).filter(Boolean);
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.map(String).map((item) => item.trim()).filter(Boolean);
        }
      } catch {
        /* fall through */
      }
    }
    return trimmed.split(/[,;]+/).map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function flagsCell(row) {
  const td = document.createElement("td");
  td.className = "flags";
  const flags = flagList(row);
  if (!flags.length) {
    td.textContent = "—";
    return td;
  }
  const wrap = document.createElement("div");
  wrap.className = "flag-list";
  for (const flag of flags) {
    const pill = document.createElement("span");
    pill.className = "pill mute";
    pill.textContent = flag;
    wrap.append(pill);
  }
  td.append(wrap);
  return td;
}

function amountCell(file, row, field, value) {
  const td = document.createElement("td");
  const gstinish = field === "supplier_gstin" || looksLikeGstin(value);
  td.className = gstinish ? "gstin" : "num";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "source-amt";
  btn.textContent = cropCaptionValue(field, value);
  btn.title = "View source";
  btn.addEventListener("click", () => openSourceCrop(file, row, field, value));
  btn.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      openSourceCrop(file, row, field, value);
    }
  });
  td.append(btn);
  return td;
}

function renderPreview(preview) {
  const files = (preview && preview.files) || [];
  lastPreviewFiles = files;
  if (!files.length) {
    previewBlock.classList.add("hidden");
    updateScanNote();
    return;
  }
  previewBlock.classList.remove("hidden");
  previewListEl.innerHTML = "";
  for (const file of files) {
    const title = document.createElement("p");
    title.className = "eyebrow";
    const previewRows = Number(file.row_count || 0);
    title.textContent = `${file.filename} · ${file.kind || ""} · ${previewRows} ${previewRows === 1 ? "row" : "rows"}`;
    const table = document.createElement("table");
    table.className = "preview-table";
    const isBank = file.kind === "bank";
    const isInvoice = file.kind === "invoice";
    const isGstrInv = file.kind === "gstr_2b" || file.kind === "gstr_1";
    const isGstr3b = file.kind === "gstr_3b";
    const isBooks = file.kind === "tally" || file.kind === "zoho";
    table.innerHTML = isGstrInv
      ? "<thead><tr><th>Date</th><th>GSTIN</th><th>Trade</th><th>Invoice no</th><th>Taxable</th><th>Value</th><th>Flags</th></tr></thead>"
      : isGstr3b
        ? "<thead><tr><th>Section</th><th>Taxable</th><th>IGST</th><th>CGST</th><th>SGST</th><th>Cess</th></tr></thead>"
        : isInvoice
          ? "<thead><tr><th>Date</th><th>Supplier</th><th>GSTIN</th><th>Invoice no</th><th>Taxable</th><th>Tax</th><th>Value</th><th>Flags</th></tr></thead>"
          : isBank
            ? "<thead><tr><th>Date</th><th>Detail</th><th>Debit</th><th>Credit</th><th>Balance</th><th>Page</th></tr></thead>"
            : isBooks
              ? "<thead><tr><th>Register</th><th>Date</th><th>Party</th><th>GSTIN</th><th>Invoice no</th><th>Value</th><th>Flags</th></tr></thead>"
              : "<thead><tr><th>Date</th><th>Detail</th><th>Debit / Taxable</th><th>Credit / Tax</th><th>Balance / Value</th></tr></thead>";
    const body = document.createElement("tbody");
    const rows = file.preview || [];
    for (const row of rows) {
      const tr = document.createElement("tr");
      if (isGstrInv) {
        tr.append(
          textCell(row.invoice_date),
          textCell(row.gstin, "gstin"),
          textCell(row.trade_name),
          textCell(row.invoice_number),
          moneyCell(row.taxable),
          moneyCell(row.invoice_value),
          flagsCell(row)
        );
      } else if (isGstr3b) {
        tr.append(
          textCell(row.section),
          moneyCell(row.taxable),
          moneyCell(row.igst),
          moneyCell(row.cgst),
          moneyCell(row.sgst),
          moneyCell(row.cess)
        );
      } else if (isBooks) {
        tr.append(
          textCell(row.register),
          textCell(row.invoice_date || row.date),
          textCell(row.supplier_name || row.party_name),
          textCell(row.supplier_gstin || row.gstin, "gstin"),
          textCell(row.invoice_number || row.voucher_number),
          moneyCell(row.invoice_value ?? row.amount),
          flagsCell(row)
        );
      } else {
        const detail = row.description || row.trade_name || row.party_name || row.section || row.invoice_number || "";
        const dateTd = document.createElement("td");
        dateTd.textContent = row.date || row.invoice_date || "";
        if (isInvoice) {
          const supplierTd = document.createElement("td");
          supplierTd.textContent = row.supplier_name || row.trade_name || row.party_name || "";
          const invTd = document.createElement("td");
          invTd.textContent = row.invoice_number || "";
          const gstin = row.supplier_gstin || row.gstin || "";
          const taxable = row.taxable_value ?? row.taxable;
          const value = row.invoice_value ?? row.amount;
          tr.append(
            dateTd,
            supplierTd,
            amountCell(file, row, "supplier_gstin", gstin),
            invTd,
            amountCell(file, row, "taxable_value", taxable),
            amountCell(file, row, "tax", row.tax),
            amountCell(file, row, "invoice_value", value),
            flagsCell(row)
          );
        } else {
          const detailTd = document.createElement("td");
          detailTd.textContent = detail;
          if (isBank) {
            const page = row.source_page == null ? "" : String(row.source_page);
            const pageTd = document.createElement("td");
            pageTd.className = "num";
            pageTd.textContent = page;
            tr.append(
              dateTd,
              detailTd,
              amountCell(file, row, "Debit", row.debit),
              amountCell(file, row, "Credit", row.credit),
              amountCell(file, row, "Balance", row.balance),
              pageTd
            );
          } else {
            const left = row.debit ?? row.taxable_value ?? row.taxable;
            const mid = row.credit ?? row.tax;
            const right = row.balance ?? row.invoice_value ?? row.amount;
            const leftTd = document.createElement("td");
            leftTd.className = "num";
            leftTd.textContent = money(left);
            const midTd = document.createElement("td");
            midTd.className = "num";
            midTd.textContent = money(mid);
            const rightTd = document.createElement("td");
            rightTd.className = "num";
            rightTd.textContent = money(right);
            tr.append(dateTd, detailTd, leftTd, midTd, rightTd);
          }
        }
      }
      body.append(tr);
    }
    if (rows.length < (file.row_count || 0)) {
      const omitted = (file.row_count || 0) - rows.length;
      const spacer = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = isGstrInv || isBooks ? 7 : isGstr3b || isBank ? 6 : isInvoice ? 8 : 5;
      cell.className = "omit";
      cell.textContent = `… ${omitted} lines omitted — open Excel …`;
      spacer.append(cell);
      if (body.children.length > 8) {
        body.insertBefore(spacer, body.children[8]);
      } else {
        body.append(spacer);
      }
    }
    table.append(body);
    previewListEl.append(title, table);
    if (isInvoice) {
      const note = document.createElement("p");
      note.className = "preview-note";
      note.textContent = "Click a GSTIN or amount to see it on the bill.";
      previewListEl.append(note);
    }
    if (isGstrInv || isGstr3b) {
      const note = document.createElement("p");
      note.className = "preview-note";
      note.textContent = window.CAReconSummary.gstrPreviewNote(window.CAReconSummary.hasRecon(lastPack));
      previewListEl.append(note);
    }
    if (isBooks) {
      const note = document.createElement("p");
      note.className = "preview-note";
      note.textContent = "Purchase and sales also go into the register Excels.";
      previewListEl.append(note);
    }
  }
  updateScanNote();
}

function closeCropModal() {
  if (!cropModal) return;
  cropModal.classList.add("hidden");
  if (cropImageEl) {
    cropImageEl.removeAttribute("src");
    cropImageEl.alt = "Page crop";
  }
}

async function openSourceCrop(file, row, field, value) {
  const api = desktopApi();
  if (!api || !api.get_source_crop) return;
  const fieldBox = row.fields && row.fields[field];
  const page = (fieldBox && fieldBox.page) || row.source_page || 1;
  const bbox = (fieldBox && fieldBox.bbox) || row.source_bbox || "";
  let result;
  try {
    result = await api.get_source_crop(file.file_id || file.id, page, bbox);
  } catch {
    showError(dumpErrorEl, "Could not load the page crop.");
    return;
  }
  if (!result || !result.ok) {
    showError(dumpErrorEl, (result && result.error) || "Could not load the page crop.");
    return;
  }
  const src = result.data_url || result.path || "";
  if (!src) {
    showError(dumpErrorEl, "Could not load the page crop.");
    return;
  }
  cropImageEl.src = src;
  cropImageEl.alt = `${file.filename || "Statement"} page ${page}`;
  cropCaptionEl.textContent = `${file.filename} · page ${page} · ${field} ${cropCaptionValue(field, value)}`;
  cropModal.classList.remove("hidden");
}

function closeUnlockModal() {
  if (!unlockModal) return;
  unlockModal.classList.add("hidden");
  unlockFile = null;
  if (unlockPasswordEl) unlockPasswordEl.value = "";
  if (unlockErrorEl) showError(unlockErrorEl, "");
}

function openUnlockModal(file) {
  unlockFile = file;
  if (unlockFilenameEl) unlockFilenameEl.textContent = file.original_name || "Unlock PDF";
  if (unlockPasswordEl) unlockPasswordEl.value = "";
  if (unlockErrorEl) showError(unlockErrorEl, "");
  unlockModal.classList.remove("hidden");
  if (unlockPasswordEl) unlockPasswordEl.focus();
}

async function submitUnlock(event) {
  if (event) event.preventDefault();
  if (!unlockFile) return;
  const api = desktopApi();
  if (!api || !api.set_file_password) {
    showError(unlockErrorEl, "Update the app to unlock PDFs.");
    if (unlockPasswordEl) unlockPasswordEl.value = "";
    return;
  }
  const secret = unlockPasswordEl ? unlockPasswordEl.value : "";
  if (unlockPasswordEl) unlockPasswordEl.value = "";
  let result;
  try {
    result = await api.set_file_password(unlockFile.id, secret);
  } catch {
    showError(unlockErrorEl, "Could not unlock that file.");
    return;
  }
  if (!result || !result.ok) {
    showError(unlockErrorEl, (result && result.error) || "Could not unlock that file.");
    return;
  }
  const periodId = currentPeriod && currentPeriod.id;
  closeUnlockModal();
  if (!periodId) return;
  if (api.reparse_period) {
    let job;
    try {
      job = await api.reparse_period(periodId);
    } catch {
      showError(dumpErrorEl, "Could not re-read the period.");
      return;
    }
    if (job && job.ok && job.job_id) {
      activeJobId = job.job_id;
      setDumpBusy(true);
      pollJob(job.job_id);
    } else if (job && !job.ok) {
      showError(dumpErrorEl, job.error || "Could not re-read the period.");
    } else {
      await openPeriod(periodId);
    }
  } else {
    await openPeriod(periodId);
  }
}

function updateScanNote() {
  if (!scanNoteEl) return;
  if (tesseractFound) {
    scanNoteEl.classList.add("hidden");
    return;
  }
  const emptyScannedBank = lastFiles.some((file) => {
    if (file.kind !== "bank") return false;
    const reason = (file.classify_reason || "").toLowerCase();
    if (!/scan|ocr|tesseract|image|raster|photo/.test(reason)) return false;
    const preview = lastPreviewFiles.find((item) => item.file_id === file.id);
    return !preview || !preview.row_count;
  });
  scanNoteEl.classList.toggle("hidden", !emptyScannedBank);
}

async function refreshTesseractNote() {
  const api = desktopApi();
  if (!tesseractChecked && api && api.tesseract_status) {
    tesseractChecked = true;
    try {
      const status = await api.tesseract_status();
      tesseractFound = Boolean(status && status.found);
    } catch {
      tesseractFound = true;
    }
  }
  updateScanNote();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function pathsFromDropEvent(event) {
  const paths = [];
  const seen = new Set();
  const add = (path) => {
    if (!path) return;
    const key = String(path).toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    paths.push(path);
  };
  const files = (event.dataTransfer && event.dataTransfer.files) || [];
  for (const file of files) {
    add(file.pywebviewFullPath || file.path);
  }
  const api = window.pywebview && window.pywebview.api;
  if (api && api.take_drop_paths) {
    try {
      const extra = await api.take_drop_paths();
      if (extra && extra.ok) {
        for (const path of extra.paths || []) add(path);
      }
    } catch {
      /* native drop list is optional */
    }
  }
  return paths;
}

async function startDump(paths) {
  if (!currentPeriod) return;
  if (!devMode && authState && !authState.signed_in) {
    showError(dumpErrorEl, "Sign in to process files.");
    return;
  }
  if (!paths || !paths.length) {
    showError(dumpErrorEl, "No files or folders were chosen.");
    return;
  }
  showError(dumpErrorEl, "");
  setDumpStatus({ tone: "progress", text: "Sorting…" });
  setDumpBusy(true);
  const result = await window.pywebview.api.start_dump(currentPeriod.id, paths);
  if (!result.ok) {
    showError(dumpErrorEl, result.error);
    activeJobId = null;
    setDumpBusy(false);
    setDumpStatus(window.CAStatusSummary.summarizeFiles(lastFiles));
    return;
  }
  activeJobId = result.job_id;
  pollJob(result.job_id);
}

function pollJob(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (jobId !== activeJobId) return;
    const result = await window.pywebview.api.get_job(jobId);
    if (jobId !== activeJobId) return;
    if (!result.ok) return;
    const job = result.job;
    if (job.status === "routing" || job.status === "queued" || job.status === "parsing") {
      renderFiles(job.files || []);
      setDumpStatus({
        tone: "progress",
        text: job.status === "parsing"
          ? "Reading bank PDF…"
          : `Sorting ${(job.files || []).length}…`,
      });
      return;
    }
    clearInterval(pollTimer);
    pollTimer = null;
    if (jobId !== activeJobId) return;
    activeJobId = null;
    setDumpBusy(false);
    const failed = job.status === "failed";
    const jobError = job.error_message || "Could not sort those files.";
    const passwordFail = failed && /password/i.test(job.error_message || "");
    if (failed) {
      showError(dumpErrorEl, jobError);
    }
    const dumpVisible = !paneDump.classList.contains("hidden");
    if (dumpVisible && currentPeriod && currentPeriod.id === job.period_id) {
      await openPeriod(currentPeriod.id);
      if (job.blocked) {
        setDumpStatus({
          tone: "failure",
          text: job.error_message || "Pre-flight stopped this pack. Nothing was written.",
        });
      } else {
        setDumpStatus(window.CAStatusSummary.summarizeJobStatus(job));
      }
    }
    if (passwordFail) {
      showError(dumpErrorEl, jobError);
      const locked = lastFiles.find(fileNeedsPassword);
      if (locked) openUnlockModal(locked);
    }
    if (job.warnings && job.warnings.length) {
      showError(dumpErrorEl, job.warnings.join(" · "));
    }
    syncGuide();
  }, 350);
}

async function chooseOutputFolder() {
  showError(setupErrorEl, "");
  const picked = await window.pywebview.api.pick_output_folder();
  if (!picked.ok) {
    showError(setupErrorEl, picked.error);
    return "";
  }
  setOutputLabel(picked.output_path);
  setPathWarnings(picked.path_warnings || []);
  syncGuide();
  return picked.output_path;
}

function clearGuideHighlight() {
  if (lastGuideHighlight) {
    lastGuideHighlight.classList.remove("guide-target");
    lastGuideHighlight = null;
  }
}

function highlightGuide(selector) {
  clearGuideHighlight();
  if (!selector) return;
  const el = document.querySelector(selector);
  if (!el) return;
  el.classList.add("guide-target");
  lastGuideHighlight = el;
}

function guideOnSetup() {
  return !setupEl.classList.contains("hidden");
}

function currentGuideCard() {
  const onSetup = guideOnSetup();
  const onClients = !paneClients.classList.contains("hidden");
  const onPeriods = !panePeriods.classList.contains("hidden");
  const onDump = !paneDump.classList.contains("hidden");
  const clientCount = clientListEl.children.length;
  const periodCount = periodListEl.children.length;
  const hasFiles = lastFileCount > 0;
  const hasPack = packVisible;
  const folderChosen = Boolean(document.getElementById("output-path") && document.getElementById("output-path").value);

  if (onSetup) {
    if (!folderChosen) {
      return {
        kicker: "Step 1 of 5",
        title: "Name the firm, then pick a folder",
        copy: "Type the firm name. Then click Choose folder — that is where cleaned Excels will be saved.",
        items: ["Type the firm name.", "Click Choose folder.", "After the path appears, click Open the desk."],
        highlight: "#pick-output",
      };
    }
    return {
      kicker: "Step 1 of 5",
      title: "Open the desk",
      copy: "Folder is set. Click Open the desk to continue.",
      items: ["Click Open the desk."],
      highlight: "#save-firm",
    };
  }
  if (onClients && clientCount === 0) {
    return {
      kicker: "Step 2 of 5",
      title: "Add the first client",
      copy: "Type the legal name as you file it, then click Add client. GSTIN is optional.",
      items: ["Type the client name.", "Click Add client."],
      highlight: "#add-form",
    };
  }
  if (onClients && clientCount > 0) {
    return {
      kicker: "Step 3 of 5",
      title: "Open that client",
      copy: "Click the client row you just added. Periods live under the client.",
      items: ["Click the client name in the list."],
      highlight: "#client-list .client-row",
    };
  }
  if (onPeriods && periodCount === 0) {
    return {
      kicker: "Step 3 of 5",
      title: "Add this month’s period",
      copy: "Type the month you are working on, for example Aug 2026, then click Add period.",
      items: ["Check the period box.", "Click Add period."],
      highlight: "#period-form",
    };
  }
  if (onPeriods && periodCount > 0) {
    return {
      kicker: "Step 4 of 5",
      title: "Open the period",
      copy: "Click the period row. That is the dump tray for this month.",
      items: ["Click the period in the list."],
      highlight: "#period-list .period-row",
    };
  }
  if (onDump && !hasFiles) {
    return {
      kicker: "Step 4 of 5",
      title: "Dump this month’s files",
      copy: "Click Add folder and pick the mixed folder, or drop that folder onto the dashed box. Nested files are included. Bank PDFs, invoices, GSTR JSON and Tally/Zoho can go in together.",
      items: ["Click Add folder, or drop a folder on the dashed box."],
      highlight: "#add-folder",
    };
  }
  if (onDump && hasFiles && !hasPack) {
    return {
      kicker: "Step 4 of 5",
      title: "Wait for the pack",
      copy: "The app is sorting files on this PC. Unknown or unreadable files stay in Needs review until they convert.",
      items: ["Wait until an Excel pack appears below.", "If a file is Unknown, set its type."],
      highlight: "#drop-zone",
    };
  }
  if (onDump && hasPack) {
    return {
      kicker: "Step 5 of 5",
      title: "Open the Excel pack",
      copy: "Click Open in Excel. Click an amount in Spot-check if you want to see it on the original page.",
      items: ["Click Open in Excel.", "Optional: click an amount to see the source crop."],
      highlight: "#open-pack",
    };
  }
  return null;
}

function renderGuideList(items) {
  const list = document.getElementById("guide-list");
  if (!list) return;
  list.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = item;
    list.append(li);
  }
}

function deskIsVisible() {
  return deskEl && !deskEl.classList.contains("hidden");
}

function syncGuide() {
  const card = document.getElementById("guide");
  if (!card) return;
  const onSetup = guideOnSetup();
  if (onSetup || guideDismissed || !deskIsVisible()) {
    card.classList.add("hidden");
    clearGuideHighlight();
    if (onSetup) {
      const folderChosen = Boolean(document.getElementById("output-path") && document.getElementById("output-path").value);
      highlightGuide(folderChosen ? "#save-firm" : "#pick-output");
    }
    return;
  }
  const step = currentGuideCard();
  if (!step) {
    card.classList.add("hidden");
    clearGuideHighlight();
    return;
  }
  document.getElementById("guide-kicker").textContent = step.kicker;
  document.getElementById("guide-title").textContent = step.title;
  document.getElementById("guide-copy").textContent = step.copy;
  renderGuideList(step.items);
  card.classList.remove("hidden");
  highlightGuide(step.highlight);
}

async function dismissGuide() {
  guideDismissed = true;
  const api = desktopApi();
  if (api && api.set_guide_dismissed) {
    await api.set_guide_dismissed(true);
  }
  syncGuide();
}

async function reopenGuide() {
  guideDismissed = false;
  const api = desktopApi();
  if (api && api.set_guide_dismissed) {
    await api.set_guide_dismissed(false);
  }
  syncGuide();
}

async function deleteClientRow(client) {
  if (!window.confirm(`Delete ${client.name} and every file dumped for them on this PC?`)) {
    return;
  }
  showError(deskErrorEl, "");
  const result = await window.pywebview.api.delete_client_desk(client.id);
  if (!result.ok) {
    showError(deskErrorEl, result.error);
    return;
  }
  if (currentClient && currentClient.id === client.id) {
    showError(setupErrorEl, picked.error);
    return "";
  }
  setOutputLabel(picked.output_path);
  setPathWarnings(picked.path_warnings || []);
  syncGuide();
  return picked.output_path;
}

function clearGuideHighlight() {
  if (lastGuideHighlight) {
    lastGuideHighlight.classList.remove("guide-target");
    lastGuideHighlight = null;
  }
}

function highlightGuide(selector) {
  clearGuideHighlight();
  if (!selector) return;
  const el = document.querySelector(selector);
  if (!el) return;
  el.classList.add("guide-target");
  lastGuideHighlight = el;
}

function guideOnSetup() {
  return !setupEl.classList.contains("hidden");
}

function currentGuideCard() {
  const onSetup = guideOnSetup();
  const onClients = !paneClients.classList.contains("hidden");
  const onPeriods = !panePeriods.classList.contains("hidden");
  const onDump = !paneDump.classList.contains("hidden");
  const clientCount = clientListEl.children.length;
  const periodCount = periodListEl.children.length;
  const hasFiles = lastFileCount > 0;
  const hasPack = packVisible;
  const folderChosen = Boolean(document.getElementById("output-path") && document.getElementById("output-path").value);

  if (onSetup) {
    if (!folderChosen) {
      return {
        kicker: "Step 1 of 5",
        title: "Name the firm, then pick a folder",
        copy: "Type the firm name. Then click Choose folder — that is where cleaned Excels will be saved.",
        items: ["Type the firm name.", "Click Choose folder.", "After the path appears, click Open the desk."],
        highlight: "#pick-output",
      };
    }
    return {
      kicker: "Step 1 of 5",
      title: "Open the desk",
      copy: "Folder is set. Click Open the desk to continue.",
      items: ["Click Open the desk."],
      highlight: "#save-firm",
    };
  }
  if (onClients && clientCount === 0) {
    return {
      kicker: "Step 2 of 5",
      title: "Add the first client",
      copy: "Type the legal name as you file it, then click Add client. GSTIN is optional.",
      items: ["Type the client name.", "Click Add client."],
      highlight: "#add-form",
    };
  }
  if (onClients && clientCount > 0) {
    return {
      kicker: "Step 3 of 5",
      title: "Open that client",
      copy: "Click the client row you just added. Periods live under the client.",
      items: ["Click the client name in the list."],
      highlight: "#client-list .client-row",
    };
  }
  if (onPeriods && periodCount === 0) {
    return {
      kicker: "Step 3 of 5",
      title: "Add this month’s period",
      copy: "Type the month you are working on, for example Aug 2026, then click Add period.",
      items: ["Check the period box.", "Click Add period."],
      highlight: "#period-form",
    };
  }
  if (onPeriods && periodCount > 0) {
    return {
      kicker: "Step 4 of 5",
      title: "Open the period",
      copy: "Click the period row. That is the dump tray for this month.",
      items: ["Click the period in the list."],
      highlight: "#period-list .period-row",
    };
  }
  if (onDump && !hasFiles) {
    return {
      kicker: "Step 4 of 5",
      title: "Dump this month’s files",
      copy: "Click Add folder and pick the mixed folder, or drop that folder onto the dashed box. Nested files are included. Bank PDFs, invoices, GSTR JSON and Tally/Zoho can go in together.",
      items: ["Click Add folder, or drop a folder on the dashed box."],
      highlight: "#add-folder",
    };
  }
  if (onDump && hasFiles && !hasPack) {
    return {
      kicker: "Step 4 of 5",
      title: "Wait for the pack",
      copy: "The app is sorting files on this PC. Unknown or unreadable files stay in Needs review until they convert.",
      items: ["Wait until an Excel pack appears below.", "If a file is Unknown, set its type."],
      highlight: "#drop-zone",
    };
  }
  if (onDump && hasPack) {
    return {
      kicker: "Step 5 of 5",
      title: "Open the Excel pack",
      copy: "Click Open in Excel. Click an amount in Spot-check if you want to see it on the original page.",
      items: ["Click Open in Excel.", "Optional: click an amount to see the source crop."],
      highlight: "#open-pack",
    };
  }
  return null;
}

function renderGuideList(items) {
  const list = document.getElementById("guide-list");
  if (!list) return;
  list.innerHTML = "";
  for (const item of items || []) {
    const li = document.createElement("li");
    li.textContent = item;
    list.append(li);
  }
}

function deskIsVisible() {
  return deskEl && !deskEl.classList.contains("hidden");
}

function syncGuide() {
  const card = document.getElementById("guide");
  if (!card) return;
  const onSetup = guideOnSetup();
  if (onSetup || guideDismissed || !deskIsVisible()) {
    card.classList.add("hidden");
    clearGuideHighlight();
    if (onSetup) {
      const folderChosen = Boolean(document.getElementById("output-path") && document.getElementById("output-path").value);
      highlightGuide(folderChosen ? "#save-firm" : "#pick-output");
    }
    return;
  }
  const step = currentGuideCard();
  if (!step) {
    card.classList.add("hidden");
    clearGuideHighlight();
    return;
  }
  document.getElementById("guide-kicker").textContent = step.kicker;
  document.getElementById("guide-title").textContent = step.title;
  document.getElementById("guide-copy").textContent = step.copy;
  renderGuideList(step.items);
  card.classList.remove("hidden");
  highlightGuide(step.highlight);
}

async function dismissGuide() {
  guideDismissed = true;
  const api = desktopApi();
  if (api && api.set_guide_dismissed) {
    await api.set_guide_dismissed(true);
  }
  syncGuide();
}

async function reopenGuide() {
  guideDismissed = false;
  const api = desktopApi();
  if (api && api.set_guide_dismissed) {
    await api.set_guide_dismissed(false);
  }
  syncGuide();
}

async function deleteClientRow(client) {
  if (!window.confirm(`Delete ${client.name} and every file dumped for them on this PC?`)) {
    return;
  }
  showError(deskErrorEl, "");
  const result = await window.pywebview.api.delete_client_desk(client.id);
  if (!result.ok) {
    showError(deskErrorEl, result.error);
    return;
  }
  if (currentClient && currentClient.id === client.id) {
    currentClient = null;
    currentPeriod = null;
    showPane("clients");
    recordNav({ pane: "clients" });
  }
  renderClients(result.clients || []);
  syncGuide();
}

async function boot() {
  initPasswordToggles();
  initActionSearchBar();
  initFilePreview();
  const state = await window.pywebview.api.get_state();
  lastAppState = state;
  guideDismissed = Boolean(state.guide_dismissed);
  authState = state.auth || null;
  applyDevMode(state.license);
  await refreshAuthState();
  const isSignedIn = devMode || Boolean(authState && authState.signed_in);
  if (!isSignedIn) {
    // Strict in-app auth: gate is shown by refreshAuthState.
    // Do not show folder/firm setup or desk until signed in.
    return;
  }
  if (state.firm && state.output_path) {
    showDesk(state);
  } else {
    showSetup(state);
  }
}

saveFirmBtn.addEventListener("click", async () => {
  showError(setupErrorEl, "");
  const out = document.getElementById("output-path").value;
  if (!out) {
    showError(setupErrorEl, "Choose a folder for the cleaned Excels first.");
    return;
  }
  const savedOut = await window.pywebview.api.set_output_folder(out);
  if (!savedOut.ok) {
    showError(setupErrorEl, savedOut.error);
    return;
  }
  const result = await window.pywebview.api.save_firm(firmNameEl.value);
  if (!result.ok) {
    showError(setupErrorEl, result.error);
    return;
  }
  showDesk({
    firm: result.firm,
    clients: result.clients,
    output_path: savedOut.output_path,
    path_warnings: savedOut.path_warnings || [],
    license: result.license,
  });
});

document.getElementById("pick-output").addEventListener("click", chooseOutputFolder);
document.getElementById("change-output").addEventListener("click", async () => {
  const path = await chooseOutputFolder();
  if (path) setOutputLabel(path);
});

firmNameEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") saveFirmBtn.click();
});

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError(deskErrorEl, "");
  const result = await window.pywebview.api.create_client(
    clientNameEl.value,
    clientGstinEl.value
  );
  if (!result.ok) {
    showError(deskErrorEl, result.error);
    return;
  }
  renderClients(result.clients);
  addForm.reset();
  clientNameEl.focus();
  syncGuide();
});

periodForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentClient) return;
  showError(periodErrorEl, "");
  const result = await window.pywebview.api.create_period(
    currentClient.id,
    periodLabelEl.value
  );
  if (!result.ok) {
    showError(periodErrorEl, result.error);
    return;
  }
  renderPeriods(result.periods);
  lastPeriodCount = (result.periods || []).length;
  syncGuide();
});

document.getElementById("back-to-clients").addEventListener("click", async () => {
  const state = await window.pywebview.api.get_state();
  currentPeriod = null;
  showDesk(state);
});

document.getElementById("back-to-periods").addEventListener("click", () => {
  if (currentClient) openClient(currentClient.id);
});

const navBackBtn = document.getElementById("nav-back");
const navForwardBtn = document.getElementById("nav-forward");
const navRefreshBtn = document.getElementById("nav-refresh");
if (navBackBtn) navBackBtn.addEventListener("click", goNavBack);
if (navForwardBtn) navForwardBtn.addEventListener("click", goNavForward);
if (navRefreshBtn) navRefreshBtn.addEventListener("click", refreshCurrentView);

document.getElementById("open-pack").addEventListener("click", async () => {
  if (!currentPeriod) return;
  const key = packOpenKey || (packHasBank ? "bank" : "");
  const result = await window.pywebview.api.open_bank_pack(currentPeriod.id, key);
  if (!result.ok) showError(dumpErrorEl, result.error);
});

document.getElementById("open-folder").addEventListener("click", async () => {
  if (!currentPeriod) return;
  const result = await window.pywebview.api.open_pack_folder(currentPeriod.id);
  if (!result.ok) showError(dumpErrorEl, result.error);
});

addFilesBtn.addEventListener("click", async () => {
  const picked = await window.pywebview.api.pick_files();
  if (!picked.ok) {
    showError(dumpErrorEl, picked.error);
    return;
  }
  if (!picked.paths.length) return;
  await startDump(picked.paths);
});

addFolderBtn.addEventListener("click", async () => {
  const picked = await window.pywebview.api.pick_folder();
  if (!picked.ok) {
    showError(dumpErrorEl, picked.error);
    return;
  }
  if (!picked.paths.length) return;
  await startDump(picked.paths);
});

document.addEventListener("dragover", (event) => {
  event.preventDefault();
});
document.addEventListener("drop", (event) => {
  event.preventDefault();
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
  dropZone.classList.add("over");
});
dropZone.addEventListener("dragleave", (event) => {
  if (!dropZone.contains(event.relatedTarget)) dropZone.classList.remove("over");
});
async function handleDumpDrop(event) {
  event.preventDefault();
  dropZone.classList.remove("over");
  const paths = await pathsFromDropEvent(event);
  if (!paths.length) {
    showError(dumpErrorEl, "Drop files or a folder from File Explorer.");
    return;
  }
  await startDump(paths);
}

dropZone.addEventListener("drop", (event) => {
  event.stopPropagation();
  handleDumpDrop(event);
});
paneDump.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
});
paneDump.addEventListener("drop", handleDumpDrop);

const wipeModal = document.getElementById("wipe-modal");
const wipeErrorEl = document.getElementById("wipe-error");

if (reconFiltersEl) {
  reconFiltersEl.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-recon-filter]");
    if (!btn) return;
    reconFilter = btn.getAttribute("data-recon-filter") || "all";
    renderRecon(lastPack);
  });
}

document.getElementById("guide-skip").addEventListener("click", dismissGuide);
document.getElementById("guide-open").addEventListener("click", reopenGuide);

const authForm = document.getElementById("auth-form");
const authEmailEl = document.getElementById("auth-email");
const authPasswordEl = document.getElementById("auth-password");
const authSubmitBtn = document.getElementById("auth-submit");
const authModeToggle = document.getElementById("auth-mode-toggle");
const authForgotBtn = document.getElementById("auth-forgot");
let authBusy = false;
let authMode = "login"; // "login" | "signup"

function renderAuthMode() {
  if (!authSubmitBtn) return;
  if (authMode === "signup") {
    authSubmitBtn.textContent = "Create account";
    if (authPasswordEl) authPasswordEl.setAttribute("autocomplete", "new-password");
    if (authModeToggle) authModeToggle.textContent = "Already have an account? Log in";
    const title = document.getElementById("auth-title");
    const lede = document.getElementById("auth-lede");
    if (title) title.textContent = "Create your account";
    if (lede) lede.textContent = "Sign up with email and password. Processing stays on this PC.";
  } else {
    authSubmitBtn.textContent = "Log in";
    if (authPasswordEl) authPasswordEl.setAttribute("autocomplete", "current-password");
    if (authModeToggle) authModeToggle.textContent = "Create account instead";
    const title = document.getElementById("auth-title");
    const lede = document.getElementById("auth-lede");
    if (title) title.textContent = "Sign in to CA Unpacker";
    if (lede) lede.textContent = "Create an account or sign in to continue. All processing stays on this PC.";
  }
}

function setAuthBusy(busy, label) {
  authBusy = Boolean(busy);
  if (!authSubmitBtn) return;
  authSubmitBtn.disabled = authBusy;
  if (authModeToggle) authModeToggle.disabled = authBusy;
  if (authForgotBtn) authForgotBtn.disabled = authBusy;
  if (authBusy) authSubmitBtn.textContent = label;
  else renderAuthMode();
}

function clearAuthPassword() {
  if (authPasswordEl) authPasswordEl.value = "";
}

if (authForm) {
  renderAuthMode();
  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (authBusy) return;
    showError(authErrorEl, "");
    showError(authNoticeEl, "");
    const api = desktopApi();
    const email = authEmailEl ? authEmailEl.value : "";
    const password = authPasswordEl ? authPasswordEl.value : "";
    if (!api) {
      showError(authErrorEl, "Update the app to sign in here.");
      return;
    }
    const isSignup = authMode === "signup";
    const fn = isSignup ? api.signup_with_password : api.login_with_password;
    if (!fn) {
      showError(authErrorEl, "Update the app to continue.");
      return;
    }
    setAuthBusy(true, isSignup ? "Creating account…" : "Signing in…");
    let result;
    try {
      result = await fn(email, password);
    } catch {
      result = { ok: false, error: "Could not reach the service. Try again." };
    }
    clearAuthPassword();
    setAuthBusy(false);
    if (!result || !result.ok) {
      showError(authErrorEl, (result && result.error) || "Failed.");
      return;
    }
    if (result.confirmation_required) {
      showError(authNoticeEl, "Account created. Check your email to confirm, then log in.");
      // switch to login mode after signup that needs confirmation
      authMode = "login";
      renderAuthMode();
      return;
    }
    await ensurePostAuth();
  });
}

if (authModeToggle) {
  authModeToggle.addEventListener("click", () => {
    if (authBusy) return;
    showError(authErrorEl, "");
    showError(authNoticeEl, "");
    authMode = (authMode === "login") ? "signup" : "login";
    renderAuthMode();
    if (authPasswordEl) authPasswordEl.focus();
  });
}

if (authForgotBtn) {
  authForgotBtn.addEventListener("click", async () => {
    if (authBusy) return;
    showError(authErrorEl, "");
    showError(authNoticeEl, "");
    const api = desktopApi();
    if (!api || !api.request_password_reset) {
      showError(authErrorEl, "Update the app to reset your password here.");
      return;
    }
    const email = authEmailEl ? authEmailEl.value : "";
    try {
      await api.request_password_reset(email);
    } catch {
      // Never reveal whether the address exists.
    }
    showError(authNoticeEl, "If that email has an account, a reset link is on its way.");
  });
}
if (profileButtonEl && profilePanelEl) {
  profileButtonEl.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = profilePanelEl.hidden;
    profilePanelEl.hidden = !open;
    profileButtonEl.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("click", (event) => {
    if (profilePanelEl.hidden) return;
    if (!quotaBannerEl.contains(event.target)) closeProfilePanel();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !profilePanelEl.hidden) {
      closeProfilePanel();
      profileButtonEl.focus();
    }
  });
}

const authLogoutBtn = document.getElementById("auth-logout");
if (authLogoutBtn) {
  authLogoutBtn.addEventListener("click", async () => {
    const api = desktopApi();
    if (!api || !api.logout) return;
    closeProfilePanel();
    await api.logout();
    await ensurePostAuth();
  });
}

document.getElementById("license-open").addEventListener("click", () => {
  showError(document.getElementById("license-error"), "");
  document.getElementById("license-modal").classList.remove("hidden");
});
document.getElementById("license-cancel").addEventListener("click", () => {
  document.getElementById("license-modal").classList.add("hidden");
});
document.getElementById("license-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = document.getElementById("license-error");
  showError(errorEl, "");
  const result = await window.pywebview.api.activate_license(
    document.getElementById("license-key").value
  );
  if (!result.ok) {
    showError(errorEl, result.error);
    return;
  }
  renderLicense(result.license);
  document.getElementById("license-modal").classList.add("hidden");
});

document.getElementById("wipe-open").addEventListener("click", () => {
  showError(wipeErrorEl, "");
  wipeModal.classList.remove("hidden");
});

document.getElementById("wipe-cancel").addEventListener("click", () => {
  wipeModal.classList.add("hidden");
});

document.getElementById("wipe-confirm").addEventListener("click", async () => {
  showError(wipeErrorEl, "");
  const result = await window.pywebview.api.wipe_and_restart();
  if (!result.ok) {
    showError(wipeErrorEl, result.error);
  }
});

if (cropModal) {
  cropModal.addEventListener("click", (event) => {
    if (event.target === cropModal) closeCropModal();
  });
}
const cropCloseBtn = document.getElementById("crop-close");
if (cropCloseBtn) cropCloseBtn.addEventListener("click", closeCropModal);

if (unlockModal) {
  unlockModal.addEventListener("click", (event) => {
    if (event.target === unlockModal) closeUnlockModal();
  });
}
const unlockForm = document.getElementById("unlock-form");
if (unlockForm) unlockForm.addEventListener("submit", submitUnlock);
const unlockCancelBtn = document.getElementById("unlock-cancel");
if (unlockCancelBtn) unlockCancelBtn.addEventListener("click", closeUnlockModal);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (cropModal && !cropModal.classList.contains("hidden")) {
      closeCropModal();
      return;
    }
    if (unlockModal && !unlockModal.classList.contains("hidden")) {
      closeUnlockModal();
    }
    return;
  }
  if (isTypingTarget(event.target)) return;
  if (!deskIsVisible()) return;
  if (event.altKey && event.key === "ArrowLeft") {
    event.preventDefault();
    goNavBack();
    return;
  }
  if (event.altKey && event.key === "ArrowRight") {
    event.preventDefault();
    goNavForward();
    return;
  }
  if (event.key === "F5" || ((event.ctrlKey || event.metaKey) && (event.key === "r" || event.key === "R"))) {
    event.preventDefault();
    refreshCurrentView();
  }
});

/* ==========================================================================
   21st.dev Component Logics:
   - Origin UI Password Toggle (@originui/input)
   - Kokonut UI Action Search Bar (@kokonutd/action-search-bar)
   ========================================================================== */
function initPasswordToggles() {
  const authToggleBtn = document.getElementById("auth-show-password");
  const authPw = document.getElementById("auth-password");
  if (authToggleBtn && authPw) {
    authToggleBtn.addEventListener("click", () => {
      const isPw = authPw.type === "password";
      authPw.type = isPw ? "text" : "password";
      authToggleBtn.title = isPw ? "Hide password" : "Show password";
    });
  }
}

let actionSearchBarInitialized = false;
function initActionSearchBar() {
  if (actionSearchBarInitialized) return;
  const input = document.getElementById("action-search-input");
  const dropdown = document.getElementById("action-search-dropdown");
  const list = document.getElementById("action-dropdown-list");
  const bar = document.getElementById("action-search-bar");
  if (!input || !dropdown || !list || !bar) return;
  actionSearchBarInitialized = true;

  let activeIndex = -1;
  let currentItems = [];

  const defaultActions = [
    {
      id: "act-new-client",
      title: "Register New Client",
      meta: "Entity Details",
      icon: "+",
      short: "N",
      run: () => {
        showScreen("desk");
        const clientInput = document.getElementById("client-name");
        if (clientInput) {
          if (paneClients && paneClients.classList.contains("hidden")) {
            document.getElementById("back-to-clients")?.click();
          }
          setTimeout(() => clientInput.focus(), 60);
        }
      }
    },
    {
      id: "act-guide",
      title: "Open Terminal Runbook",
      meta: "Bank Guides & Workflows",
      icon: "📖",
      short: "R",
      run: () => {
        document.getElementById("guide-open")?.click();
      }
    },
    {
      id: "act-license",
      title: "Manage License Key",
      meta: "Air-gap Hardware Verification",
      icon: "🔑",
      short: "L",
      run: () => {
        document.getElementById("license-open")?.click();
      }
    },
    {
      id: "act-refresh",
      title: "Force Refresh Desk",
      meta: "Synchronize Repository State",
      icon: "↻",
      short: "F5",
      run: () => {
        refreshCurrentView();
      }
    },
    {
      id: "act-output",
      title: "Change Workpapers Folder",
      meta: "Excel Output Directory",
      icon: "📁",
      short: "O",
      run: () => {
        document.getElementById("change-output")?.click();
      }
    }
  ];

  function renderDropdown(items) {
    currentItems = items;
    activeIndex = -1;
    list.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "action-item";
      empty.style.color = "var(--term-text-muted)";
      empty.style.justifyContent = "center";
      empty.textContent = "No matching actions or clients found";
      list.appendChild(empty);
      return;
    }

    items.forEach((item, index) => {
      const el = document.createElement("div");
      el.className = "action-item";
      el.id = `action-item-${item.id}`;

      const left = document.createElement("div");
      left.className = "action-item-left";

      const icon = document.createElement("span");
      icon.className = "action-item-icon font-mono";
      icon.textContent = item.icon || "•";

      const title = document.createElement("span");
      title.className = "action-item-title";
      title.textContent = item.title;

      left.append(icon, title);

      if (item.meta) {
        const meta = document.createElement("span");
        meta.className = "action-item-meta font-mono";
        meta.textContent = item.meta;
        left.append(meta);
      }

      const right = document.createElement("span");
      right.className = "action-item-shortcut font-mono";
      right.textContent = item.short || "";

      el.append(left, right);

      el.addEventListener("click", () => {
        closeDropdown();
        item.run?.();
      });

      list.appendChild(el);
    });
  }

  function openDropdown() {
    bar.classList.add("active");
    dropdown.classList.remove("hidden");
    filterItems(input.value);
  }

  function closeDropdown() {
    bar.classList.remove("active");
    dropdown.classList.add("hidden");
    activeIndex = -1;
  }

  function filterItems(query) {
    const q = (query || "").trim().toLowerCase();
    const clients = (lastAppState && lastAppState.clients) || [];

    const clientItems = clients.map((c) => ({
      id: `client-${c.id}`,
      title: c.name,
      meta: c.gstin || "Client Entity",
      icon: "🏢",
      short: "↵",
      run: () => openClient(c.id)
    }));

    if (!q) {
      renderDropdown([...defaultActions, ...clientItems.slice(0, 6)]);
      return;
    }

    const matchedClients = clientItems.filter(
      (c) => c.title.toLowerCase().includes(q) || c.meta.toLowerCase().includes(q)
    );

    const matchedActions = defaultActions.filter(
      (a) => a.title.toLowerCase().includes(q) || (a.meta && a.meta.toLowerCase().includes(q))
    );

    renderDropdown([...matchedActions, ...matchedClients]);
  }

  input.addEventListener("focus", openDropdown);
  input.addEventListener("input", (e) => filterItems(e.target.value));

  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!currentItems.length) return;
      activeIndex = (activeIndex + 1) % currentItems.length;
      updateActive();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!currentItems.length) return;
      activeIndex = (activeIndex - 1 + currentItems.length) % currentItems.length;
      updateActive();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (activeIndex >= 0 && currentItems[activeIndex]) {
        closeDropdown();
        currentItems[activeIndex].run?.();
      }
    } else if (e.key === "Escape") {
      closeDropdown();
      input.blur();
    }
  });

  function updateActive() {
    const children = list.querySelectorAll(".action-item");
    children.forEach((c, idx) => {
      c.classList.toggle("focused", idx === activeIndex);
      if (idx === activeIndex) c.scrollIntoView({ block: "nearest" });
    });
  }

  document.addEventListener("click", (e) => {
    if (!document.getElementById("action-search-container")?.contains(e.target)) {
      closeDropdown();
    }
  });

  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      input.focus();
      input.select();
    } else if (e.key === "/" && !isTypingTarget(document.activeElement)) {
      e.preventDefault();
      input.focus();
    }
  });
}

window.addEventListener("pywebviewready", boot);

// Browser preview fallback when opened directly in Google Chrome / Web Browser
if (!window.pywebview) {
  let mockState = {
    firm: { name: "Mehta & Associates, Chartered Accountants" },
    output_path: "C:\\CA_Workpapers",
    clients: [
      { id: 1, name: "Rajesh Trading Corporation", gstin: "27AABCR1234F1Z5" },
      { id: 2, name: "Shivani Healthcare LLP", gstin: "24AAECS9876E1Z2" },
      { id: 3, name: "Apex Logistics India Pvt Ltd", gstin: "27AAGCA5678B1ZP" },
      { id: 4, name: "Kothari Textiles & Yarn Mill", gstin: "24AAEFK4321A1Z9" }
    ],
    auth: { signed_in: true, email: "partner@mehta-associates.in" },
    license: { plan: "Pro", plan_label: "PRO TIER (AIR-GAP)", tier: "pro", active: true, usage: { total_files: 14, limit: 500 } },
    guide_dismissed: true,
    path_warnings: []
  };
  let mockPeriods = [
    { id: 101, client_id: 1, label: "Aug 2026", status: "ready" },
    { id: 102, client_id: 1, label: "Jul 2026", status: "ready" },
    { id: 103, client_id: 2, label: "Q1 FY 2026-27", status: "ready" }
  ];
  let mockFiles = [
    { id: 1, period_id: 101, name: "HDFC_Current_Account_Aug2026.pdf", kind: "bank", status: "ready" },
    { id: 2, period_id: 101, name: "GSTR2B_27AABCR1234F1Z5_082026.json", kind: "gstr2b", status: "ready" },
    { id: 3, period_id: 101, name: "Tally_Purchase_Register_Aug.xlsx", kind: "books", status: "ready" }
  ];

  window.pywebview = {
    api: {
      get_state: async () => JSON.parse(JSON.stringify(mockState)),
      get_auth_state: async () => ({ ok: true, signed_in: mockState.auth.signed_in, email: mockState.auth.email, plan: mockState.license.plan }),
      login_with_password: async (email, pw) => {
        mockState.auth.signed_in = true;
        mockState.auth.email = email || "partner@mehta-associates.in";
        return { ok: true, session: { email: mockState.auth.email } };
      },
      signup_with_password: async (email, pw) => {
        mockState.auth.signed_in = true;
        mockState.auth.email = email || "partner@mehta-associates.in";
        return { ok: true, session: { email: mockState.auth.email } };
      },
      logout: async () => {
        mockState.auth.signed_in = false;
        return { ok: true };
      },
      request_password_reset: async (email) => ({ ok: true }),
      save_firm: async (name) => {
        mockState.firm = { name: name || "Mehta & Associates, Chartered Accountants" };
        return { ok: true, firm: mockState.firm, clients: mockState.clients, license: mockState.license };
      },
      set_output_folder: async (p) => {
        mockState.output_path = p || "C:\\CA_Workpapers";
        return { ok: true, output_path: mockState.output_path, path_warnings: [] };
      },
      pick_output_folder: async () => ({ ok: true, output_path: "C:\\CA_Workpapers" }),
      pick_folder: async () => ({ ok: true, paths: ["C:\\CA_Workpapers\\Client_Dumps\\Aug2026"] }),
      pick_files: async () => ({ ok: true, paths: ["HDFC_Statement_Aug2026.pdf", "GSTR2B_Aug2026.json"] }),
      create_client: async (name, gstin) => {
        const c = { id: Date.now(), name, gstin: gstin || "" };
        mockState.clients.push(c);
        return { ok: true, clients: mockState.clients };
      },
      get_client_desk: async (cid) => {
        const client = mockState.clients.find(c => c.id === cid) || mockState.clients[0];
        const periods = mockPeriods.filter(p => p.client_id === client.id);
        return { ok: true, client, periods };
      },
      delete_client_desk: async (cid) => {
        mockState.clients = mockState.clients.filter(c => c.id !== cid);
        return { ok: true, clients: mockState.clients };
      },
      create_period: async (cid, label) => {
        const p = { id: Date.now(), client_id: cid, label: label || "Aug 2026" };
        mockPeriods.push(p);
        return { ok: true, periods: mockPeriods.filter(x => x.client_id === cid) };
      },
      get_period_desk: async (pid) => {
        const p = mockPeriods.find(x => x.id === pid) || mockPeriods[0];
        return { ok: true, period: p, files: mockFiles, pack: null };
      },
      start_dump: async (pid, paths) => ({ ok: true, job_id: "demo-job-1" }),
      get_job: async (jid) => ({ ok: true, job: { id: jid, status: "completed", progress: 100 } }),
      open_bank_pack: async (pid, key) => ({ ok: true }),
      open_pack_folder: async (pid) => ({ ok: true }),
      activate_license: async (key) => ({ ok: true, license: { plan: "Pro", tier: "pro", active: true } }),
      wipe_and_restart: async () => { location.reload(); return { ok: true }; },
      set_guide_dismissed: async (val) => { mockState.guide_dismissed = val; return { ok: true }; },
      get_file_preview: async (file_id, file_path, page, sheet_name) => {
        return {
          ok: true,
          type: "spreadsheet",
          filename: "HDFC_Current_Account_Aug2026.xlsx",
          size_formatted: "142.5 KB",
          sheets: ["Transactions", "Summary"],
          active_sheet: sheet_name || "Transactions",
          columns: ["Date", "Description", "Debit (₹)", "Credit (₹)", "Balance (₹)"],
          rows: [
            ["01-Aug-2026", "Opening Balance", "", "", "1,45,230.00"],
            ["02-Aug-2026", "NEFT/MUM/INFOSYS/SALARY", "", "75,000.00", "2,20,230.00"],
            ["04-Aug-2026", "UPI/OFFICE/SUPPLIES/AMZN", "1,240.00", "", "2,18,990.00"],
            ["08-Aug-2026", "CHQ 001248 MUNICIPAL TAX", "12,500.00", "", "2,06,490.00"],
            ["15-Aug-2026", "RTGS/VENDOR PAYMENT/TATA", "55,000.00", "", "1,51,490.00"]
          ],
          total_rows: 5
        };
      },
      list_folder_files: async (folder_path) => ({
        ok: true,
        folder_path: folder_path || "C:\\CA_Workpapers",
        files: mockFiles
      }),
      get_period_output_path: async (pid) => ({
        ok: true,
        path: "C:\\CA_Workpapers\\Rajesh Trading\\Aug 2026"
      }),
      open_file_in_os: async (path) => ({ ok: true, path })
    }
  };

  window.addEventListener("DOMContentLoaded", () => {
    setTimeout(async () => {
      await boot();
    }, 40);
  });
}


