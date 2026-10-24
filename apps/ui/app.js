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
const paneDashboard = document.getElementById("pane-dashboard");
const paneRecon = document.getElementById("pane-recon");
const paneReports = document.getElementById("pane-reports");
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
const dashboardLoadingEl = document.getElementById("dashboard-loading");
const dashboardContentEl = document.getElementById("dashboard-content");
const dashboardEmptyEl = document.getElementById("dashboard-empty");
const dashboardErrorEl = document.getElementById("dashboard-error");
const reconPageErrorEl = document.getElementById("recon-page-error");
const reconLoadingEl = document.getElementById("recon-loading");
const reconWorkspaceEl = document.getElementById("recon-workspace");
const reconEmptyEl = document.getElementById("recon-empty");
const reconWorkflowsEl = document.getElementById("recon-workflows");
const reconMissingEl = document.getElementById("recon-missing");
const reconCalculatingEl = document.getElementById("recon-calculating");
const reconResultsEl = document.getElementById("recon-results");
const reconPeriodEl = document.getElementById("recon-period");
const reconResultTitleEl = document.getElementById("recon-result-title");
const reconResultSubEl = document.getElementById("recon-result-sub");
const reconResultStampEl = document.getElementById("recon-result-stamp");
const reconRulesEl = document.getElementById("recon-rules");
const reconSummaryEl = document.getElementById("recon-summary");
const reconTotalsEl = document.getElementById("recon-totals");
const reconTableHeadEl = document.getElementById("recon-table-head");
const reconTableBodyEl = document.getElementById("recon-table-body");
const reconTableEmptyEl = document.getElementById("recon-table-empty");
const reconPageFiltersEl = document.getElementById("recon-page-filters");
const reconSearchEl = document.getElementById("recon-search");
const reconDetailModal = document.getElementById("recon-detail-modal");
const reconDetailTitleEl = document.getElementById("recon-detail-title");
const reconDetailStatusEl = document.getElementById("recon-detail-status");
const reconDetailExplanationEl = document.getElementById("recon-detail-explanation");
const reconDetailDiffsEl = document.getElementById("recon-detail-diffs");
const reconDetailBodyEl = document.getElementById("recon-detail-body");
const reconDetailErrorEl = document.getElementById("recon-detail-error");
const reportsLoadingEl = document.getElementById("reports-loading");
const reportsErrorEl = document.getElementById("reports-error");
const reportsListEl = document.getElementById("reports-list");
const reportsEmptyEl = document.getElementById("reports-empty");
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
const removeFileModal = document.getElementById("remove-file-modal");
const removeFileCopyEl = document.getElementById("remove-file-copy");
const removeFileErrorEl = document.getElementById("remove-file-error");
const removeFileConfirmBtn = document.getElementById("remove-file-confirm");
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

let currentClient = null;
let currentPeriod = null;
let kindOptions = [];
let currencyOptions = [];
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
let removeFileTarget = null;
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
let dashboardData = null;
let reconWorkspaceData = null;
let selectedReconPeriodId = null;
let activeReconWorkflowId = "";
let lastReconPageResult = null;
let reconPageFilter = "all";
let reconPageSearch = "";
let reconPageBusy = false;
let reportsData = null;

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
  if (paneDashboard) paneDashboard.classList.toggle("hidden", name !== "dashboard");
  if (paneRecon) paneRecon.classList.toggle("hidden", name !== "recon");
  if (paneReports) paneReports.classList.toggle("hidden", name !== "reports");
  if (name === "clients") navLabelEl.textContent = "Clients";
  if (name === "periods") navLabelEl.textContent = "Periods";
  if (name === "dump") navLabelEl.textContent = "Document Workspace";
  if (name === "dashboard") navLabelEl.textContent = "Dashboard";
  if (name === "recon") navLabelEl.textContent = "Reconciliation";
  if (name === "reports") navLabelEl.textContent = "Reports";
  setRailPage(
    name === "dashboard" || name === "recon" || name === "reports"
      ? name
      : "documents"
  );
  updateDeskContext(name);
}

