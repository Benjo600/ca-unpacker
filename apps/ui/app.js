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
const clientProfessionEl = document.getElementById("client-profession");
const clientEntityEl = document.getElementById("client-entity");
const clientProfessionCustomWrap = document.getElementById("client-profession-custom-wrap");
const clientProfessionCustomEl = document.getElementById("client-profession-custom");
const deskErrorEl = document.getElementById("desk-error");
const paneClients = document.getElementById("pane-clients");
const panePeriods = document.getElementById("pane-periods");
const paneDump = document.getElementById("pane-dump");
const periodClientNameEl = document.getElementById("period-client-name");
const profileForm = document.getElementById("profile-form");
const profileProfessionEl = document.getElementById("profile-profession");
const profileEntityEl = document.getElementById("profile-entity");
const profileGstEl = document.getElementById("profile-gst");
const profileProfessionCustomWrap = document.getElementById("profile-profession-custom-wrap");
const profileProfessionCustomEl = document.getElementById("profile-profession-custom");
const profileSummaryEl = document.getElementById("profile-summary");
const profileStateEl = document.getElementById("profile-state");
const profileNoteEl = document.getElementById("profile-note");
const profileErrorEl = document.getElementById("profile-error");
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
const treatmentBlock = document.getElementById("treatment-block");
const treatmentMetaEl = document.getElementById("treatment-meta");
const treatmentCountEl = document.getElementById("treatment-count");
const treatmentListEl = document.getElementById("treatment-list");
const treatmentNoteEl = document.getElementById("treatment-note");
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
const cropTitleEl = document.getElementById("crop-title");
const cropReadoutEl = document.getElementById("crop-readout");
const cropValueEl = document.getElementById("crop-value");
const previewPaneEl = document.getElementById("preview-pane");
const previewBodyEl = document.getElementById("preview-body");
const previewFootEl = document.getElementById("preview-foot");
const previewTitleEl = document.getElementById("preview-title");
const previewMetaEl = document.getElementById("preview-meta");
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
let cropSource = null;
let tesseractChecked = false;
let tesseractFound = true;
let guideDismissed = false;
let lastGuideHighlight = null;
let lastPeriodCount = 0;
let authState = null;
let devMode = false;
let lastAppState = null;
let previewFile = null;
let previewPage = 1;
let previewPassword = "";
let previewFormatted = true;
let previewSheet = "";
let previewFit = true;
let previewPageCount = 0;
let previewSeq = 0;
let previewTrigger = null;
let profileOptions = { professions: [], entity_types: [] };
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
        renderProfileOptions(state.profile_options);
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

function renderProfileOptions(options) {
  if (!options) return;
  profileOptions = options;
  const professions = options.professions || [];
  const groups = new Map();
  for (const item of professions) {
    if (!groups.has(item.group || "Other")) groups.set(item.group || "Other", []);
    groups.get(item.group || "Other").push(item);
  }

  for (const select of [clientProfessionEl, profileProfessionEl]) {
    if (!select) continue;
    const previous = select.value;
    select.innerHTML = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "Not set";
    select.append(none);
    for (const [group, items] of groups) {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group;
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item.key;
        option.textContent = item.label;
        optgroup.append(option);
      }
      select.append(optgroup);
    }
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = "Other (type below)";
    select.append(custom);
    select.value = previous || "";
  }

  for (const select of [clientEntityEl, profileEntityEl]) {
    if (!select) continue;
    const previous = select.value;
    select.innerHTML = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "Not set";
    select.append(none);
    for (const item of options.entity_types || []) {
      const option = document.createElement("option");
      option.value = item.key;
      option.textContent = item.label;
      select.append(option);
    }
    select.value = previous || "";
  }
  syncProfileCustomFields();
}

async function ensureProfileOptions() {
  if ((profileOptions.professions || []).length) return;
  try {
    const options = await window.pywebview.api.get_profile_options();
    if (options && options.professions) renderProfileOptions(options);
  } catch (error) {
    /* the form still works without the catalog */
  }
}

