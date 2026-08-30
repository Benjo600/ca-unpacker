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
  addFilesBtn.disabled = busy;
  addFolderBtn.disabled = busy;
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

function showDesk(state) {
  setupEl.classList.add("hidden");
  deskEl.classList.remove("hidden");
  firmLabelEl.textContent = state.firm ? state.firm.name : "";
  setOutputLabel(state.output_path || "");
  renderClients(state.clients || []);
  showPane("clients");
  syncGuide();
}

function showSetup(state) {
  deskEl.classList.add("hidden");
  setupEl.classList.remove("hidden");
  const lib = document.getElementById("library-path");
  if (lib) lib.textContent = state.library_path || "";
  setOutputLabel(state.output_path || "");
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

function syncGuide() {
  const card = document.getElementById("guide");
  if (!card) return;
  const onSetup = guideOnSetup();
  if (onSetup || guideDismissed) {
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

async function boot() {
  const state = await window.pywebview.api.get_state();
  guideDismissed = Boolean(state.guide_dismissed);
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
  if (event.key !== "Escape") return;
  if (cropModal && !cropModal.classList.contains("hidden")) {
    closeCropModal();
    return;
  }
  if (unlockModal && !unlockModal.classList.contains("hidden")) {
    closeUnlockModal();
  }
});

window.addEventListener("pywebviewready", boot);