function setRailPage(page) {
  const items = {
    documents: "nav-documents",
    dashboard: "nav-dashboard",
    recon: "nav-recon",
    reports: "nav-reports",
  };
  for (const [name, id] of Object.entries(items)) {
    const button = document.getElementById(id);
    if (!button) continue;
    const active = name === page;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
}

function updateDeskContext(pane) {
  const el = document.getElementById("desk-context");
  if (!el) return;
  const current = pane || currentDeskPane();
  if (current === "dashboard") {
    el.textContent = "Practice / Dashboard";
    return;
  }
  if (current === "recon") {
    el.textContent = "Practice / Reconciliation";
    return;
  }
  if (current === "reports") {
    el.textContent = "Practice / Reports";
    return;
  }
  const parts = ["Clients"];
  if (current === "periods" || current === "dump") {
    const clientName =
      (currentClient && currentClient.name) ||
      (periodClientNameEl && periodClientNameEl.textContent) ||
      (dumpEyebrowEl && dumpEyebrowEl.textContent);
    if (clientName && clientName !== "Document Workspace") parts.push(clientName);
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
  if (paneDashboard && !paneDashboard.classList.contains("hidden")) return "dashboard";
  if (paneRecon && !paneRecon.classList.contains("hidden")) return "recon";
  if (paneReports && !paneReports.classList.contains("hidden")) return "reports";
  if (paneDump && !paneDump.classList.contains("hidden")) return "dump";
  if (panePeriods && !panePeriods.classList.contains("hidden")) return "periods";
  return "clients";
}

function navEntryKey(entry) {
  if (!entry) return "";
  return `${entry.pane}:${entry.clientId || ""}:${entry.periodId || ""}:${entry.reconPeriodId || ""}`;
}

function currentNavEntry() {
  const pane = currentDeskPane();
  const entry = { pane };
  if (pane === "periods" && currentClient) entry.clientId = currentClient.id;
  if (pane === "dump") {
    if (currentClient) entry.clientId = currentClient.id;
    if (currentPeriod) entry.periodId = currentPeriod.id;
  }
  if (pane === "recon" && selectedReconPeriodId) {
    entry.reconPeriodId = selectedReconPeriodId;
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
  if (entry.pane === "dashboard") {
    await showDashboard({ record: false });
    return;
  }
  if (entry.pane === "recon") {
    await showReconciliation({
      record: false,
      periodId: entry.reconPeriodId || selectedReconPeriodId,
    });
    return;
  }
  if (entry.pane === "reports") {
    await showReports({ record: false });
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
    if (pane === "dashboard") {
      await loadDashboard();
    } else if (pane === "recon") {
      await loadReconciliationWorkspace({ keepSelection: true });
    } else if (pane === "reports") {
      await loadReports();
    } else if (pane === "dump" && currentPeriod) {
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
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = client.name;
    const gstin = document.createElement("span");
    gstin.className = "gstin";
    gstin.textContent = client.gstin || "—";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "row-delete";
    del.textContent = "Delete";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteClientRow(client);
    });
    row.append(name, gstin, del);
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
    hint.textContent = "Open Document Workspace";
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

function currencySelect(file) {
  const api = desktopApi();
  if (!api || !api.set_file_currency) {
    const pill = document.createElement("span");
    pill.className = "pill mute";
    pill.textContent = file.currency_label || "Currency unknown";
    return pill;
  }
  const select = document.createElement("select");
  select.className = "kind-pick currency-pick";
  select.title =
    "Currency is detected from the statement. Choosing a code only labels amounts; it never converts them.";
  const auto = document.createElement("option");
  auto.value = "";
  const detected = file.currency_detected_code
    ? `${file.currency_detected_code}${file.currency_detected_status && file.currency_detected_status !== "confirmed" ? ` (${file.currency_detected_status})` : ""}`
    : "not detected";
  auto.textContent = `Detected: ${detected}`;
  select.append(auto);
  for (const option of currencyOptions) {
    const item = document.createElement("option");
    item.value = option.code;
    item.textContent = option.label;
    if (option.code === file.currency_code) item.selected = true;
    select.append(item);
  }
  if (file.currency_override) select.value = file.currency_override;
  select.addEventListener("change", async () => {
    const result = await api.set_file_currency(file.id, select.value);
    if (!result.ok) {
      showError(dumpErrorEl, result.error);
      select.value = file.currency_override || "";
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

function appendFileRow(container, file, className) {
  const row = document.createElement("div");
  row.className = className;
  const details = document.createElement("div");
  details.className = "file-details";
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = file.original_name;
  name.title = file.parse_reason_message || file.classify_reason || "";
  const outcome = document.createElement("span");
  const outcomeName = window.CAStatusSummary.outcomeLabel(file.parse_outcome);
  outcome.className = `pill outcome-${file.parse_outcome || "unclassified"}`;
  outcome.textContent = outcomeName;
  outcome.setAttribute("aria-label", `Outcome: ${outcomeName}`);
  details.append(name, outcome);
  if (file.parse_outcome === "processed" && Number.isFinite(Number(file.parse_row_count))) {
    const rows = document.createElement("span");
    const count = Number(file.parse_row_count);
    rows.className = "file-meta";
    rows.textContent = `${count} ${count === 1 ? "row" : "rows"}`;
    details.append(rows);
  }
  if (file.kind === "bank" && file.currency_label) {
    const currency = document.createElement("span");
    currency.className = "file-meta";
    currency.textContent = `Currency: ${file.currency_label}`;
    currency.title = file.currency_source
      ? `Source: ${file.currency_source.replaceAll("_", " ")}`
      : "";
    details.append(currency);
  }
  const reasonLine = document.createElement("p");
  reasonLine.className = "file-reason";
  reasonLine.textContent = file.parse_reason_message || file.classify_reason || "";
  if (reasonLine.textContent) details.append(reasonLine);
  const actions = document.createElement("div");
  actions.className = "file-actions";
  if (fileNeedsPassword(file)) {
    const unlock = document.createElement("button");
    unlock.type = "button";
    unlock.className = "text-btn unlock-btn";
    unlock.textContent = "Unlock";
    unlock.addEventListener("click", (event) => {
      event.preventDefault();
      openUnlockModal(file);
    });
    actions.append(unlock);
  }
  actions.append(kindSelect(file, false));
  if (file.kind === "bank") actions.append(currencySelect(file));
  actions.append(removeFileButton(file));
  row.append(details, actions);
  container.append(row);
}

function removeFileButton(file) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "file-remove";
  button.title = `Remove ${file.original_name} from this period`;
  button.setAttribute(
    "aria-label",
    `Remove ${file.original_name} from this period`
  );
  button.innerHTML =
    '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">' +
    '<path d="M6.5 1.5h3a1 1 0 0 1 1 1V3H11a.75.75 0 0 1 0 1.5H5A.75.75 0 0 1 5 3h.5v-.5a1 1 0 0 1 1-1Z" fill="currentColor"/>' +
    '<path d="M4 5.5h8l-.6 8a1.5 1.5 0 0 1-1.5 1.4H6.1A1.5 1.5 0 0 1 4.6 13.5L4 5.5Zm2.4 1.6.3 6h.9l-.3-6h-.9Zm2.9 0-.3 6h.9l.3-6h-.9Z" fill="currentColor"/>' +
    "</svg>";
  button.addEventListener("click", (event) => {
    event.preventDefault();
    openRemoveFileModal(file);
  });
  return button;
}

function renderFiles(files) {
  lastFiles = files || [];
  lastFileCount = lastFiles.length;
  const review = lastFiles.filter((file) =>
    window.CAStatusSummary.isReviewOutcome(file.parse_outcome)
  );
  const rest = lastFiles.filter((file) =>
    !window.CAStatusSummary.isReviewOutcome(file.parse_outcome)
  );
  reviewBlock.classList.toggle("hidden", review.length === 0);
  updateReviewNote();
  reviewListEl.innerHTML = "";
  for (const file of review) {
    appendFileRow(reviewListEl, file, "review-row");
  }

  fileListEl.innerHTML = "";
  fileEmptyEl.classList.toggle("hidden", lastFiles.length > 0);
  for (const file of rest) {
    appendFileRow(fileListEl, file, "file-row");
  }
  updateScanNote();
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
  if (result.client) currentClient = result.client;
  kindOptions = result.kinds || [];
  currencyOptions = result.currencies || [];
  dumpTitleEl.textContent = result.period.label;
  dumpEyebrowEl.textContent = result.client ? result.client.name : "Document Workspace";
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

function money(value, currency) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
  if (/^[A-Z]{3}$/.test(code)) {
    try {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: code,
        currencyDisplay: "code",
      }).format(number);
    } catch {
      /* fall through to a neutral decimal format */
    }
  }
  return number.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

function moneyCell(value, currency) {
  const td = document.createElement("td");
  td.className = "num";
  td.textContent = money(value, currency);
  return td;
}

function renderPack(pack) {
  packHasBank = false;
  packOpenKey = "";
  packVisible = Boolean(pack && pack.exists);
  packBlock.classList.remove("match", "mismatch");
  if (!pack || !pack.exists) {
    packBlock.classList.add("hidden");
    updateReviewNote();
    return;
  }
  packBlock.classList.remove("hidden");
  const bankOut = (pack.outputs || []).find((out) => out.key === "bank");
  const purchaseOut = (pack.outputs || []).find((out) => out.key === "purchase");
  packHasBank = Boolean(bankOut);
  packOpenKey = bankOut ? "bank" : purchaseOut ? "purchase" : "";
  if (pack.balance_status === "match") packBlock.classList.add("match");
  if (pack.balance_status === "mismatch") packBlock.classList.add("mismatch");
  packMetaEl.textContent = `Excel ready · ${pack.row_count || 0} rows`;
  packFilesEl.innerHTML = "";
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
    btn.textContent = `${out.label} · ${out.rows} rows${out.status && out.status !== "ready" ? " · " + out.status : ""}`;
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
    moneyLine.textContent = `Opening ${money(file.opening_balance, file.currency_code)} · Stated close ${money(file.stated_closing, file.currency_code)} · Computed close ${money(file.computed_closing, file.currency_code)}`;
    if (file.currency_label) {
      const currencyLine = document.createElement("p");
      currencyLine.className = "file-meta";
      currencyLine.textContent = `Currency: ${file.currency_label}`;
      line.append(head, moneyLine, currencyLine);
    } else {
      line.append(head, moneyLine);
    }
    packFilesEl.append(line);
  }
  updateReviewNote();
  renderRecon(pack);
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

/* ------------------------------------------------------------------ */
/* Dashboard                                                          */
/* ------------------------------------------------------------------ */

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value === null || value === undefined ? "" : String(value);
}

function formatWhen(value) {
  if (!value) return "";
  const when = new Date(value);
  if (Number.isNaN(when.getTime())) return "";
  return when.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clearNode(node) {
  if (node) node.innerHTML = "";
}

async function openDocumentWorkspace() {
  const api = desktopApi();
  let state = lastAppState;
  if (api && api.get_state) {
    try {
      state = await api.get_state();
    } catch {
      state = lastAppState;
    }
  }
  if (state && state.firm && state.output_path) {
    showDesk(state);
    return;
  }
  showPane("clients");
  recordNav({ pane: "clients" });
  syncGuide();
}

async function showDashboard(options = {}) {
  showPane("dashboard");
  if (options.record !== false) recordNav({ pane: "dashboard" });
  syncGuide();
  await loadDashboard();
}

async function loadDashboard() {
  if (!dashboardLoadingEl) return;
  dashboardLoadingEl.classList.remove("hidden");
  dashboardContentEl.classList.add("hidden");
  dashboardEmptyEl.classList.add("hidden");
  showError(dashboardErrorEl, "");
  const api = desktopApi();
  if (!api || !api.get_dashboard) {
    dashboardLoadingEl.classList.add("hidden");
    showError(dashboardErrorEl, "Update the app to open the dashboard.");
    return;
  }
  let result;
  try {
    result = await api.get_dashboard();
  } catch {
    result = { ok: false, error: "Could not load the dashboard." };
  }
  dashboardLoadingEl.classList.add("hidden");
  if (!result || !result.ok) {
    showError(
      dashboardErrorEl,
      (result && result.error) || "Could not load the dashboard."
    );
    return;
  }
  dashboardData = result;
  renderDashboard(result);
}

function renderDashboard(data) {
  const totals = data.totals || {};
  dashboardContentEl.classList.remove("hidden");
  setText("dash-documents", Number(totals.documents) || 0);
  setText(
    "dash-documents-note",
    `${Number(totals.rows_extracted) || 0} rows extracted`
  );
  setText("dash-processed", Number(totals.processed) || 0);
  setText("dash-attention-count", Number(totals.attention) || 0);
  setText(
    "dash-attention-summary",
    `${Number(totals.needs_review) || 0} review · ${Number(totals.failed) || 0} failed · ${Number(totals.unclassified) || 0} unclassified`
  );
  setText("dash-periods", Number(totals.periods) || 0);
  setText(
    "dash-periods-note",
    `${Number(totals.recon_ready_periods) || 0} with a comparison`
  );
  setText("dash-clients", Number(totals.clients) || 0);
  const generated = formatWhen(data.generated_at);
  setText(
    "dashboard-sub",
    generated
      ? `Live counts from this PC’s document library · updated ${generated}`
      : "Live counts from this PC’s document library."
  );
  renderDashboardActivity(data.recent_activity || []);
  renderDashboardAttention(data.attention || []);
  renderDashboardTypes(data.document_types || []);
  renderDashboardRecon(data.latest_reconciliation);
  dashboardEmptyEl.classList.toggle(
    "hidden",
    (Number(totals.documents) || 0) > 0
  );
}

function renderDashboardActivity(activity) {
  const list = document.getElementById("dashboard-activity");
  if (!list) return;
  clearNode(list);
  const empty = document.getElementById("dashboard-activity-empty");
  if (!activity.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  for (const item of activity) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "practice-row";
    const main = document.createElement("span");
    main.className = "practice-row-main";
    const title = document.createElement("span");
    title.className = "practice-row-title";
    title.textContent = `${item.client_name || "Client"} · ${item.period_label || "Period"}`;
    const meta = document.createElement("span");
    meta.className = "practice-row-meta";
    const when = formatWhen(item.finished_at || item.created_at);
    meta.textContent = `${window.CAPracticeSummary.jobStatusLabel(item.status)} · ${Number(item.files) || 0} files${when ? ` · ${when}` : ""}`;
    main.append(title, meta);
    const side = document.createElement("span");
    side.className = "practice-row-side";
    const count = document.createElement("span");
    count.className = "num";
    count.textContent = `${Number(item.processed) || 0} / ${Number(item.files) || 0}`;
    const note = document.createElement("span");
    note.className = "practice-note";
    const attention =
      (Number(item.needs_review) || 0) +
      (Number(item.failed) || 0) +
      (Number(item.unclassified) || 0);
    note.textContent = attention ? `${attention} need attention` : "Processed";
    side.append(count, note);
    row.append(main, side);
    row.addEventListener("click", () => openPeriod(item.period_id));
    list.append(row);
  }
}

function renderDashboardAttention(items) {
  const list = document.getElementById("dashboard-attention");
  if (!list) return;
  clearNode(list);
  const empty = document.getElementById("dashboard-attention-empty");
  if (!items.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  for (const item of items) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "practice-row";
    const main = document.createElement("span");
    main.className = "practice-row-main";
    const title = document.createElement("span");
    title.className = "practice-row-title";
    title.textContent = item.file_name || "Document";
    const meta = document.createElement("span");
    meta.className = "practice-row-meta";
    meta.textContent = `${item.client_name || "Client"} · ${item.period_label || "Period"} · ${item.kind_label || item.kind || ""}`;
    const reason = document.createElement("span");
    reason.className = "practice-row-meta";
    reason.textContent = item.reason || "";
    main.append(title, meta, reason);
    const side = document.createElement("span");
    side.className = "practice-row-side";
    const pill = document.createElement("span");
    const outcome = item.outcome || "needs_review";
    pill.className = `pill outcome-${outcome}`;
    pill.textContent = window.CAStatusSummary.outcomeLabel(outcome);
    side.append(pill);
    row.append(main, side);
    row.addEventListener("click", () => openPeriod(item.period_id));
    list.append(row);
  }
}

function renderDashboardTypes(types) {
  const body = document.getElementById("dashboard-types");
  if (!body) return;
  clearNode(body);
  const empty = document.getElementById("dashboard-types-empty");
  if (!types.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  for (const item of types) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = item.label || item.kind;
    const count = document.createElement("td");
    count.className = "num";
    count.textContent = String(Number(item.count) || 0);
    const processed = document.createElement("td");
    processed.className = "num";
    processed.textContent = String(Number(item.processed) || 0);
    const attention = document.createElement("td");
    attention.className = "num";
    attention.textContent = String(
      (Number(item.needs_review) || 0) +
        (Number(item.failed) || 0) +
        (Number(item.unclassified) || 0)
    );
    tr.append(name, count, processed, attention);
    body.append(tr);
  }
}

function renderDashboardRecon(latest) {
  const box = document.getElementById("dashboard-recon");
  if (!box) return;
  clearNode(box);
  if (!latest || !latest.available) {
    const message = document.createElement("p");
    message.className = "practice-note";
    message.textContent =
      (latest && latest.message) ||
      "No period has two compatible processed datasets yet.";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ui-btn ui-btn-secondary";
    button.textContent = "Open Reconciliation";
    button.addEventListener("click", () => showReconciliation());
    box.append(message, button);
    return;
  }
  const title = document.createElement("p");
  title.className = "practice-recon-title";
  title.textContent = latest.workflow_label || "Reconciliation";
  const line = document.createElement("p");
  line.className = "practice-recon-line";
  line.textContent = `${latest.client_name || "Client"} · ${latest.period_label || "Period"}${latest.generated_at ? ` · ${formatWhen(latest.generated_at)}` : ""}`;
  const counts = document.createElement("p");
  counts.className = "practice-recon-counts";
  const summary = window.CAPracticeSummary.countsText(
    latest.counts || {},
    latest
  );
  for (const part of summary.split(" · ")) {
    const span = document.createElement("span");
    span.textContent = part;
    counts.append(span);
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ui-btn ui-btn-secondary";
  button.textContent = "Open this reconciliation";
  button.addEventListener("click", () =>
    showReconciliation({
      periodId: latest.period_id,
      workflowId: latest.workflow_id,
    })
  );
  box.append(title, line, counts, button);
}

/* ------------------------------------------------------------------ */
/* Reconciliation page                                                */
/* ------------------------------------------------------------------ */

async function showReconciliation(options = {}) {
  showPane("recon");
  if (options.record !== false) {
    recordNav({
      pane: "recon",
      reconPeriodId: options.periodId || selectedReconPeriodId,
    });
  }
  syncGuide();
  await loadReconciliationWorkspace(options);
}

async function loadReconciliationWorkspace(options = {}) {
  if (!reconLoadingEl) return;
  reconLoadingEl.classList.remove("hidden");
  reconEmptyEl.classList.add("hidden");
  reconWorkspaceEl.classList.add("hidden");
  showError(reconPageErrorEl, "");
  const api = desktopApi();
  if (!api || !api.get_reconciliation_workspace) {
    reconLoadingEl.classList.add("hidden");
    showError(reconPageErrorEl, "Update the app to open reconciliation.");
    return;
  }
  let result;
  try {
    result = await api.get_reconciliation_workspace();
  } catch {
    result = { ok: false, error: "Could not load reconciliation data." };
  }
  reconLoadingEl.classList.add("hidden");
  if (!result || !result.ok) {
    showError(
      reconPageErrorEl,
      (result && result.error) || "Could not load reconciliation data."
    );
    return;
  }
  reconWorkspaceData = result;
  const periods = result.periods || [];
  if (!periods.length) {
    reconEmptyEl.classList.remove("hidden");
    return;
  }
  const requested = Number(options.periodId || selectedReconPeriodId || 0);
  const chosen =
    periods.find((item) => item.id === requested) ||
    periods.find((item) => item.id === result.selected_period_id) ||
    periods[0];
  selectedReconPeriodId = chosen.id;
  renderReconPeriodOptions(periods);
  reconWorkspaceEl.classList.remove("hidden");

  const periodChanged = requested !== chosen.id;
  if (periodChanged) {
    lastReconPageResult = null;
    reconResultsEl.classList.add("hidden");
    reconMissingEl.classList.add("hidden");
  }

  const workflowId = options.workflowId || "";
  renderReconWorkspaceForSelection(workflowId || activeReconWorkflowId);
  const active = findReconWorkflow(chosen, workflowId || activeReconWorkflowId);
  if (active && active.available) {
    await runReconPage(active.id, { periodId: chosen.id });
  } else if (active && !active.available) {
    activeReconWorkflowId = active.id;
    showReconMissing(chosen, active);
  } else if (options.keepSelection && activeReconWorkflowId) {
    const kept = findReconWorkflow(chosen, activeReconWorkflowId);
    if (kept && kept.available) {
      await runReconPage(kept.id, { periodId: chosen.id });
    }
  }
}

function renderReconPeriodOptions(periods) {
  if (!reconPeriodEl) return;
  reconPeriodEl.innerHTML = "";
  for (const period of periods) {
    const option = document.createElement("option");
    option.value = String(period.id);
    option.textContent = `${period.client_name} · ${period.label}`;
    if (period.id === selectedReconPeriodId) option.selected = true;
    reconPeriodEl.append(option);
  }
}

function currentReconPeriod() {
  const periods = (reconWorkspaceData && reconWorkspaceData.periods) || [];
  return periods.find((item) => item.id === selectedReconPeriodId) || null;
}

function findReconWorkflow(period, workflowId) {
  if (!period || !workflowId) return null;
  return (
    (period.workflows || []).find((item) => item.id === workflowId) || null
  );
}

function renderReconWorkspaceForSelection(activeId) {
  const period = currentReconPeriod();
  if (!period) return;
  setText(
    "recon-period-meta",
    `${period.client_name} · ${Number(period.file_count) || 0} files · GSTR-2B ${Number(period.datasets.gstr_2b) || 0} · Invoices ${Number(period.datasets.invoices) || 0} · Purchase register ${Number(period.datasets.purchase_register) || 0} · Bank ${Number(period.datasets.bank) || 0} · Ledger ${Number(period.datasets.bank_ledger) || 0}`
  );
  renderReconWorkflowCards(period, activeId);
}

function renderReconWorkflowCards(period, activeId) {
  if (!reconWorkflowsEl) return;
  clearNode(reconWorkflowsEl);
  const definitions = (reconWorkspaceData && reconWorkspaceData.workflows) || [];
  const statusById = {};
  for (const status of period.workflows || []) statusById[status.id] = status;
  for (const definition of definitions) {
    const status = statusById[definition.id] || {
      available: false,
      missing: [definition.left_label, definition.right_label],
      left_count: 0,
      right_count: 0,
    };
    const button = document.createElement("button");
    button.type = "button";
    button.className = "recon-workflow";
    if (definition.id === activeId) button.classList.add("is-active");
    if (!status.available) button.classList.add("is-unavailable");
    const title = document.createElement("span");
    title.className = "recon-workflow-title";
    title.textContent = definition.label;
    const pill = document.createElement("span");
    pill.className = `pill ${status.available ? "match" : "review"}`;
    pill.textContent = status.available ? "Ready" : "Missing input";
    const desc = document.createElement("span");
    desc.className = "recon-workflow-desc";
    desc.textContent = definition.description;
    const meta = document.createElement("span");
    meta.className = "recon-workflow-meta";
    const left = document.createElement("span");
    left.textContent = `${definition.left_label} ${Number(status.left_count) || 0}`;
    const right = document.createElement("span");
    right.textContent = `${definition.right_label} ${Number(status.right_count) || 0}`;
    meta.append(left, right);
    button.append(title, pill, desc, meta);
    button.addEventListener("click", () => {
      if (reconPageBusy) return;
      activeReconWorkflowId = definition.id;
      renderReconWorkflowCards(period, definition.id);
      if (status.available) {
        runReconPage(definition.id, { periodId: period.id });
      } else {
        lastReconPageResult = null;
        reconResultsEl.classList.add("hidden");
        showReconMissing(period, status);
      }
    });
    reconWorkflowsEl.append(button);
  }
}

function showReconMissing(period, status) {
  if (!reconMissingEl) return;
  reconMissingEl.innerHTML = "";
  const title = document.createElement("strong");
  title.textContent = "Required input is missing";
  const message = document.createElement("p");
  const missing = (status && status.missing) || [];
  message.textContent = missing.length
    ? `This period does not have ${missing.join(" and ")} data. Process the source documents in the Document Workspace, then refresh. No reconciliation is calculated until both datasets are available.`
    : "This comparison needs more processed data.";
  reconMissingEl.append(title, message);
  reconMissingEl.classList.remove("hidden");
  reconResultsEl.classList.add("hidden");
  reconCalculatingEl.classList.add("hidden");
}

async function runReconPage(workflowId, options = {}) {
  if (reconPageBusy) return;
  const periodId = Number(options.periodId || selectedReconPeriodId || 0);
  if (!periodId) return;
  const period = currentReconPeriod();
  const status = findReconWorkflow(period, workflowId);
  if (status && !status.available) {
    showReconMissing(period, status);
    return;
  }
  const api = desktopApi();
  if (!api || !api.run_reconciliation) {
    showError(reconPageErrorEl, "Update the app to run reconciliation.");
    return;
  }
  reconPageBusy = true;
  activeReconWorkflowId = workflowId;
  reconPageFilter = "all";
  reconPageSearch = "";
  if (reconSearchEl) reconSearchEl.value = "";
  updateReconFilterButtons();
  showError(reconPageErrorEl, "");
  reconMissingEl.classList.add("hidden");
  reconResultsEl.classList.add("hidden");
  reconCalculatingEl.classList.remove("hidden");
  renderReconWorkflowCards(period, workflowId);
  let result;
  try {
    result = await api.run_reconciliation(periodId, workflowId);
  } catch {
    result = { ok: false, error: "Could not calculate this reconciliation." };
  }
  reconPageBusy = false;
  reconCalculatingEl.classList.add("hidden");
  if (Number(selectedReconPeriodId) !== periodId) return;
  if (!result || !result.ok) {
    showError(
      reconPageErrorEl,
      (result && result.error) || "Could not calculate this reconciliation."
    );
    return;
  }
  if (!result.available) {
    lastReconPageResult = null;
    showReconMissing(
      period,
      {
        available: false,
        missing: result.missing || [],
      }
    );
    return;
  }
  lastReconPageResult = result;
  renderReconPageResult(result);
}

function updateReconFilterButtons() {
  const filters = document.getElementById("recon-page-filters");
  if (!filters) return;
  for (const button of filters.querySelectorAll("[data-recon-page-filter]")) {
    const active =
      (button.getAttribute("data-recon-page-filter") || "all") === reconPageFilter;
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
}

function renderReconPageResult(result) {
  const workflow = result.workflow || {};
  if (reconResultTitleEl) reconResultTitleEl.textContent = workflow.label || "Reconciliation";
  setText(
    "recon-result-sub",
    `${result.period?.client_name || "Client"} · ${result.period?.label || "Period"} · ${formatWhen(result.generated_at)}`
  );
  if (reconResultStampEl) {
    reconResultStampEl.textContent = `${result.datasets?.left?.count || 0} + ${result.datasets?.right?.count || 0} rows`;
  }
  if (reconRulesEl) {
    reconRulesEl.textContent = `Rules: ${(workflow.rules || []).join(" ")}`;
  }
  renderReconDatasets(result);
  renderReconSummary(result);
  renderReconTotals(result);
  renderReconTableHead(result);
  updateReconFilterButtons();
  renderReconPageRows();
  reconResultsEl.classList.remove("hidden");
}

function renderReconDatasets(result) {
  const box = document.getElementById("recon-datasets");
  if (!box) return;
  clearNode(box);
  for (const side of ["left", "right"]) {
    const data = (result.datasets && result.datasets[side]) || {};
    const item = document.createElement("div");
    item.className = "recon-dataset";
    const label = document.createElement("strong");
    label.textContent = `${data.label || (side === "left" ? "Left" : "Right")} · ${Number(data.count) || 0} rows`;
    const files = (data.sources || [])
      .map((source) => source.file_name)
      .filter(Boolean);
    const text = document.createElement("span");
    text.textContent = files.length ? files.join(" · ") : "No source file recorded";
    item.append(label, text);
    box.append(item);
  }
}

function renderReconSummary(result) {
  if (!reconSummaryEl) return;
  clearNode(reconSummaryEl);
  const counts = result.counts || {};
  const workflow = result.workflow || {};
  const order = window.CAPracticeSummary.STATUS_KEYS;
  let shown = 0;
  for (const key of order) {
    const value = Number(counts[key]) || 0;
    if (!value) continue;
    shown += 1;
    const span = document.createElement("span");
    span.append(
      document.createTextNode(
        `${window.CAPracticeSummary.statusLabel(key, workflow)} `
      )
    );
    const strong = document.createElement("strong");
    strong.textContent = String(value);
    span.append(strong);
    reconSummaryEl.append(span);
  }
  if (!shown) {
    const span = document.createElement("span");
    span.textContent = "No rows";
    reconSummaryEl.append(span);
  }
}

function renderReconTotals(result) {
  if (!reconTotalsEl) return;
  clearNode(reconTotalsEl);
  const totals = result.totals || {};
  const workflow = result.workflow || {};
  const items = [
    [`${workflow.left_label || "Left"} total`, totals.left_amount],
    [`${workflow.right_label || "Right"} total`, totals.right_amount],
    ["Matched amount", totals.matched_amount],
    ["Difference (left − right)", totals.difference],
  ];
  for (const [label, value] of items) {
    const box = document.createElement("div");
    box.className = "recon-total";
    const key = document.createElement("span");
    key.className = "recon-total-k";
    key.textContent = label;
    const amount = document.createElement("span");
    amount.className = "recon-total-v";
    amount.textContent = money(value);
    box.append(key, amount);
    reconTotalsEl.append(box);
  }
}

function renderReconTableHead(result) {
  if (!reconTableHeadEl) return;
  clearNode(reconTableHeadEl);
  const workflow = result.workflow || {};
  const row = document.createElement("tr");
  const labels = [
    "Status",
    "Reference",
    "Party",
    "Date",
    `${workflow.left_label || "Left"} amount`,
    `${workflow.right_label || "Right"} amount`,
    "Difference",
    "Explanation",
  ];
  for (const label of labels) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    row.append(th);
  }
  reconTableHeadEl.append(row);
}

function reconReference(row) {
  const left = row.left && row.left.reference ? row.left.reference : "";
  const right = row.right && row.right.reference ? row.right.reference : "";
  if (left && right && left !== right) return `${left} / ${right}`;
  return left || right || "—";
}

function reconParty(row) {
  const left = row.left && row.left.party ? row.left.party : "";
  const right = row.right && row.right.party ? row.right.party : "";
  if (left && right && left !== right) return `${left} / ${right}`;
  return left || right || "—";
}

function reconDate(row) {
  const left = row.left && row.left.date ? row.left.date : "";
  const right = row.right && row.right.date ? row.right.date : "";
  if (left && right && left !== right) return `${left} / ${right}`;
  return left || right || "—";
}

function reconAmountCell(value, currency) {
  const td = document.createElement("td");
  td.className = "num";
  td.textContent = money(value, currency);
  return td;
}

function reconStatusPillForPage(status, workflow) {
  const pill = document.createElement("span");
  const tone = window.CAPracticeSummary.statusTone(status);
  pill.className = `pill ${tone === "muted" ? "mute" : tone}`;
  pill.textContent = window.CAPracticeSummary.statusLabel(status, workflow);
  return pill;
}

function renderReconPageRows() {
  if (!reconTableBodyEl || !lastReconPageResult) return;
  const result = lastReconPageResult;
  const workflow = result.workflow || {};
  const rows = window.CAPracticeSummary.filterRows(
    result.rows || [],
    reconPageFilter,
    reconPageSearch
  );
  clearNode(reconTableBodyEl);
  reconTableEmptyEl.classList.toggle("hidden", rows.length > 0);
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.className = "is-clickable";
    tr.tabIndex = 0;
    const status = document.createElement("td");
    status.append(reconStatusPillForPage(row.status, workflow));
    const reference = document.createElement("td");
    reference.className = "practice-mono";
    reference.textContent = reconReference(row);
    const party = document.createElement("td");
    party.className = "practice-wrap recon-party";
    party.textContent = reconParty(row);
    const date = document.createElement("td");
    date.className = "practice-mono";
    date.textContent = reconDate(row);
    const leftAmount = reconAmountCell(
      row.left ? row.left.amount : null,
      row.left ? row.left.currency : ""
    );
    const rightAmount = reconAmountCell(
      row.right ? row.right.amount : null,
      row.right ? row.right.currency : ""
    );
    const difference = reconAmountCell(
      row.differences ? row.differences.amount : null
    );
    const explanation = document.createElement("td");
    explanation.className = "recon-explanation";
    explanation.textContent = row.explanation || "";
    tr.append(
      status,
      reference,
      party,
      date,
      leftAmount,
      rightAmount,
      difference,
      explanation
    );
    const open = () => openReconDetail(row);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
    reconTableBodyEl.append(tr);
  }
}

/* ------------------------------------------------------------------ */
/* Reconciliation detail                                              */
/* ------------------------------------------------------------------ */

function sourceFieldValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return value.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function appendReconFieldGrid(container, record) {
  const fields = [
    ["Reference", record.reference],
    ["Date", record.date],
    ["Party", record.party],
    ["GSTIN", record.gstin],
    ["Amount", record.amount],
    ["Taxable", record.taxable],
    ["Tax", record.tax],
    ["Currency", record.currency],
    ["Description", record.description],
    ["Source row", record.source],
  ];
  const list = document.createElement("dl");
  list.className = "recon-field-grid";
  for (const [label, value] of fields) {
    if (value === null || value === undefined || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = sourceFieldValue(value);
    list.append(dt, dd);
  }
  if (!list.children.length) {
    const empty = document.createElement("p");
    empty.className = "recon-empty-side";
    empty.textContent = "No readable fields on this side.";
    container.append(empty);
    return;
  }
  container.append(list);
}

function isPageSource(record) {
  const name = String((record && record.file_name) || "").toLowerCase();
  return /\.(pdf|png|jpe?g|webp|tiff?|bmp)$/.test(name);
}

function appendReconSourceSide(label, record) {
  const panel = document.createElement("section");
  panel.className = "recon-source";
  const title = document.createElement("h2");
  title.textContent = label;
  panel.append(title);
  if (!record) {
    const empty = document.createElement("p");
    empty.className = "recon-empty-side";
    empty.textContent = "No record on this side.";
    panel.append(empty);
    return panel;
  }
  const meta = document.createElement("p");
  meta.className = "recon-source-meta";
  const bits = [
    record.file_name || "Source file",
    record.kind || "",
    record.source_page ? `page ${record.source_page}` : "",
  ].filter(Boolean);
  meta.textContent = bits.join(" · ");
  panel.append(meta);

  const actions = document.createElement("div");
  actions.className = "recon-source-actions";
  if (record.file_id) {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "ui-btn ui-btn-secondary";
    open.textContent = "Open original file";
    open.addEventListener("click", () => openReconSourceFile(record));
    actions.append(open);
  }
  if (record.file_id && record.source_page && isPageSource(record)) {
    const crop = document.createElement("button");
    crop.type = "button";
    crop.className = "ui-btn ui-btn-secondary";
    crop.textContent = "Show source page";
    crop.addEventListener("click", () => openReconSourceCrop(record, label));
    actions.append(crop);
  }
  if (actions.children.length) panel.append(actions);
  appendReconFieldGrid(panel, record);

  const extracted = document.createElement("div");
  extracted.className = "recon-extracted";
  const heading = document.createElement("p");
  heading.className = "practice-note";
  heading.textContent = "Extracted record";
  const detail = document.createElement("div");
  detail.textContent = "Loading…";
  extracted.append(heading, detail);
  panel.append(extracted);
  if (record.row_id) {
    loadReconExtractedRecord(record.row_id, detail);
  } else {
    detail.textContent = "No extracted-row id is available.";
  }
  return panel;
}

async function loadReconExtractedRecord(rowId, container) {
  const api = desktopApi();
  if (!api || !api.get_extracted_record) {
    container.textContent = "Update the app to inspect extracted records.";
    return;
  }
  let result;
  try {
    result = await api.get_extracted_record(rowId);
  } catch {
    result = { ok: false };
  }
  if (!result || !result.ok) {
    container.textContent = "Could not load the extracted record.";
    return;
  }
  container.innerHTML = "";
  const record = result.record || {};
  const list = document.createElement("dl");
  list.className = "recon-field-grid";
  for (const [key, value] of Object.entries(record)) {
    if (key === "fields" || key === "source_bbox") continue;
    if (value === null || value === undefined || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = key.replaceAll("_", " ");
    const dd = document.createElement("dd");
    dd.textContent = sourceFieldValue(value);
    list.append(dt, dd);
  }
  if (list.children.length) container.append(list);
  else container.textContent = "The extracted record is empty.";
}

async function openReconSourceFile(record) {
  const api = desktopApi();
  if (!api || !api.open_source_file) {
    showError(reconDetailErrorEl, "Update the app to open source files.");
    return;
  }
  showError(reconDetailErrorEl, "");
  let result;
  try {
    result = await api.open_source_file(record.file_id);
  } catch {
    result = { ok: false, error: "Could not open the source file." };
  }
  if (!result || !result.ok) {
    showError(
      reconDetailErrorEl,
      (result && result.error) || "Could not open the source file."
    );
  }
}

async function openReconSourceCrop(record, label) {
  const api = desktopApi();
  if (!api || !api.get_source_crop) {
    showError(reconDetailErrorEl, "Update the app to show source pages.");
    return;
  }
  let result;
  try {
    result = await api.get_source_crop(
      record.file_id,
      Number(record.source_page) || 1,
      record.source_bbox || ""
    );
  } catch {
    result = { ok: false, error: "Could not load the source page." };
  }
  if (!result || !result.ok) {
    showError(
      reconDetailErrorEl,
      (result && result.error) || "Could not load the source page."
    );
    return;
  }
  const src = result.data_url || result.path || "";
  if (!src) {
    showError(reconDetailErrorEl, "Could not load the source page.");
    return;
  }
  showError(reconDetailErrorEl, "");
  cropImageEl.src = src;
  cropImageEl.alt = `${record.file_name || label} page ${record.source_page || 1}`;
  cropCaptionEl.textContent = `${record.file_name || label} · page ${record.source_page || 1} · ${label}`;
  cropModal.classList.remove("hidden");
}

function openReconDetail(row) {
  if (!reconDetailModal) return;
  const result = lastReconPageResult || {};
  const workflow = result.workflow || {};
  reconDetailTitleEl.textContent = reconReference(row);
  reconDetailStatusEl.innerHTML = "";
  reconDetailStatusEl.append(reconStatusPillForPage(row.status, workflow));
  reconDetailExplanationEl.textContent = row.explanation || "";
  showError(reconDetailErrorEl, "");

  clearNode(reconDetailDiffsEl);
  const diffs = row.differences || {};
  const items = [
    ["Amount difference", diffs.amount],
    ["Tax difference", diffs.tax],
    ["Taxable difference", diffs.taxable],
    ["Date gap", diffs.date_days === null || diffs.date_days === undefined ? null : `${diffs.date_days} days`],
  ];
  for (const [label, value] of items) {
    const box = document.createElement("div");
    box.className = "recon-total";
    const key = document.createElement("span");
    key.className = "recon-total-k";
    key.textContent = label;
    const shown = document.createElement("span");
    shown.className = "recon-total-v";
    shown.textContent =
      typeof value === "number" && label !== "Date gap"
        ? money(value)
        : sourceFieldValue(value);
    box.append(key, shown);
    reconDetailDiffsEl.append(box);
  }

  clearNode(reconDetailBodyEl);
  reconDetailBodyEl.append(
    appendReconSourceSide(workflow.left_label || "Left dataset", row.left),
    appendReconSourceSide(workflow.right_label || "Right dataset", row.right)
  );
  reconDetailModal.classList.remove("hidden");
  const closeButton = document.getElementById("recon-detail-close");
  if (closeButton) closeButton.focus();
}

function closeReconDetail() {
  if (!reconDetailModal) return;
  reconDetailModal.classList.add("hidden");
  showError(reconDetailErrorEl, "");
}

/* ------------------------------------------------------------------ */
/* Reports                                                            */
/* ------------------------------------------------------------------ */

async function showReports(options = {}) {
  showPane("reports");
  if (options.record !== false) recordNav({ pane: "reports" });
  syncGuide();
  await loadReports();
}

async function loadReports() {
  if (!reportsLoadingEl) return;
  reportsLoadingEl.classList.remove("hidden");
  reportsEmptyEl.classList.add("hidden");
  reportsListEl.classList.add("hidden");
  showError(reportsErrorEl, "");
  const api = desktopApi();
  if (!api || !api.get_reports) {
    reportsLoadingEl.classList.add("hidden");
    showError(reportsErrorEl, "Update the app to open reports.");
    return;
  }
  let result;
  try {
    result = await api.get_reports();
  } catch {
    result = { ok: false, error: "Could not load generated packs." };
  }
  reportsLoadingEl.classList.add("hidden");
  if (!result || !result.ok) {
    showError(
      reportsErrorEl,
      (result && result.error) || "Could not load generated packs."
    );
    return;
  }
  reportsData = result;
  renderReports(result.packs || []);
}

function renderReports(packs) {
  clearNode(reportsListEl);
  reportsEmptyEl.classList.toggle("hidden", packs.length > 0);
  reportsListEl.classList.toggle("hidden", packs.length === 0);
  for (const pack of packs) {
    const section = document.createElement("section");
    section.className = "report-pack";
    const head = document.createElement("div");
    head.className = "report-pack-head";
    const titleWrap = document.createElement("div");
    const title = document.createElement("h2");
    title.textContent = `${pack.client_name} · ${pack.period_label}`;
    const meta = document.createElement("p");
    meta.className = "practice-note";
    const when = formatWhen(pack.created_at);
    meta.textContent = `${Number(pack.row_count) || 0} rows${when ? ` · ${when}` : ""}`;
    titleWrap.append(title, meta);
    const folder = document.createElement("button");
    folder.type = "button";
    folder.className = "ui-btn ui-btn-secondary";
    folder.textContent = "Open folder";
    folder.addEventListener("click", () => openReportFolder(pack.period_id));
    head.append(titleWrap, folder);
    section.append(head);
    for (const output of pack.outputs || []) {
      const row = document.createElement("div");
      row.className = "report-output";
      const name = document.createElement("span");
      name.className = "report-output-name";
      name.textContent = output.label || output.key || "Excel";
      const details = document.createElement("span");
      details.className = "report-output-meta";
      details.textContent = `${Number(output.rows) || 0} rows${output.status && output.status !== "ready" ? ` · ${output.status}` : ""}`;
      const open = document.createElement("button");
      open.type = "button";
      open.className = "ui-btn ui-btn-secondary";
      open.textContent = "Open";
      open.addEventListener("click", () =>
        openReportOutput(pack.period_id, output.key)
      );
      row.append(name, details, open);
      section.append(row);
    }
    reportsListEl.append(section);
  }
}

async function openReportOutput(periodId, key) {
  const api = desktopApi();
  if (!api || !api.open_bank_pack) return;
  let result;
  try {
    result = await api.open_bank_pack(periodId, key || "");
  } catch {
    result = { ok: false, error: "Could not open that pack." };
  }
  if (!result || !result.ok) {
    showError(reportsErrorEl, (result && result.error) || "Could not open that pack.");
  }
}

async function openReportFolder(periodId) {
  const api = desktopApi();
  if (!api || !api.open_pack_folder) return;
  let result;
  try {
    result = await api.open_pack_folder(periodId);
  } catch {
    result = { ok: false, error: "Could not open the pack folder." };
  }
  if (!result || !result.ok) {
    showError(
      reportsErrorEl,
      (result && result.error) || "Could not open the pack folder."
    );
  }
}

function looksLikeGstin(value) {
  if (value === null || value === undefined || value === "") return false;
  return String(value).trim().length === 15;
}

function cropCaptionValue(field, value, currency) {
  if (field === "supplier_gstin" || looksLikeGstin(value)) {
    const raw = value === null || value === undefined ? "" : String(value).trim();
    return raw || "—";
  }
  return money(value, currency);
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

function amountCell(file, row, field, value, currency) {
  const td = document.createElement("td");
  const gstinish = field === "supplier_gstin" || looksLikeGstin(value);
  td.className = gstinish ? "gstin" : "num";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "source-amt";
  btn.textContent = cropCaptionValue(field, value, currency);
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
    const currencyCode = (file.currency && file.currency.currency_code) || "";
    const title = document.createElement("p");
    title.className = "eyebrow";
    const currencyNote = file.currency && file.currency.currency_label
      ? ` · ${file.currency.currency_label}`
      : "";
    title.textContent = `${file.filename} · ${file.kind || ""} · ${file.row_count} rows${currencyNote}`;
    const table = document.createElement("table");
    table.className = "preview-table";
    const isBank = file.kind === "bank";
    const isInvoice = file.kind === "invoice";
    const isGstrInv = file.kind === "gstr_2b" || file.kind === "gstr_1";
    const isGstr3b = file.kind === "gstr_3b";
    const isBooks = file.kind === "tally" || file.kind === "zoho";
    const isSap = file.kind === "sap";
    table.innerHTML = isGstrInv
      ? "<thead><tr><th>Date</th><th>GSTIN</th><th>Trade</th><th>Invoice no</th><th>Taxable</th><th>Value</th><th>Flags</th></tr></thead>"
      : isGstr3b
        ? "<thead><tr><th>Section</th><th>Taxable</th><th>IGST</th><th>CGST</th><th>SGST</th><th>Cess</th></tr></thead>"
        : isInvoice
          ? "<thead><tr><th>Date</th><th>Supplier</th><th>GSTIN</th><th>Invoice no</th><th>Taxable</th><th>Tax</th><th>Value</th><th>Flags</th></tr></thead>"
          : isBank
            ? "<thead><tr><th>Date</th><th>Detail</th><th>Debit</th><th>Credit</th><th>Balance</th><th>Page</th></tr></thead>"
            : isSap
              ? "<thead><tr><th>Report</th><th>Date</th><th>Account / party</th><th>Document</th><th>Debit</th><th>Credit</th><th>Balance</th><th>Flags</th></tr></thead>"
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
          moneyCell(row.taxable, currencyCode),
          moneyCell(row.invoice_value, currencyCode),
          flagsCell(row)
        );
      } else if (isGstr3b) {
        tr.append(
          textCell(row.section),
          moneyCell(row.taxable, currencyCode),
          moneyCell(row.igst, currencyCode),
          moneyCell(row.cgst, currencyCode),
          moneyCell(row.sgst, currencyCode),
          moneyCell(row.cess, currencyCode)
        );
      } else if (isSap) {
        tr.append(
          textCell(row.report_type_label || row.report_type),
          textCell(row.posting_date || row.document_date || row.date),
          textCell(row.gl_account || row.account_name || row.party_name),
          textCell(row.document_number || row.invoice_number),
          moneyCell(row.debit, currencyCode || row.currency),
          moneyCell(row.credit, currencyCode || row.currency),
          moneyCell(row.balance, currencyCode || row.currency),
          flagsCell(row)
        );
      } else if (isBooks) {
        tr.append(
          textCell(row.register),
          textCell(row.invoice_date || row.date),
          textCell(row.supplier_name || row.party_name),
          textCell(row.supplier_gstin || row.gstin, "gstin"),
          textCell(row.invoice_number || row.voucher_number),
          moneyCell(row.invoice_value ?? row.amount, currencyCode),
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
            amountCell(file, row, "supplier_gstin", gstin, currencyCode),
            invTd,
            amountCell(file, row, "taxable_value", taxable, currencyCode),
            amountCell(file, row, "tax", row.tax, currencyCode),
            amountCell(file, row, "invoice_value", value, currencyCode),
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
              amountCell(file, row, "Debit", row.debit, row.currency_code || currencyCode),
              amountCell(file, row, "Credit", row.credit, row.currency_code || currencyCode),
              amountCell(file, row, "Balance", row.balance, row.currency_code || currencyCode),
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
      cell.colSpan = isGstrInv || isBooks ? 7 : isSap || isInvoice ? 8 : isGstr3b || isBank ? 6 : 5;
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
    if (isSap) {
      const note = document.createElement("p");
      note.className = "preview-note";
      note.textContent =
        "SAP report rows keep source debit, credit and balance values. Validation flags appear in the Excel.";
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
      setDumpStatus(window.CAStatusSummary.summarizeJobStatus(job));
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
      copy: "Click the period row. That is the Document Workspace for this month.",
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

function openRemoveFileModal(file) {
  const guard = window.CARemoveFile.guardRemoveFile({
    file,
    busy: activeJobId !== null,
  });
  if (guard.action !== "ready") {
    if (guard.reason) showError(dumpErrorEl, guard.reason);
    return;
  }
  removeFileTarget = file;
  removeFileCopyEl.textContent = window.CARemoveFile.confirmMessage(file);
  showError(removeFileErrorEl, "");
  removeFileModal.classList.remove("hidden");
  removeFileConfirmBtn.focus();
}

function closeRemoveFileModal() {
  removeFileTarget = null;
  removeFileModal.classList.add("hidden");
  showError(removeFileErrorEl, "");
}

async function confirmRemoveFile() {
  if (!removeFileTarget) {
    closeRemoveFileModal();
    return;
  }
  if (window.CARemoveFile.resolveRemoveChoice(true).action !== "remove") {
    closeRemoveFileModal();
    return;
  }
  const file = removeFileTarget;
  showError(removeFileErrorEl, "");
  removeFileConfirmBtn.disabled = true;
  removeFileConfirmBtn.textContent = "Removing…";
  let result;
  try {
    result = await window.pywebview.api.remove_period_file(file.id);
  } catch (error) {
    result = { ok: false, error: "Could not remove this file." };
  }
  removeFileConfirmBtn.disabled = false;
  removeFileConfirmBtn.textContent = "Remove file";
  if (!result || !result.ok) {
    // Stay open and report the failure; never claim a removal that did not happen.
    showError(
      removeFileErrorEl,
      (result && result.error) || "Could not remove this file. Nothing was changed."
    );
    return;
  }
  closeRemoveFileModal();
  if (result.refresh && currentPeriod) {
    await openPeriod(currentPeriod.id);
    return;
  }
  if (result.files) {
    if (result.period) currentPeriod = result.period;
    renderFiles(result.files || []);
    renderPack(result.pack);
    renderPreview(result.preview);
    setDumpStatus(window.CAStatusSummary.summarizeFiles(result.files || []));
    syncGuide();
    return;
  }
  if (currentPeriod) await openPeriod(currentPeriod.id);
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

const navDocumentsBtn = document.getElementById("nav-documents");
const navDashboardBtn = document.getElementById("nav-dashboard");
const navReconBtn = document.getElementById("nav-recon");
const navReportsBtn = document.getElementById("nav-reports");
if (navDocumentsBtn) navDocumentsBtn.addEventListener("click", openDocumentWorkspace);
if (navDashboardBtn) navDashboardBtn.addEventListener("click", () => showDashboard());
if (navReconBtn) navReconBtn.addEventListener("click", () => showReconciliation());
if (navReportsBtn) navReportsBtn.addEventListener("click", () => showReports());

const dashboardRefreshBtn = document.getElementById("dashboard-refresh");
if (dashboardRefreshBtn) dashboardRefreshBtn.addEventListener("click", loadDashboard);
for (const id of ["quick-workspace", "dashboard-start", "recon-go-workspace", "reports-go-workspace"]) {
  const button = document.getElementById(id);
  if (button) button.addEventListener("click", openDocumentWorkspace);
}
const quickReconBtn = document.getElementById("quick-recon");
if (quickReconBtn) quickReconBtn.addEventListener("click", () => showReconciliation());
const quickReportsBtn = document.getElementById("quick-reports");
if (quickReportsBtn) quickReportsBtn.addEventListener("click", () => showReports());

if (reconPeriodEl) {
  reconPeriodEl.addEventListener("change", () => {
    selectedReconPeriodId = Number(reconPeriodEl.value) || null;
    lastReconPageResult = null;
    reconResultsEl.classList.add("hidden");
    reconMissingEl.classList.add("hidden");
    showError(reconPageErrorEl, "");
    recordNav({ pane: "recon", reconPeriodId: selectedReconPeriodId });
    renderReconWorkspaceForSelection(activeReconWorkflowId);
    const period = currentReconPeriod();
    const active = findReconWorkflow(period, activeReconWorkflowId);
    if (active && active.available) {
      runReconPage(active.id, { periodId: selectedReconPeriodId });
    } else if (active && !active.available) {
      showReconMissing(period, active);
    }
  });
}
const reconRefreshBtn = document.getElementById("recon-refresh");
if (reconRefreshBtn) {
  reconRefreshBtn.addEventListener("click", () =>
    loadReconciliationWorkspace({ keepSelection: true })
  );
}
if (reconPageFiltersEl) {
  reconPageFiltersEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-recon-page-filter]");
    if (!button) return;
    reconPageFilter = button.getAttribute("data-recon-page-filter") || "all";
    updateReconFilterButtons();
    renderReconPageRows();
  });
}
if (reconSearchEl) {
  reconSearchEl.addEventListener("input", () => {
    reconPageSearch = reconSearchEl.value || "";
    renderReconPageRows();
  });
}
if (reconDetailModal) {
  reconDetailModal.addEventListener("click", (event) => {
    if (event.target === reconDetailModal) closeReconDetail();
  });
}
const reconDetailCloseBtn = document.getElementById("recon-detail-close");
if (reconDetailCloseBtn) reconDetailCloseBtn.addEventListener("click", closeReconDetail);
const reportsRefreshBtn = document.getElementById("reports-refresh");
if (reportsRefreshBtn) reportsRefreshBtn.addEventListener("click", loadReports);

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

if (removeFileModal) {
  removeFileModal.addEventListener("click", (event) => {
    if (event.target === removeFileModal) closeRemoveFileModal();
  });
}
document.getElementById("remove-file-cancel").addEventListener("click", closeRemoveFileModal);
removeFileConfirmBtn.addEventListener("click", confirmRemoveFile);

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
    if (removeFileModal && !removeFileModal.classList.contains("hidden")) {
      closeRemoveFileModal();
      return;
    }
    if (cropModal && !cropModal.classList.contains("hidden")) {
      closeCropModal();
      return;
    }
    if (unlockModal && !unlockModal.classList.contains("hidden")) {
      closeUnlockModal();
      return;
    }
    if (reconDetailModal && !reconDetailModal.classList.contains("hidden")) {
      closeReconDetail();
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

window.addEventListener("pywebviewready", boot);