function syncProfileCustomFields() {
  if (clientProfessionCustomWrap) {
    clientProfessionCustomWrap.classList.toggle(
      "hidden",
      !clientProfessionEl || clientProfessionEl.value !== "custom"
    );
  }
  if (profileProfessionCustomWrap) {
    profileProfessionCustomWrap.classList.toggle(
      "hidden",
      !profileProfessionEl || profileProfessionEl.value !== "custom"
    );
  }
}

function readProfile(professionEl, entityEl, gstEl, customEl) {
  const key = professionEl ? professionEl.value : "";
  const profile = {
    profession_key: key,
    profession_label: key === "custom" ? (customEl ? customEl.value.trim() : "") : "",
    entity_type: entityEl ? entityEl.value : "",
    gst_registered: null,
  };
  if (gstEl && gstEl.value === "yes") profile.gst_registered = true;
  if (gstEl && gstEl.value === "no") profile.gst_registered = false;
  return profile;
}

function fillProfileForm(client) {
  const profile = (client && client.profile) || {};
  if (profileProfessionEl) profileProfessionEl.value = profile.profession_key || "";
  if (profileEntityEl) profileEntityEl.value = profile.entity_type || "";
  if (profileGstEl) {
    profileGstEl.value =
      profile.gst_registered === true ? "yes" : profile.gst_registered === false ? "no" : "";
  }
  if (profileProfessionCustomEl) {
    profileProfessionCustomEl.value =
      profile.profession_key === "custom" ? profile.profession_label || "" : "";
  }
  syncProfileCustomFields();
  if (profileSummaryEl) {
    profileSummaryEl.textContent = client && client.profile_is_set
      ? client.profile_summary || "Profile set"
      : "No profile set. Pick a profession to turn on treatment checks.";
  }
  if (profileStateEl) {
    profileStateEl.textContent = client && client.profile_is_set ? "Profile set" : "Not set";
    profileStateEl.className = "pill" + (client && client.profile_is_set ? " match" : "");
  }
  if (profileNoteEl) profileNoteEl.textContent = "";
}

function severityClass(severity) {
  if (severity === "review") return "mismatch";
  if (severity === "check") return "unknown";
  return "mute";
}

function severityLabel(severity) {
  if (severity === "review") return "Review";
  if (severity === "check") return "Check";
  return "Note";
}

function observedText(observed) {
  if (!observed) return "";
  const parts = [];
  if (observed.count !== undefined) parts.push(`${observed.count} line(s)`);
  if (observed.total !== undefined) parts.push(`total ${money(observed.total)}`);
  if (observed.largest !== undefined) parts.push(`largest ${money(observed.largest)}`);
  if (observed.turnover !== undefined) parts.push(`turnover ${money(observed.turnover)}`);
  if (observed.sales_lines !== undefined && observed.count === undefined) {
    parts.push(`${observed.sales_lines} sales line(s)`);
  }
  return parts.join(" · ");
}

function thresholdText(threshold) {
  if (!threshold) return "";
  const parts = [];
  if (threshold.amount !== undefined) parts.push(`${money(threshold.amount)}`);
  if (threshold.enhanced) parts.push(`enhanced ${money(threshold.enhanced)}`);
  if (threshold.basis) parts.push(threshold.basis);
  if (threshold.rate) parts.push(threshold.rate);
  if (threshold.as_of) parts.push(threshold.as_of);
  return parts.join(" · ");
}

