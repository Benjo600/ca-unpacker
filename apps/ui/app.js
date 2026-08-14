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
const fileListEl = document.getElementById("file-list");
const fileEmptyEl = document.getElementById("file-empty");
const reviewBlock = document.getElementById("review-block");
const reviewListEl = document.getElementById("review-list");
const packBlock = document.getElementById("pack-block");
const packMetaEl = document.getElementById("pack-meta");
const packFilesEl = document.getElementById("pack-files");
const previewBlock = document.getElementById("preview-block");
const previewListEl = document.getElementById("preview-list");

let currentClient = null;
let currentPeriod = null;
let kindOptions = [];
let pollTimer = null;

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
    row.append(name, gstin);
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
    hint.textContent = "Open dump tray";
    hint.style.color = "#5c6b63";
    hint.style.fontSize = "13px";
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
    const result = await window.pywebview.api.override_kind(file.id, select.value);
    if (!result.ok) {
      showError(dumpErrorEl, result.error);
      return;
    }
    if (currentPeriod) await openPeriod(currentPeriod.id);
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

function renderFiles(files) {
  const review = files.filter((file) => file.needs_review);
  const rest = files.filter((file) => !file.needs_review);
  reviewBlock.classList.toggle("hidden", review.length === 0);
  reviewListEl.innerHTML = "";
  for (const file of review) {
    const row = document.createElement("div");
    row.className = "review-row";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = file.original_name;
    name.title = file.classify_reason || "";
    row.append(name, kindSelect(file, false));
    reviewListEl.append(row);
  }

  fileListEl.innerHTML = "";
  fileEmptyEl.classList.toggle("hidden", files.length > 0);
  for (const file of rest) {
    const row = document.createElement("div");
    row.className = "file-row";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = file.original_name;
    name.title = file.classify_reason || "";
    row.append(name, kindSelect(file, false));
    fileListEl.append(row);
  }
}

function setOutputLabel(path) {
  const label = document.getElementById("output-label");
  const field = document.getElementById("output-path");
  if (field && path) field.value = path;
  if (label) label.textContent = path ? path : "No output folder";
}

function showDesk(state) {
  setupEl.classList.add("hidden");
  deskEl.classList.remove("hidden");
  firmLabelEl.textContent = state.firm ? state.firm.name : "";
  setOutputLabel(state.output_path || "");
  renderClients(state.clients || []);
  showPane("clients");
}

function showSetup(state) {
  deskEl.classList.add("hidden");
  setupEl.classList.remove("hidden");
  const lib = document.getElementById("library-path");
  if (lib) lib.textContent = state.library_path || "";
  setOutputLabel(state.output_path || "");
  if (state.firm && state.firm.name) firmNameEl.value = state.firm.name;
  firmNameEl.focus();
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
  showPane("periods");
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
  dumpStatusEl.textContent = `${(result.files || []).length} files`;
  showPane("dump");
}

function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  return Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function renderPack(pack) {
  if (!pack || !pack.exists) {
    packBlock.classList.add("hidden");
    return;
  }
  packBlock.classList.remove("hidden");
  const result = pack.balance_status === "match" ? "all balances match" : "one or more mismatches";
  packMetaEl.textContent = `${pack.row_count || 0} extracted rows${pack.balance_status ? " · bank " + result : ""}`;
  packFilesEl.innerHTML = "";
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
    const line = document.createElement("p");
    line.className = "file-flag";
    line.textContent = `${file.filename} · ${file.row_count} bank lines · ${file.status}`;
    packFilesEl.append(line);
  }
}

function renderPreview(preview) {
  const files = (preview && preview.files) || [];
  if (!files.length) {
    previewBlock.classList.add("hidden");
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
    table.innerHTML = "<thead><tr><th>Date</th><th>Detail</th><th>Debit / Taxable</th><th>Credit / Tax</th><th>Balance / Value</th></tr></thead>";
    const body = document.createElement("tbody");
    for (const row of file.preview || []) {
      const tr = document.createElement("tr");
      const detail = row.description || row.trade_name || row.party_name || row.section || row.invoice_number || "";
      const left = row.debit ?? row.taxable_value ?? row.taxable;
      const mid = row.credit ?? row.tax;
      const right = row.balance ?? row.invoice_value ?? row.amount;
      tr.innerHTML = `<td>${row.date || row.invoice_date || ""}</td><td>${escapeHtml(detail)}</td><td class="num">${money(left)}</td><td class="num">${money(mid)}</td><td class="num">${money(right)}</td>`;
      body.append(tr);
    }
    table.append(body);
    previewListEl.append(title, table);
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function startDump(paths) {
  if (!currentPeriod) return;
  if (!paths || !paths.length) {
    showError(dumpErrorEl, "No files were chosen.");
    return;
  }
  showError(dumpErrorEl, "");
  dumpStatusEl.textContent = "Sorting…";
  const result = await window.pywebview.api.start_dump(currentPeriod.id, paths);
  if (!result.ok) {
    showError(dumpErrorEl, result.error);
    return;
  }
  pollJob(result.job_id);
}

function pollJob(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const result = await window.pywebview.api.get_job(jobId);
    if (!result.ok) return;
    const job = result.job;
    if (job.status === "routing" || job.status === "queued" || job.status === "parsing") {
      dumpStatusEl.textContent = job.status === "parsing" ? "Reading bank PDF…" : `Sorting ${job.files.length}…`;
      return;
    }
    clearInterval(pollTimer);
    pollTimer = null;
    if (job.status === "failed") {
      showError(dumpErrorEl, job.error_message || "Could not sort those files.");
    }
    await openPeriod(currentPeriod.id);
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
  return picked.output_path;
}

async function boot() {
  const state = await window.pywebview.api.get_state();
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
});

document.getElementById("back-to-clients").addEventListener("click", async () => {
  const state = await window.pywebview.api.get_state();
  currentPeriod = null;
  showDesk(state);
});

document.getElementById("back-to-periods").addEventListener("click", () => {
  if (currentClient) openClient(currentClient.id);
});

document.getElementById("open-pack").addEventListener("click", async () => {
  if (!currentPeriod) return;
  const result = await window.pywebview.api.open_bank_pack(currentPeriod.id, "");
  if (!result.ok) showError(dumpErrorEl, result.error);
});

document.getElementById("open-folder").addEventListener("click", async () => {
  if (!currentPeriod) return;
  const result = await window.pywebview.api.open_pack_folder(currentPeriod.id);
  if (!result.ok) showError(dumpErrorEl, result.error);
});

document.getElementById("add-files").addEventListener("click", async () => {
  const picked = await window.pywebview.api.pick_files();
  if (picked.ok) await startDump(picked.paths);
});

document.getElementById("add-folder").addEventListener("click", async () => {
  const picked = await window.pywebview.api.pick_folder();
  if (picked.ok) await startDump(picked.paths);
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("over"));
dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  dropZone.classList.remove("over");
  const paths = [];
  for (const file of event.dataTransfer.files) {
    if (file.path) paths.push(file.path);
  }
  if (!paths.length) {
    showError(dumpErrorEl, "Use Add files or Add folder if drag-and-drop does not give a path.");
    return;
  }
  await startDump(paths);
});

const wipeModal = document.getElementById("wipe-modal");
const wipeErrorEl = document.getElementById("wipe-error");

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

window.addEventListener("pywebviewready", boot);