function renderTreatment(pack) {
  if (!treatmentBlock) return;
  const treatment = pack && pack.treatment;
  if (!treatment) {
    treatmentBlock.classList.add("hidden");
    return;
  }
  treatmentBlock.classList.remove("hidden");
  const profile = treatment.profile || {};
  treatmentMetaEl.textContent = profile.summary
    ? `${profile.summary}${profile.gst_rate ? " · GST " + profile.gst_rate : ""}`
    : "Treatment notes for this period";
  const counts = treatment.counts || {};
  const total = counts.total || 0;
  treatmentCountEl.textContent = total
    ? `${counts.review || 0} to review · ${counts.check || 0} to check · ${counts.info || 0} notes`
    : "No flags";
  treatmentCountEl.className =
    "pill" + (counts.review ? " mismatch" : counts.check ? " unknown" : " match");

  treatmentListEl.innerHTML = "";
  for (const flag of treatment.flags || []) {
    const row = document.createElement("div");
    row.className = "treatment-row";
    const head = document.createElement("div");
    head.className = "treatment-row-head";
    const chip = document.createElement("span");
    chip.className = "pill " + severityClass(flag.severity);
    chip.textContent = severityLabel(flag.severity);
    const title = document.createElement("span");
    title.className = "treatment-title";
    title.textContent = flag.title || flag.code;
    head.append(chip, title);
    const detail = document.createElement("p");
    detail.className = "treatment-detail";
    detail.textContent = flag.detail || "";
    row.append(head, detail);

    const meta = [];
    if (flag.area) meta.push(flag.area);
    const observed = observedText(flag.observed);
    if (observed) meta.push(observed);
    const threshold = thresholdText(flag.threshold);
    if (threshold) meta.push(`limit ${threshold}`);
    if (flag.law_ref) meta.push(flag.law_ref);
    if (meta.length) {
      const metaEl = document.createElement("p");
      metaEl.className = "treatment-meta";
      metaEl.textContent = meta.join(" · ");
      row.append(metaEl);
    }
    if (flag.action) {
      const actionEl = document.createElement("p");
      actionEl.className = "treatment-action";
      actionEl.textContent = flag.action;
      row.append(actionEl);
    }
    treatmentListEl.append(row);
  }
  if (!(treatment.flags || []).length) {
    const empty = document.createElement("p");
    empty.className = "treatment-empty";
    empty.textContent = "Nothing in this period triggered a treatment check for this profile.";
    treatmentListEl.append(empty);
  }
  treatmentNoteEl.textContent = profile.watch
    ? `For this profession: ${profile.watch}`
    : treatment.disclaimer || "";
}

function renderTreatmentHint(client, pack) {
  if (!treatmentBlock) return;
  if (!pack || !pack.exists) return;
  if (pack.treatment) return;
  if (!client || !client.profile_is_set) return;
  treatmentBlock.classList.remove("hidden");
  treatmentMetaEl.textContent = client.profile_summary || "Profile set";
  treatmentCountEl.textContent = "Not generated";
  treatmentCountEl.className = "pill mute";
  treatmentListEl.innerHTML = "";
  const note = document.createElement("p");
  note.className = "treatment-empty";
  note.textContent =
    "This pack was built before the profile was set or last changed. Re-parse the period to generate its treatment notes.";
  treatmentListEl.append(note);
  treatmentNoteEl.textContent = "";
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
    const profile = document.createElement("span");
    profile.className = "client-profile" + (client.profile_is_set ? "" : " muted");
    profile.textContent = client.profile_is_set
      ? client.profile_summary || "Profile set"
      : "No profile";
    profile.title = profile.textContent;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "row-delete";
    del.textContent = "Delete";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteClientRow(client);
    });
    row.append(name, profile, gstin, del);
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

function appendFileRow(container, file, className) {
  const row = document.createElement("div");
  row.className = className;
  const details = document.createElement("div");
  details.className = "file-details";
  const name = document.createElement("button");
  name.type = "button";
  name.className = "name file-preview-open";
  name.textContent = file.original_name;
  name.title = "Preview this file";
  name.addEventListener("click", () => openFilePreview(file, 1));
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
  row.append(details, actions);
  container.append(row);
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
  if (state.profile_options) {
    renderProfileOptions(state.profile_options);
  } else {
    ensureProfileOptions();
  }
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
  await ensureProfileOptions();
  currentClient = result.client;
  periodClientNameEl.textContent = result.client.name;
  fillProfileForm(currentClient);
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
  renderTreatmentHint(result.client, result.pack);
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
  renderTreatment(pack);
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
    moneyLine.textContent = `Opening ${money(file.opening_balance)} · Stated close ${money(file.stated_closing)} · Computed close ${money(file.computed_closing)}`;
    line.append(head, moneyLine);
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
  td.append(btn);
  return td;
}

/* A compact clickable source reference, in the NotebookLM sense: small,
   labelled, always opens the crop of the exact spot the value came from. */
function citationChip(file, row, field, value, label, title) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "cite-chip";
  chip.textContent = label || "SRC";
  chip.title = title || "View source";
  chip.addEventListener("click", () => openSourceCrop(file, row, field, value));
  return chip;
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
    title.textContent = `${file.filename} · ${file.kind || ""} · ${file.row_count} rows`;
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
            if (page) {
              pageTd.append(
                citationChip(
                  file,
                  row,
                  "page",
                  null,
                  `p${page}`,
                  `${file.filename || "Statement"} · page ${page}`
                )
              );
            } else {
              pageTd.textContent = "—";
            }
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
  cropSource = null;
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
  const fieldName =
    field && field !== "page" ? String(field).replace(/_/g, " ") : "";
  cropTitleEl.textContent = file.filename || "Source file";
  cropCaptionEl.textContent = `Page ${page}${fieldName ? ` · ${fieldName}` : ""}`;
  const hasValue = Boolean(fieldName) && value !== null && value !== undefined;
  cropReadoutEl.hidden = !hasValue;
  cropValueEl.textContent = hasValue ? cropCaptionValue(field, value) : "";
  cropImageEl.src = src;
  cropImageEl.alt = `${file.filename || "Statement"} page ${page}`;
  cropSource = { file, page, bbox };
  cropModal.classList.remove("hidden");
}

async function copyCitationText(text, button) {
  let copied = false;
  try {
    await navigator.clipboard.writeText(text);
    copied = true;
  } catch {
    try {
      const scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.append(scratch);
      scratch.select();
      copied = document.execCommand("copy");
      scratch.remove();
    } catch {
      copied = false;
    }
  }
  const original = button.textContent;
  button.textContent = copied ? "Copied" : "Copy failed";
  setTimeout(() => {
    button.textContent = original;
  }, 1400);
}

/* ---------------------------------------------------------------- preview */

function previewElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function previewButton(label, onClick, className) {
  const button = previewElement("button", className || "ghost", label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

function formatFileSize(size) {
  const value = Number(size);
  if (!Number.isFinite(value) || value <= 0) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function previewMetaText(result) {
  const parts = [];
  if (result.kind_label) parts.push(result.kind_label);
  if (result.preview_type === "pdf" && result.page_count) {
    parts.push(`${result.page_count} ${result.page_count === 1 ? "page" : "pages"}`);
  }
  const size = formatFileSize(result.size);
  if (size) parts.push(size);
  return parts.join(" · ");
}

function openFilePreview(file, page = 1) {
  if (!file || !previewPaneEl) return;
  previewTrigger = document.activeElement;
  previewFile = file;
  previewPage = Math.max(1, Number(page) || 1);
  previewPassword = "";
  previewFormatted = true;
  previewSheet = "";
  previewFit = true;
  previewTitleEl.textContent = file.original_name || file.filename || "File";
  previewMetaEl.textContent = "";
  previewPaneEl.classList.remove("hidden");
  loadFilePreview();
}

function closeFilePreview() {
  if (!previewPaneEl || previewPaneEl.classList.contains("hidden")) return;
  previewPaneEl.classList.add("hidden");
  previewBodyEl.innerHTML = "";
  previewBodyEl.className = "preview-body";
  previewFootEl.innerHTML = "";
  previewFootEl.hidden = true;
  previewFile = null;
  previewPassword = "";
  previewSeq += 1;
  const target = previewTrigger;
  previewTrigger = null;
  if (target && typeof target.focus === "function" && document.contains(target)) {
    target.focus();
  }
}

function renderPreviewLoading() {
  previewBodyEl.innerHTML = "";
  previewBodyEl.className = "preview-body";
  previewFootEl.innerHTML = "";
  previewFootEl.hidden = true;
  previewBodyEl.append(previewElement("p", "preview-message", "Opening file…"));
}

async function loadFilePreview() {
  if (!previewFile) return;
  const api = desktopApi();
  if (!api || !api.get_file_preview) {
    renderPreviewError("Update the app to preview files here.");
    return;
  }
  const fileId = previewFile.id || previewFile.file_id;
  const seq = ++previewSeq;
  renderPreviewLoading();
  let result;
  try {
    result = await api.get_file_preview(
      fileId,
      previewPage,
      previewPassword,
      previewSheet,
      previewFormatted
    );
  } catch {
    result = { ok: false, error: "Could not open this file." };
  }
  if (seq !== previewSeq) return;
  if (!result || !result.ok) {
    if (result && result.reason === "password_required") {
      renderPreviewPassword(result.error);
      return;
    }
    renderPreviewError((result && result.error) || "Could not open this file.");
    return;
  }
  if (result.name) previewTitleEl.textContent = result.name;
  previewMetaEl.textContent = previewMetaText(result);
  renderPreviewResult(result);
}

function renderPreviewError(message) {
  previewBodyEl.innerHTML = "";
  previewBodyEl.className = "preview-body";
  previewFootEl.innerHTML = "";
  previewFootEl.hidden = true;
  previewPageCount = 0;
  const note = previewElement("p", "preview-message error");
  note.append(previewElement("strong", null, "This file cannot be shown."));
  note.append(document.createTextNode(message));
  previewBodyEl.append(note);
}

function renderPreviewPassword(message) {
  previewBodyEl.innerHTML = "";
  previewBodyEl.className = "preview-body";
  previewFootEl.innerHTML = "";
  previewFootEl.hidden = true;
  previewPageCount = 0;

  const form = previewElement("form", "preview-password");
  form.autocomplete = "off";
  const heading = previewElement("p", "preview-message", message || "This PDF needs a password.");
  form.append(heading);

  const label = previewElement("label", null, "PDF password");
  label.setAttribute("for", "preview-password");
  const input = document.createElement("input");
  input.id = "preview-password";
  input.type = "password";
  input.autocomplete = "off";
  form.append(label, input);

  const submit = previewElement("button", null, "Preview page");
  submit.type = "submit";
  form.append(submit, previewElement("p", "fine", "Used once for this preview. Not saved."));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    previewPassword = input.value;
    input.value = "";
    loadFilePreview();
  });
  previewBodyEl.append(form);
  input.focus();
}

function renderPreviewResult(result) {
  previewBodyEl.innerHTML = "";
  previewBodyEl.className = `preview-body preview-${result.preview_type || "unsupported"}`;
  previewFootEl.innerHTML = "";
  previewFootEl.hidden = true;
  previewPageCount = 0;

  if (result.preview_type === "pdf" || result.preview_type === "image") {
    renderPreviewImage(result);
  } else if (result.preview_type === "text") {
    renderPreviewText(result);
  } else if (result.preview_type === "table") {
    renderPreviewTable(result);
  } else if (result.preview_type === "archive") {
    renderPreviewArchive(result);
  } else {
    renderPreviewUnsupported(result);
  }
}

function applyPreviewFit() {
  const canvas = previewBodyEl.querySelector(".preview-canvas");
  if (!canvas) return;
  canvas.classList.toggle("actual", !previewFit);
}

function renderPreviewImage(result) {
  const image = result.image || {};
  const canvas = previewElement("div", "preview-canvas");
  const img = document.createElement("img");
  img.src = image.data_url;
  img.alt = `${result.name} page ${result.page || 1}`;
  img.draggable = false;
  canvas.append(img);
  previewBodyEl.append(canvas);
  applyPreviewFit();

  if (result.preview_type === "pdf") {
    previewPageCount = Number(result.page_count) || 0;
    const pager = previewElement("div", "preview-pager");
    const prev = previewButton("Previous", () => {
      if (previewPage <= 1) return;
      previewPage -= 1;
      loadFilePreview();
    });
    prev.disabled = result.page <= 1;
    const next = previewButton("Next", () => {
      if (previewPage >= result.page_count) return;
      previewPage += 1;
      loadFilePreview();
    });
    next.disabled = result.page >= result.page_count;

    const zoom = previewButton(previewFit ? "Actual size" : "Fit width", () => {
      previewFit = !previewFit;
      applyPreviewFit();
      zoom.textContent = previewFit ? "Actual size" : "Fit width";
    });

    pager.append(
      prev,
      previewElement("span", "page-label", `Page ${result.page} of ${result.page_count}`),
      next,
      previewElement("span", "spacer"),
      zoom
    );
    previewFootEl.append(pager);
    previewFootEl.hidden = false;
  }
}

function renderPreviewText(result) {
  const pre = previewElement("pre", "preview-text", result.text || "");
  previewBodyEl.append(pre);

  if (result.is_json) {
    previewFootEl.append(
      previewButton(result.formatted ? "Show raw file" : "Show formatted", () => {
        previewFormatted = !previewFormatted;
        loadFilePreview();
      })
    );
  }
  previewFootEl.append(
    previewButton(pre && pre.classList.contains("no-wrap") ? "Wrap lines" : "No wrap", (event) => {
      const wrap = pre.classList.toggle("no-wrap");
      event.currentTarget.textContent = wrap ? "Wrap lines" : "No wrap";
    })
  );

  if (result.note) previewFootEl.append(previewElement("p", "preview-note", result.note));
  previewFootEl.hidden = false;
}

function renderPreviewTable(result) {
  const table = result.table || {};
  const rows = table.rows || [];
  if (!rows.length) {
    previewBodyEl.append(previewElement("p", "preview-message", "This file has no rows to show."));
    return;
  }

  const wrap = previewElement("div", "preview-grid-wrap");
  const node = previewElement("table", "preview-grid");
  const width = rows.reduce((max, row) => Math.max(max, row.length), 0);
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (let index = 0; index < width; index += 1) {
    headerRow.append(previewElement("th", null, rows[0][index] == null ? "" : rows[0][index]));
  }
  head.append(headerRow);
  const body = document.createElement("tbody");
  for (const row of rows.slice(1)) {
    const tr = document.createElement("tr");
    for (let index = 0; index < width; index += 1) {
      tr.append(previewElement("td", null, row[index] == null ? "" : row[index]));
    }
    body.append(tr);
  }
  node.append(head, body);
  wrap.append(node);
  previewBodyEl.append(wrap);

  const sheets = table.sheets || [];
  if (sheets.length > 1) {
    const tabs = previewElement("div", "preview-pager");
    for (const name of sheets) {
      const tab = previewButton(name, () => {
        previewSheet = name;
        loadFilePreview();
      }, "ghost");
      if (name === table.sheet) tab.setAttribute("aria-pressed", "true");
      tabs.append(tab);
    }
    previewFootEl.append(tabs);
  }

  const note = result.note || "";
  if (note) previewFootEl.append(previewElement("p", "preview-note", note));
  previewFootEl.hidden = !previewFootEl.childElementCount;
}

function renderPreviewArchive(result) {
  const archive = result.archive || {};
  const entries = archive.entries || [];
  if (!entries.length) {
    previewBodyEl.append(previewElement("p", "preview-message", "This archive is empty."));
    return;
  }
  const list = previewElement("ul", "preview-archive");
  for (const entry of entries) {
    const item = document.createElement("li");
    item.append(previewElement("span", "entry-name", entry.name));
    item.append(previewElement("span", "entry-size", formatFileSize(entry.size) || "0 B"));
    list.append(item);
  }
  previewBodyEl.append(list);
  if (result.note) {
    previewFootEl.append(previewElement("p", "preview-note", result.note));
    previewFootEl.hidden = false;
  }
}

function renderPreviewUnsupported(result) {
  const note = previewElement("p", "preview-message");
  note.append(previewElement("strong", null, "No preview for this file type."));
  note.append(document.createTextNode(result.note || "Open it in its own program to read it."));
  previewBodyEl.append(note);
}

async function openSourceFile(file) {
  const api = desktopApi();
  if (!api || !api.open_source_file || !file) return;
  const fileId = file.id || file.file_id;
  let result;
  try {
    result = await api.open_source_file(fileId);
  } catch {
    result = { ok: false, error: "Could not open that file." };
  }
  if (!result || !result.ok) {
    showError(dumpErrorEl, (result && result.error) || "Could not open that file.");
  }
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
      copy: "Type the legal name as you file it, pick the profession if you know it, then click Add client. GSTIN and profile are optional.",
      items: ["Type the client name.", "Pick a profession, or leave it not set.", "Click Add client."],
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

async function boot(prefetched) {
  const state = prefetched || (await window.pywebview.api.get_state());
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
    auth: lastAppState ? lastAppState.auth : null,
    profile_options: lastAppState ? lastAppState.profile_options : null,
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
  const profile = readProfile(
    clientProfessionEl,
    clientEntityEl,
    null,
    clientProfessionCustomEl
  );
  if (clientGstinEl.value.trim()) profile.gst_registered = true;
  const result = await window.pywebview.api.create_client(
    clientNameEl.value,
    clientGstinEl.value,
    profile
  );
  if (!result.ok) {
    showError(deskErrorEl, result.error);
    return;
  }
  renderClients(result.clients);
  addForm.reset();
  syncProfileCustomFields();
  clientNameEl.focus();
  syncGuide();
});

clientProfessionEl.addEventListener("change", syncProfileCustomFields);
profileProfessionEl.addEventListener("change", syncProfileCustomFields);

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!currentClient) return;
  showError(profileErrorEl, "");
  const profile = readProfile(
    profileProfessionEl,
    profileEntityEl,
    profileGstEl,
    profileProfessionCustomEl
  );
  const result = await window.pywebview.api.update_client_profile(currentClient.id, profile);
  if (!result.ok) {
    showError(profileErrorEl, result.error);
    return;
  }
  currentClient = result.client;
  fillProfileForm(currentClient);
  renderClients(result.clients || []);
  if (profileNoteEl) {
    profileNoteEl.textContent =
      "Saved. Open a period and re-parse it to refresh that period's treatment notes.";
  }
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

function resetWorkspaceState() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  activeJobId = null;
  currentClient = null;
  currentPeriod = null;
  kindOptions = [];
  lastFiles = [];
  lastPreviewFiles = [];
  lastPack = null;
  packVisible = false;
  packHasBank = false;
  packOpenKey = "";
  reconFilter = "all";
  unlockFile = null;
  cropSource = null;
  lastPeriodCount = 0;
  lastGuideHighlight = null;
  previewFile = null;
  previewPage = 1;
  previewPassword = "";
  previewSheet = "";
  navHistory = [];
  navIndex = -1;
  closeCropModal();
  closeFilePreview();
  closeUnlockModal();
  closeProfilePanel();
  addForm.reset();
  syncProfileCustomFields();
  periodForm.reset();
  profileForm.reset();
}

document.getElementById("wipe-confirm").addEventListener("click", async () => {
  showError(wipeErrorEl, "");
  const result = await window.pywebview.api.wipe_and_reset();
  if (!result.ok) {
    showError(wipeErrorEl, result.error);
    return;
  }
  wipeModal.classList.add("hidden");
  resetWorkspaceState();
  await boot(result);
});

if (cropModal) {
  cropModal.addEventListener("click", (event) => {
    if (event.target === cropModal) closeCropModal();
  });
}
const cropCloseBtn = document.getElementById("crop-close");
if (cropCloseBtn) cropCloseBtn.addEventListener("click", closeCropModal);

const cropCopyBtn = document.getElementById("crop-copy");
if (cropCopyBtn) {
  cropCopyBtn.addEventListener("click", async () => {
    if (!cropSource) return;
    const { file, page, bbox } = cropSource;
    const citation = `${file.filename || "source"}#p${page}${bbox ? `@${bbox}` : ""}`;
    await copyCitationText(citation, cropCopyBtn);
  });
}

const cropOpenPageBtn = document.getElementById("crop-open-page");
if (cropOpenPageBtn) {
  cropOpenPageBtn.addEventListener("click", () => {
    if (!cropSource) return;
    const { file, page } = cropSource;
    closeCropModal();
    openFilePreview(file, page);
  });
}

const previewCloseBtn = document.getElementById("preview-close");
if (previewCloseBtn) previewCloseBtn.addEventListener("click", closeFilePreview);

const previewExternalBtn = document.getElementById("preview-external");
if (previewExternalBtn) {
  previewExternalBtn.addEventListener("click", () => openSourceFile(previewFile));
}

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
      return;
    }
    if (previewPaneEl && !previewPaneEl.classList.contains("hidden")) {
      closeFilePreview();
    }
    return;
  }
  if (isTypingTarget(event.target)) return;
  if (
    previewPaneEl &&
    !previewPaneEl.classList.contains("hidden") &&
    !event.altKey &&
    previewPageCount > 1 &&
    (event.key === "ArrowLeft" || event.key === "ArrowRight")
  ) {
    event.preventDefault();
    if (event.key === "ArrowLeft" && previewPage > 1) {
      previewPage -= 1;
      loadFilePreview();
    } else if (event.key === "ArrowRight" && previewPage < previewPageCount) {
      previewPage += 1;
      loadFilePreview();
    }
    return;
  }
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
