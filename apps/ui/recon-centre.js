/* CA Unpacker — Reconciliation Control Centre
 *
 * A self-contained controller for the desktop reconciliation workspace.  It
 * talks only to the DesktopApi bridge (window.pywebview.api); matching and
 * persistence remain in apps/engine.  No source accounting record is edited.
 */
(function () {
  "use strict";

  const state = {
    tab: "control",
    control: null,
    controlFilters: {
      client_id: "",
      financial_year: "",
      period_id: "",
      workflow_id: "",
      source_file_id: "",
      run_status: "",
      exception_status: "",
    },
    workspace: null,
    run: null,
    rows: null,
    rowFilters: {
      status: "all",
      category: "",
      exception_status: "",
      search: "",
      page: 1,
      page_size: 100,
    },
    exceptions: null,
    exceptionFilters: {
      status: "outstanding",
      category: "",
      client_id: "",
      period_id: "",
      financial_year: "",
      workflow_id: "",
      search: "",
      page: 1,
      page_size: 100,
    },
    history: null,
    historyFilters: {
      client_id: "",
      financial_year: "",
      period_id: "",
      workflow_id: "",
      run_status: "",
      search: "",
      page: 1,
      page_size: 50,
    },
    selectedRuns: [],
    rules: null,
    rulesDraft: null,
    selectedRuleKey: null,
    busy: false,
    searchTimer: null,
    opened: false,
  };

  const STATUS_TONE = {
    matched: "ok",
    accepted: "ok",
    manual: "ok",
    timing_difference: "ok",
    approved_adjustment: "ok",
    completed: "ok",
    exact: "ok",
    strong: "ok",
    proposed: "warn",
    probable: "warn",
    partial: "warn",
    review: "warn",
    investigating: "warn",
    assigned: "warn",
    reopened: "warn",
    completed_with_exceptions: "warn",
    running: "warn",
    queued: "warn",
    unmatched: "bad",
    duplicate: "bad",
    reversal_candidate: "bad",
    rejected: "bad",
    open: "bad",
    failed: "bad",
    cancelled: "muted",
    resolved: "ok",
    approved: "ok",
    closed: "muted",
  };

  const STATUS_LABEL = {
    all: "All rows",
    matched: "Matched",
    review: "Requires review",
    proposed: "Proposed",
    unmatched: "Unmatched",
    duplicate: "Duplicate",
    reversal: "Reversal candidates",
    open: "Open",
    investigating: "Investigating",
    assigned: "Assigned",
    resolved: "Resolved",
    approved: "Approved",
    timing_difference: "Timing difference",
    approved_adjustment: "Approved adjustment",
    reopened: "Reopened",
    closed: "Closed",
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
  };

  const CATEGORY_ORDER = [
    "unmatched_transaction",
    "amount_mismatch",
    "date_mismatch",
    "reference_mismatch",
    "gstin_mismatch",
    "gstin_invalid",
    "place_of_supply_mismatch",
    "duplicate_records",
    "partial_settlement",
    "missing_source_data",
    "currency_mismatch",
    "possible_reversal",
    "multiple_possible_matches",
    "allocation_required",
    "timing_difference",
    "bank_charge_interest",
    "balance_variance",
  ];

  // ---------------------------------------------------------------------
  // Small helpers
  // ---------------------------------------------------------------------

  function api() {
    return (window.pywebview && window.pywebview.api) || null;
  }

  async function call(name, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[name] !== "function") {
      return { ok: false, error: "This desktop build does not expose the reconciliation service yet." };
    }
    try {
      return await bridge[name](...args);
    } catch (error) {
      return { ok: false, error: String(error && error.message ? error.message : error) };
    }
  }

  function node(tag, props, ...children) {
    const el = document.createElement(tag);
    const options = props || {};
    for (const [key, value] of Object.entries(options)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key === "html") el.innerHTML = value;
      else if (key === "dataset") Object.assign(el.dataset, value);
      else if (key === "style") Object.assign(el.style, value);
      else if (key.startsWith("on") && typeof value === "function") {
        el.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === "value") el.value = value;
      else if (key === "checked") el.checked = Boolean(value);
      else if (key === "disabled") el.disabled = Boolean(value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat ? children.flat(Infinity) : children) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  function clear(el) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function fmtInt(value) {
    const number = Number(value);
    return Number.isFinite(number) ? new Intl.NumberFormat("en-IN").format(number) : "0";
  }

  function fmtMoney(value, currency) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const code = String(currency || "INR").toUpperCase();
    const safe = /^[A-Z]{3}$/.test(code) ? code : "INR";
    try {
      return new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: safe,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(number);
    } catch {
      return `₹${number.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
  }

  function fmtNumber(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return number.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(value) {
    if (!value) return "—";
    const when = new Date(value);
    if (Number.isNaN(when.getTime())) return String(value);
    return when.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function fmtDay(value) {
    if (!value) return "—";
    const when = new Date(value);
    if (Number.isNaN(when.getTime())) return String(value);
    return when.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }

  function labelize(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function statusLabel(status) {
    return STATUS_LABEL[status] || labelize(status);
  }

  function pill(text, tone) {
    return node("span", { class: `rc-pill rc-${tone || "muted"}`, text });
  }

  function statusPill(status) {
    return pill(statusLabel(status), STATUS_TONE[status] || "muted");
  }

  function categoryLabel(category) {
    return labelize(category);
  }

  function showPageError(message) {
    const el = document.getElementById("recon-page-error");
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = message;
  }

  let toastTimer = null;
  function toast(message, tone) {
    let box = document.getElementById("rc-toast");
    if (!box) {
      box = node("div", { id: "rc-toast", class: "rc-toast", role: "status" });
      document.body.append(box);
    }
    box.className = `rc-toast rc-toast-${tone || "ok"}`;
    box.textContent = message;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      box.className = "rc-toast hidden";
    }, 3800);
  }

  function busy(on) {
    state.busy = Boolean(on);
    document.body.classList.toggle("rc-busy", state.busy);
  }

  function debounce(fn, ms) {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(fn, ms);
  }

  function emptyState(title, copy, actions) {
    return node(
      "section",
      { class: "rc-empty" },
      node("p", { class: "rc-eyebrow", text: "Nothing to show" }),
      node("h2", { text: title }),
      node("p", { text: copy }),
      node("div", { class: "rc-empty-actions" }, ...(actions || []))
    );
  }

  function errorPanel(err) {
    return node(
      "div",
      { class: "rc-error-panel" },
      node("strong", { text: "The action could not be completed." }),
      node("p", { text: err || "Try refreshing the workspace." })
    );
  }

  function optionList(items, selected, placeholder) {
    const select = node("select", { class: "rc-select" });
    if (placeholder !== undefined) {
      select.append(node("option", { value: "", text: placeholder }));
    }
    for (const item of items || []) {
      const value = String(item.value);
      select.append(
        node("option", {
          value,
          text: item.label,
          selected: String(selected || "") === value ? true : undefined,
        })
      );
    }
    return select;
  }

  function field(label, control, note) {
    return node(
      "label",
      { class: "rc-field" },
      node("span", { class: "rc-field-label", text: label }),
      control,
      note ? node("span", { class: "rc-field-note", text: note }) : null
    );
  }

  function filterSelect(name, label, items, value, onChange) {
    const select = optionList(items, value, label);
    select.addEventListener("change", () => onChange(select.value));
    return select;
  }

  // ---------------------------------------------------------------------
  // Modal / drawer
  // ---------------------------------------------------------------------

  function createModal(options) {
    const config = options || {};
    const overlay = node("div", {
      class: `rc-overlay ${config.drawer ? "rc-drawer-overlay" : "rc-modal-overlay"}`,
    });
    const panel = node("div", {
      class: `rc-modal ${config.drawer ? "rc-drawer" : ""} ${config.wide ? "rc-modal-wide" : ""}`,
    });
    const title = node("h2", { text: config.title || "" });
    const subtitle = node("p", { class: "rc-modal-sub", text: config.subtitle || "" });
    const body = node("div", { class: "rc-modal-body" });
    const footer = node("div", { class: "rc-modal-foot" });
    const closeButton = node("button", {
      type: "button",
      class: "rc-icon-btn",
      "aria-label": "Close",
      text: "×",
      onclick: () => close(),
    });
    const head = node(
      "header",
      { class: "rc-modal-head" },
      node("div", {}, title, subtitle),
      closeButton
    );
    panel.append(head, body, footer);
    overlay.append(panel);
    document.body.append(overlay);

    let closed = false;
    function close() {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKey);
      overlay.remove();
      if (typeof config.onClose === "function") config.onClose();
    }
    function onKey(event) {
      if (event.key === "Escape") close();
    }
    overlay.addEventListener("mousedown", (event) => {
      if (event.target === overlay) close();
    });
    document.addEventListener("keydown", onKey);
    return {
      overlay,
      panel,
      head,
      body,
      footer,
      close,
      setTitle(value) {
        title.textContent = value;
      },
      setSubtitle(value) {
        subtitle.textContent = value;
      },
    };
  }

  function modalButton(text, className, onClick) {
    return node("button", {
      type: "button",
      class: `ui-btn ${className || "ui-btn-secondary"}`,
      text,
      onclick: onClick,
    });
  }

  function askReason(title, label, note, actionText) {
    return new Promise((resolve) => {
      const modal = createModal({
        title,
        subtitle: "Every manual decision needs an auditable reason.",
      });
      const input = node("textarea", {
        class: "rc-textarea",
        rows: "4",
        placeholder: "Explain the evidence you checked and why this decision is appropriate.",
      });
      const error = node("p", { class: "error", hidden: true });
      const submit = modalButton(actionText || "Save decision", "ui-btn-primary", () => {
        const reason = input.value.trim();
        if (reason.length < 3) {
          error.hidden = false;
          error.textContent = "Write at least a short reason before saving.";
          input.focus();
          return;
        }
        modal.close();
        resolve(reason);
      });
      modal.body.append(
        node("p", { class: "rc-callout", text: note || "The decision is recorded with your account, timestamp and the related records." }),
        field(label || "Reason", input),
        error
      );
      modal.footer.append(modalButton("Cancel", "ui-btn-secondary", () => {
        modal.close();
        resolve(null);
      }), submit);
      input.focus();
    });
  }

  // ---------------------------------------------------------------------
  // Navigation / shell
  // ---------------------------------------------------------------------

  function root() {
    return document.getElementById("recon-centre");
  }

  function renderTabs() {
    const tabs = document.getElementById("recon-tabs");
    if (!tabs) return;
    for (const button of tabs.querySelectorAll("[data-rc-tab]")) {
      const active = button.dataset.rcTab === state.tab;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
  }

  function switchTab(tab) {
    state.tab = tab;
    renderTabs();
    if (tab === "control") {
      loadControl(true).then(() => renderControl());
    } else if (tab === "workbench") renderWorkbench();
    else if (tab === "exceptions") loadExceptions();
    else if (tab === "history") loadHistory();
    else if (tab === "rules") loadRules();
  }

  async function open(options) {
    const config = options || {};
    if (!root()) return;
    state.opened = true;
    if (config.runId) {
      await openRun(Number(config.runId));
      return;
    }
    state.tab = config.tab || state.tab || "control";
    if (config.periodId) state.controlFilters.period_id = String(config.periodId);
    renderTabs();
    await Promise.all([loadControl(false), loadWorkspace()]);
    if (state.tab === "control") renderControl();
    else switchTab(state.tab);
  }

  async function refresh() {
    if (!state.opened) {
      await open({});
      return;
    }
    showPageError("");
    if (state.tab === "control") {
      await Promise.all([loadControl(true), loadWorkspace()]);
      renderControl();
    } else if (state.tab === "workbench") {
      if (state.run) {
        const run = await call("get_recon_run", state.run.id);
        if (run.ok) state.run = run;
        await loadRows();
        renderWorkbench();
      } else {
        await loadControl(false);
        renderWorkbench();
      }
    } else if (state.tab === "exceptions") await loadExceptions();
    else if (state.tab === "history") await loadHistory();
    else if (state.tab === "rules") await loadRules();
  }

  async function loadControl(reload) {
    if (state.control && !reload && !filtersActive()) {
      return;
    }
    const result = await call("get_recon_control_centre", state.controlFilters);
    if (!result || !result.ok) {
      showPageError((result && result.error) || "Could not load the reconciliation control centre.");
      state.control = null;
      return;
    }
    state.control = result;
    showPageError("");
  }

  function filtersActive() {
    return Object.values(state.controlFilters).some((value) => value !== "" && value !== null);
  }

  async function loadWorkspace() {
    const result = await call("get_recon_workspace");
    if (result && result.ok) state.workspace = result;
  }

  function setControlFilter(name, value) {
    state.controlFilters[name] = value;
    if (name === "client_id") state.controlFilters.period_id = "";
    loadControl(true).then(() => renderControl());
  }

  // ---------------------------------------------------------------------
  // Control Centre
  // ---------------------------------------------------------------------

  function renderControl() {
    const container = root();
    if (!container) return;
    clear(container);
    if (!state.control) {
      container.append(
        emptyState(
          "The control centre is unavailable",
          "The persisted reconciliation service could not be reached. Refresh or restart the desktop app.",
          [modalButton("Refresh", "ui-btn-primary", () => refresh())]
        )
      );
      return;
    }
    const data = state.control;
    container.append(
      renderControlFilters(data),
      renderMetrics(data),
      node(
        "div",
        { class: "rc-control-grid" },
        renderRecentRuns(data),
        renderOutstanding(data)
      ),
      renderCategoryStrip(data)
    );
  }

  function renderControlFilters(data) {
    const options = data.filters || {};
    const row = node("section", { class: "rc-filterbar", "aria-label": "Reconciliation filters" });
    const clientItems = [{ value: "", label: "All clients" }, ...(options.clients || []).map((item) => ({ value: item.id, label: item.name }))];
    row.append(
      filterSelect("client", "All clients", clientItems, state.controlFilters.client_id, (value) => setControlFilter("client_id", value)),
      filterSelect(
        "fy",
        "All financial years",
        [{ value: "", label: "All financial years" }, ...(options.financial_years || []).map((value) => ({ value, label: `FY ${value}` }))],
        state.controlFilters.financial_year,
        (value) => setControlFilter("financial_year", value)
      ),
      filterSelect(
        "period",
        "All periods",
        [
          { value: "", label: "All accounting periods" },
          ...(options.periods || [])
            .filter((item) => !state.controlFilters.client_id || String(item.client_id) === String(state.controlFilters.client_id))
            .map((item) => ({
              value: item.id,
              label: `${item.client_name} · ${item.label}`,
            })),
        ],
        state.controlFilters.period_id,
        (value) => setControlFilter("period_id", value)
      ),
      filterSelect(
        "workflow",
        "All reconciliation types",
        [{ value: "", label: "All reconciliation types" }, ...(options.workflows || []).map((item) => ({ value: item.id, label: item.label }))],
        state.controlFilters.workflow_id,
        (value) => setControlFilter("workflow_id", value)
      ),
      filterSelect(
        "source",
        "All source documents",
        [{ value: "", label: "All source documents" }, ...(options.source_files || []).map((item) => ({ value: item.id, label: item.name }))],
        state.controlFilters.source_file_id,
        (value) => setControlFilter("source_file_id", value)
      ),
      filterSelect(
        "status",
        "All run statuses",
        [{ value: "", label: "All run statuses" }, ...(options.run_statuses || []).map((value) => ({ value, label: statusLabel(value) }))],
        state.controlFilters.run_status,
        (value) => setControlFilter("run_status", value)
      ),
      filterSelect(
        "exception-status",
        "Any exception status",
        [{ value: "", label: "Any exception status" }, ...(options.exception_statuses || []).map((value) => ({ value, label: statusLabel(value) }))],
        state.controlFilters.exception_status,
        (value) => setControlFilter("exception_status", value)
      ),
      node("div", { class: "rc-filter-actions" },
        node("button", {
          type: "button",
          class: "rc-ghost-btn",
          text: "Clear filters",
          onclick: () => {
            state.controlFilters = {
              client_id: "", financial_year: "", period_id: "", workflow_id: "",
              source_file_id: "", run_status: "", exception_status: "",
            };
            loadControl(true).then(() => renderControl());
          },
        })
      )
    );
    return row;
  }

  function metricCard(label, value, note, tone, wide) {
    return node(
      "div",
      { class: `rc-metric ${wide ? "rc-metric-wide" : ""} ${tone ? `rc-metric-${tone}` : ""}` },
      node("span", { class: "rc-metric-label", text: label }),
      node("strong", { class: "rc-metric-value", text: value }),
      note ? node("span", { class: "rc-metric-note", text: note }) : null
    );
  }

  function renderMetrics(data) {
    const metrics = data.metrics || {};
    const completion = metrics.completion_counts || {};
    const completionText = [
      ["completed", "Completed", "ok"],
      ["completed_with_exceptions", "With exceptions", "warn"],
      ["in_progress", "In progress", "warn"],
      ["failed", "Failed", "bad"],
      ["cancelled", "Cancelled", "muted"],
    ]
      .filter(([key]) => Number(completion[key]) > 0)
      .map(([key, label, tone]) => pill(`${label} ${fmtInt(completion[key])}`, tone));
    if (!completionText.length) completionText.push(pill("No runs yet", "muted"));
    const grid = node("section", { class: "rc-metrics", "aria-label": "Reconciliation position" });
    grid.append(
      metricCard("Reconciliation runs", fmtInt(metrics.total_runs), "Persisted runs matching the filters"),
      metricCard("Records processed", fmtInt(metrics.records_processed), "Latest run per period and workflow"),
      metricCard("Matched records", fmtInt(metrics.matched_records), "Exact, strong and reviewed matches", "ok"),
      metricCard("Unmatched records", fmtInt(metrics.unmatched_records), "Still visible, never discarded", "bad"),
      metricCard("Requires investigation", fmtInt(metrics.requires_investigation), "Open exception positions", "warn"),
      metricCard("Duplicate records", fmtInt(metrics.duplicate_records), "Never paired arbitrarily", metrics.duplicate_records ? "bad" : ""),
      metricCard("Amount discrepancies", fmtInt(metrics.amount_discrepancies), "Amount and partial-settlement exceptions", metrics.amount_discrepancies ? "warn" : ""),
      metricCard(
        "Match rate",
        `${Number(metrics.match_rate || 0).toFixed(1)}%`,
        "Matched records ÷ processed records",
        Number(metrics.match_rate || 0) >= 80 ? "ok" : Number(metrics.match_rate || 0) > 0 ? "warn" : "muted"
      ),
      metricCard("Total debit value", fmtMoney(metrics.debit_total), "From stored source values"),
      metricCard("Total credit value", fmtMoney(metrics.credit_total), "From stored source values"),
      metricCard(
        "Unresolved exception value",
        fmtMoney(metrics.unresolved_exception_value),
        `${fmtInt(metrics.open_exceptions)} open exception(s)`,
        metrics.unresolved_exception_value ? "warn" : "ok"
      ),
      node(
        "div",
        { class: "rc-metric rc-metric-wide" },
        node("span", { class: "rc-metric-label", text: "Completion status" }),
        node("div", { class: "rc-metric-pills" }, ...completionText)
      )
    );
    return grid;
  }

  function runStatusPill(run) {
    const status = run.completion_status || run.status;
    return statusPill(status);
  }

  function runActionButton(text, onClick, title) {
    return node("button", {
      type: "button",
      class: "rc-link-btn",
      text,
      title: title || text,
      onclick: (event) => {
        event.stopPropagation();
        onClick();
      },
    });
  }

  function renderRecentRuns(data) {
    const section = node("section", { class: "rc-panel rc-panel-runs" });
    section.append(
      node(
        "div",
        { class: "rc-panel-head" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "History" }),
          node("h2", { text: "Recent reconciliation runs" })
        ),
        node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Open run history",
          onclick: () => switchTab("history"),
        })
      )
    );
    const runs = data.recent_runs || [];
    if (!runs.length) {
      section.append(
        emptyState(
          "No reconciliation has been run yet",
          "Process source documents, then start a run. Every run is persisted with its rules snapshot.",
          [modalButton("Run reconciliation", "ui-btn-primary", openRunModal)]
        )
      );
      return section;
    }
    const table = node("table", { class: "rc-table rc-table-compact" });
    table.append(
      node("thead", {},
        node("tr", {},
          ...["Run", "Client / period / type", "Status", "Records", "Matched", "Unmatched", "Match rate", ""].map(
            (label) => node("th", { text: label })
          )
        )
      )
    );
    const body = node("tbody");
    for (const run of runs) {
      const totals = run.totals || {};
      const tr = node("tr", {
        class: "rc-clickable",
        tabindex: "0",
        onclick: () => openRun(run.id),
        onkeydown: (event) => {
          if (event.key === "Enter" || event.key === " ") openRun(run.id);
        },
      });
      tr.append(
        node("td", {},
          node("span", { class: "rc-mono", text: String(run.run_uuid || "").slice(0, 8) }),
          node("span", { class: "rc-subtle rc-block", text: fmtDate(run.created_at) })
        ),
        node("td", {},
          node("strong", { text: run.client_name || "Client" }),
          node("span", { class: "rc-subtle rc-block", text: `${run.period_label || ""} · FY ${run.financial_year || "—"}` }),
          node("span", { class: "rc-subtle rc-block rc-wrap", text: run.workflow_label || "" })
        ),
        node("td", {}, runStatusPill(run)),
        node("td", { class: "rc-num", text: fmtInt(totals.records_processed) }),
        node("td", { class: "rc-num", text: fmtInt(totals.matched_records) }),
        node("td", { class: "rc-num", text: fmtInt(totals.unmatched_records) }),
        node("td", { class: "rc-num", text: `${Number(totals.match_rate || 0).toFixed(1)}%` }),
        node("td", { class: "rc-actions" },
          runActionButton("Open", () => openRun(run.id)),
          runActionButton("Export", () => exportRun(run.id)),
          runActionButton("Re-run", () => rerun(run.id))
        )
      );
      body.append(tr);
    }
    table.append(body);
    section.append(node("div", { class: "rc-table-wrap" }, table));
    return section;
  }

  function renderOutstanding(data) {
    const section = node("section", { class: "rc-panel rc-panel-exceptions" });
    section.append(
      node(
        "div",
        { class: "rc-panel-head" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Investigation" }),
          node("h2", { text: "Outstanding exceptions" })
        ),
        node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Open exception centre",
          onclick: () => switchTab("exceptions"),
        })
      )
    );
    const items = data.outstanding_exceptions || [];
    if (!items.length) {
      section.append(
        node("div", { class: "rc-quiet-state" },
          node("strong", { text: "No outstanding exceptions" }),
          node("p", { text: "Open runs still have their full exception history." })
        )
      );
      return section;
    }
    const table = node("table", { class: "rc-table rc-table-compact" });
    table.append(
      node("thead", {},
        node("tr", {},
          ...["Exception", "Amount", "Status", ""].map((label) => node("th", { text: label }))
        )
      )
    );
    const body = node("tbody");
    for (const item of items.slice(0, 12)) {
      const tr = node("tr", {
        class: "rc-clickable",
        onclick: () => openException(item.id),
      });
      tr.append(
        node("td", {},
          node("span", { class: "rc-subtle", text: item.category_label || categoryLabel(item.category) }),
          node("strong", { class: "rc-block rc-wrap", text: item.title || "" }),
          node("span", { class: "rc-subtle rc-block", text: `${item.client_name || ""} · ${item.period_label || ""}` })
        ),
        node("td", { class: "rc-num", text: fmtMoney(item.amount, item.currency) }),
        node("td", {}, statusPill(item.status)),
        node("td", {}, runActionButton("Investigate", () => openException(item.id)))
      );
      body.append(tr);
    }
    table.append(body);
    section.append(node("div", { class: "rc-table-wrap" }, table));
    return section;
  }

  function renderCategoryStrip(data) {
    const categories = data.exception_categories || [];
    if (!categories.length) {
      return node("section", { class: "rc-category-strip" },
        node("span", { class: "rc-eyebrow", text: "Exception mix" }),
        node("p", { class: "rc-subtle", text: "No open exceptions in the current scope." })
      );
    }
    return node(
      "section",
      { class: "rc-category-strip" },
      node("div", { class: "rc-category-strip-head" },
        node("span", { class: "rc-eyebrow", text: "Exception mix" }),
        node("span", { class: "rc-subtle", text: "Open items in the latest run for each scope" })
      ),
      node("div", { class: "rc-category-chips" },
        ...categories.map((item) =>
          node("button", {
            type: "button",
            class: "rc-category-chip",
            onclick: () => {
              state.exceptionFilters.category = item.category;
              state.exceptionFilters.status = "outstanding";
              switchTab("exceptions");
            },
          },
            node("span", { text: item.label }),
            node("strong", { text: fmtInt(item.count) })
          )
        )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Run modal and polling
  // ---------------------------------------------------------------------

  async function openRunModal() {
    await loadWorkspace();
    const workspace = state.workspace;
    if (!workspace || !(workspace.periods || []).length) {
      const modal = createModal({ title: "Run reconciliation", subtitle: "No client periods are available yet." });
      modal.body.append(
        emptyState(
          "Process documents first",
          "Create a client and period, then add the source documents in the Document Workspace. Reconciliation only reads processed rows.",
          [modalButton("Open Document Workspace", "ui-btn-primary", () => {
            modal.close();
            if (window.showWorkspace) window.showWorkspace();
            else document.getElementById("nav-documents")?.click();
          })]
        )
      );
      return;
    }
    const modal = createModal({
      title: "Run reconciliation",
      subtitle: "Every run is saved with a snapshot of the rules and source values.",
      wide: true,
    });
    const periodItems = (workspace.periods || []).map((period) => ({
      value: period.id,
      label: `${period.client_name} · ${period.label} · FY ${period.financial_year || financialYearGuess(period.label)}`,
    }));
    const periodSelect = optionList(periodItems, state.selectedPeriodId || "", "Choose a client period");
    const workflowSelect = node("select", { class: "rc-select" });
    const rulesSelect = node("select", { class: "rc-select" });
    const availability = node("div", { class: "rc-run-availability" });
    const userNote = node("textarea", {
      class: "rc-textarea",
      rows: "2",
      placeholder: "Optional run note (recorded in the audit trail)",
    });
    const error = node("p", { class: "error", hidden: true });
    const progressWrap = node("div", { class: "rc-progress hidden" });
    const progressBar = node("div", { class: "rc-progress-bar" });
    const progressText = node("p", { class: "rc-progress-text" });
    progressWrap.append(progressBar, progressText);
    const runButton = modalButton("Start reconciliation", "ui-btn-primary", start);
    const cancelButton = modalButton("Cancel run", "ui-btn-secondary", cancelRun);
    cancelButton.classList.add("hidden");
    modal.footer.append(modalButton("Close", "ui-btn-secondary", () => modal.close()), cancelButton, runButton);
    modal.body.append(
      field("Client period", periodSelect, "Only periods with processed source rows can be reconciled."),
      field("Reconciliation type", workflowSelect, "Each workflow uses the same matching engine with field-specific evidence."),
      field("Rule set", rulesSelect, "Leave on the automatic default to use the latest saved defaults for this workflow."),
      node("div", { class: "rc-run-actions-row" },
        node("span", { class: "rc-eyebrow", text: "Datasets for this run" }),
        node("span", { class: "rc-subtle", text: "Counts are read from stored extracted rows" })
      ),
      availability,
      field("Run note", userNote),
      error,
      progressWrap
    );

    let selectedPeriod = null;
    let selectedWorkflow = "";
    let pollTimer = null;
    let currentRunId = null;

    function financialYearGuess(label) {
      const match = String(label || "").match(/(20\d{2})/);
      const start = match ? Number(match[1]) : new Date().getFullYear();
      return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
    }

    function periodFor(id) {
      return (workspace.periods || []).find((item) => String(item.id) === String(id)) || null;
    }

    function workflowStatus(period, workflowId) {
      const status = ((period && period.workflows) || []).find((item) => item.id === workflowId);
      return status || { available: false, missing: ["source data"], left_count: 0, right_count: 0 };
    }

    function refreshWorkflowOptions() {
      clear(workflowSelect);
      workflowSelect.append(node("option", { value: "", text: "Choose a reconciliation type" }));
      for (const workflow of workspace.workflows || []) {
        const status = workflowStatus(selectedPeriod, workflow.id);
        workflowSelect.append(
          node("option", {
            value: workflow.id,
            text: `${workflow.label}${status.available ? "" : " — input missing"}`,
            disabled: status.available ? undefined : true,
          })
        );
      }
      refreshAvailability();
    }

    function refreshAvailability() {
      clear(availability);
      const workflow = (workspace.workflows || []).find((item) => item.id === selectedWorkflow);
      if (!selectedPeriod || !workflow) {
        availability.append(node("p", { class: "rc-subtle", text: "Choose a period and reconciliation type to see the source datasets." }));
        runButton.disabled = true;
        return;
      }
      const status = workflowStatus(selectedPeriod, selectedWorkflow);
      const cards = [
        ["Source A", workflow.left_label, status.left_count, status.left_sources || []],
        ["Source B", workflow.right_label, status.right_count, status.right_sources || []],
      ];
      availability.append(
        node("div", { class: "rc-dataset-cards" },
          ...cards.map(([side, label, count, sources]) =>
            node("div", { class: `rc-dataset-card ${count ? "" : "is-missing"}` },
              node("span", { class: "rc-eyebrow", text: side }),
              node("strong", { text: label }),
              node("span", { class: "rc-dataset-count", text: `${fmtInt(count)} row(s)` }),
              node("span", { class: "rc-subtle rc-wrap", text: (sources || []).map((item) => item.file_name).join(" · ") || "No source file recorded" })
            )
          )
        )
      );
      if (!status.available) {
        availability.append(
          node("p", { class: "rc-callout rc-callout-warn", text: `Input missing: ${(status.missing || []).join(" and ")}. Nothing will be calculated until both datasets are present.` })
        );
      }
      runButton.disabled = !status.available;
    }

    async function refreshRules() {
      clear(rulesSelect);
      rulesSelect.append(node("option", { value: "", text: "Automatic default (latest saved version)" }));
      if (!selectedWorkflow) return;
      const result = await call("get_recon_rules", selectedWorkflow);
      if (!result || !result.ok) return;
      for (const item of result.rulesets || []) {
        rulesSelect.append(
          node("option", {
            value: item.id,
            text: `${item.name} · v${item.version}${item.is_default ? " · default" : ""}`,
          })
        );
      }
    }

    periodSelect.addEventListener("change", () => {
      selectedPeriod = periodFor(periodSelect.value);
      refreshWorkflowOptions();
      refreshRules();
    });
    workflowSelect.addEventListener("change", () => {
      selectedWorkflow = workflowSelect.value;
      refreshAvailability();
      refreshRules();
    });

    async function start() {
      error.hidden = true;
      if (!selectedPeriod || !selectedWorkflow) {
        error.hidden = false;
        error.textContent = "Choose a period and reconciliation type first.";
        return;
      }
      runButton.disabled = true;
      cancelButton.classList.remove("hidden");
      progressWrap.classList.remove("hidden");
      progressBar.style.width = "2%";
      progressText.textContent = "Queuing the reconciliation run…";
      const result = await call(
        "start_recon_run",
        selectedPeriod.id,
        selectedWorkflow,
        rulesSelect.value ? Number(rulesSelect.value) : null
      );
      if (!result || !result.ok) {
        runButton.disabled = false;
        cancelButton.classList.add("hidden");
        error.hidden = false;
        error.textContent = (result && result.error) || "Could not start the reconciliation.";
        return;
      }
      currentRunId = result.id;
      toast("Reconciliation started. Results are persisted when it completes.", "ok");
      pollTimer = setInterval(() => poll(currentRunId), 800);
      await poll(currentRunId);
    }

    async function poll(runId) {
      const result = await call("get_recon_run", runId);
      if (!result || !result.ok) return;
      progressBar.style.width = `${Math.max(2, Number(result.progress || 0))}%`;
      progressText.textContent = `${statusLabel(result.status)} · ${Number(result.progress || 0)}% · ${result.client_name || ""} ${result.period_label || ""}`;
      if (result.status === "completed") {
        clearInterval(pollTimer);
        pollTimer = null;
        progressBar.style.width = "100%";
        progressText.textContent = "Completed. Opening the workbench…";
        setTimeout(() => {
          modal.close();
          openRun(runId);
        }, 350);
      } else if (result.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        runButton.disabled = false;
        cancelButton.classList.add("hidden");
        error.hidden = false;
        error.textContent = result.error_message || "The reconciliation failed.";
      } else if (result.status === "cancelled") {
        clearInterval(pollTimer);
        pollTimer = null;
        cancelButton.classList.add("hidden");
        runButton.disabled = false;
        error.hidden = false;
        error.textContent = "The reconciliation was cancelled. No partial results were stored.";
      }
    }

    async function cancelRun() {
      if (!currentRunId) return;
      const result = await call("cancel_recon_run", currentRunId);
      if (!result || !result.ok) {
        error.hidden = false;
        error.textContent = (result && result.error) || "Could not cancel the run.";
      }
    }

    periodSelect.value = state.controlFilters.period_id || state.selectedPeriodId || "";
    selectedPeriod = periodFor(periodSelect.value) || periodFor(periodItems[0] && periodItems[0].value);
    if (selectedPeriod) {
      periodSelect.value = String(selectedPeriod.id);
      refreshWorkflowOptions();
      refreshRules();
    }
    periodSelect.focus();
  }

  // ---------------------------------------------------------------------
  // Workbench
  // ---------------------------------------------------------------------

  async function openRun(runId) {
    showPageError("");
    const result = await call("get_recon_run", runId);
    if (!result || !result.ok) {
      showPageError((result && result.error) || "Could not open this reconciliation run.");
      return;
    }
    state.run = result;
    state.tab = "workbench";
    state.rowFilters = {
      status: "all", category: "", exception_status: "", search: "",
      page: 1, page_size: state.rowFilters.page_size || 100,
    };
    renderTabs();
    await loadRows();
    renderWorkbench();
  }

  async function loadRows() {
    if (!state.run) return;
    const filters = {
      ...state.rowFilters,
      page: state.rowFilters.page,
      page_size: state.rowFilters.page_size,
    };
    const result = await call("get_recon_run_rows", state.run.id, filters);
    if (!result || !result.ok) {
      showPageError((result && result.error) || "Could not load the reconciliation rows.");
      return;
    }
    state.rows = result;
  }

  function renderWorkbench() {
    const container = root();
    if (!container) return;
    clear(container);
    if (!state.run) {
      container.append(
        emptyState(
          "No run open",
          "Open a run from the Control Centre or start a new reconciliation. Results are persisted, so the workbench always opens a historical snapshot.",
          [
            modalButton("Open Control Centre", "ui-btn-secondary", () => switchTab("control")),
            modalButton("Run reconciliation", "ui-btn-primary", openRunModal),
          ]
        )
      );
      return;
    }
    const run = state.run;
    const totals = run.totals || {};
    container.append(
      node(
        "section",
        { class: "rc-run-head" },
        node("div", { class: "rc-run-title" },
          node("p", { class: "rc-eyebrow", text: `Run ${String(run.run_uuid || "").slice(0, 8)} · ${statusLabel(run.status)}` }),
          node("h2", { text: run.workflow_label || "Reconciliation" }),
          node("p", { class: "rc-subtle", text: `${run.client_name} · ${run.period_label} · FY ${run.financial_year} · ${fmtDate(run.completed_at || run.created_at)}` })
        ),
        node("div", { class: "rc-run-head-actions" },
          pill(statusLabel(run.completion_status || run.status), STATUS_TONE[run.completion_status || run.status] || "muted"),
          runActionButton("Export Excel + PDF", () => exportRun(run.id)),
          runActionButton("Re-run", () => rerun(run.id)),
          runActionButton("Run history", () => switchTab("history"))
        )
      ),
      renderRunMetrics(run, totals),
      renderDatasetStrip(run),
      renderRuleSnapshot(run),
      renderRowFilters(),
      renderRowsTable(),
      renderPagination(),
      renderChecks(run)
    );
  }

  function renderRunMetrics(run, totals) {
    const grid = node("section", { class: "rc-metrics rc-metrics-run" });
    const statusCard = metricCard("Run status", statusLabel(run.completion_status || run.status), `Rules v${run.ruleset_version || 1}`, STATUS_TONE[run.completion_status || run.status] || "");
    statusCard.classList.add("rc-metric-status");
    grid.append(
      metricCard("Records in run", fmtInt(totals.records_processed), `${fmtInt(totals.left_rows)} source A · ${fmtInt(totals.right_rows)} source B`),
      metricCard("Matched", fmtInt(totals.matched_records), "Confirmed or reviewed", "ok"),
      metricCard("Unmatched", fmtInt(totals.unmatched_records), "Both sides retained", "bad"),
      metricCard("Requires review", fmtInt(totals.proposed_records), "Proposed, partial and reversal positions", "warn"),
      metricCard("Duplicate records", fmtInt(totals.duplicate_records), "Not paired automatically", totals.duplicate_records ? "bad" : ""),
      metricCard("Amount discrepancies", fmtInt(totals.amount_discrepancies), "Exception count"),
      metricCard("Open exceptions", fmtInt(totals.open_exceptions), `${fmtInt(totals.total_exceptions)} total`),
      metricCard("Match rate", `${Number(totals.match_rate || 0).toFixed(1)}%`, "Matched records ÷ processed", Number(totals.match_rate || 0) >= 80 ? "ok" : "warn"),
      metricCard("Debit value", fmtMoney(totals.debit_total), "Stored source values"),
      metricCard("Credit value", fmtMoney(totals.credit_total), "Stored source values"),
      metricCard("Unresolved value", fmtMoney(totals.unresolved_amount), "Open exception value", totals.unresolved_amount ? "warn" : "ok"),
      statusCard
    );
    return grid;
  }

  function renderDatasetStrip(run) {
    const sources = run.source_files || [];
    const leftIds = (run.source_dataset_ids || {}).left || [];
    const rightIds = (run.source_dataset_ids || {}).right || [];
    const left = sources.filter((item) => leftIds.includes(item.file_id));
    const right = sources.filter((item) => rightIds.includes(item.file_id));
    return node(
      "section",
      { class: "rc-dataset-strip" },
      datasetSideCard("Source A", (run.totals || {}).left_rows, left),
      datasetSideCard("Source B", (run.totals || {}).right_rows, right),
      node("div", { class: "rc-dataset-side rc-dataset-rule" },
        node("span", { class: "rc-eyebrow", text: "Run identity" }),
        node("strong", { class: "rc-mono", text: run.run_uuid || "" }),
        node("span", { class: "rc-subtle", text: `Rules ${run.rules_snapshot?.ruleset?.name || "Default"} v${run.ruleset_version || 1} · snapshot preserved` })
      )
    );
  }

  function datasetSideCard(label, count, files) {
    return node(
      "div",
      { class: "rc-dataset-side" },
      node("span", { class: "rc-eyebrow", text: label }),
      node("strong", { text: `${fmtInt(count)} row(s)` }),
      node("span", { class: "rc-subtle rc-wrap", text: (files || []).map((item) => `${item.file_name} (${fmtInt(item.rows)})`).join(" · ") || "No file metadata recorded" })
    );
  }

  function renderRuleSnapshot(run) {
    const rules = run.rules_snapshot || {};
    const summary = rules.summary || [];
    if (!summary.length) return node("span", { class: "hidden" });
    return node(
      "details",
      { class: "rc-rule-snapshot" },
      node("summary", { text: "Rules and tolerances used for this run" }),
      node("ul", { class: "rc-rule-list" }, ...summary.map((item) => node("li", { text: item })))
    );
  }

  function renderRowFilters() {
    const bar = node("section", { class: "rc-workbench-filters" });
    const statusSelect = optionList(
      [
        { value: "all", label: "All rows" },
        { value: "matched", label: "Matched / accepted" },
        { value: "review", label: "Requires review" },
        { value: "proposed", label: "Proposed" },
        { value: "unmatched", label: "Unmatched" },
        { value: "duplicate", label: "Duplicate" },
        { value: "reversal", label: "Reversal candidates" },
      ],
      state.rowFilters.status,
      undefined
    );
    statusSelect.addEventListener("change", () => {
      state.rowFilters.status = statusSelect.value;
      state.rowFilters.page = 1;
      loadRows().then(renderWorkbench);
    });
    const categorySelect = optionList(
      [{ value: "", label: "All exception categories" }, ...CATEGORY_ORDER.map((category) => ({ value: category, label: categoryLabel(category) }))],
      state.rowFilters.category,
      undefined
    );
    categorySelect.addEventListener("change", () => {
      state.rowFilters.category = categorySelect.value;
      state.rowFilters.page = 1;
      loadRows().then(renderWorkbench);
    });
    const exceptionSelect = optionList(
      [
        { value: "", label: "Any exception status" },
        ...["open", "investigating", "assigned", "resolved", "approved", "timing_difference", "approved_adjustment", "reopened", "closed"].map((value) => ({ value, label: statusLabel(value) })),
      ],
      state.rowFilters.exception_status,
      undefined
    );
    exceptionSelect.addEventListener("change", () => {
      state.rowFilters.exception_status = exceptionSelect.value;
      state.rowFilters.page = 1;
      loadRows().then(renderWorkbench);
    });
    const search = node("input", {
      type: "search",
      class: "rc-input rc-search",
      placeholder: "Search reference, party, GSTIN, source file or explanation",
      value: state.rowFilters.search,
      autocomplete: "off",
    });
    search.addEventListener("input", () => {
      state.rowFilters.search = search.value;
      debounce(() => {
        state.rowFilters.page = 1;
        loadRows().then(renderWorkbench);
      }, 260);
    });
    const pageSize = optionList(
      [50, 100, 200, 500].map((value) => ({ value, label: `${value} rows` })),
      state.rowFilters.page_size,
      undefined
    );
    pageSize.addEventListener("change", () => {
      state.rowFilters.page_size = Number(pageSize.value) || 100;
      state.rowFilters.page = 1;
      loadRows().then(renderWorkbench);
    });
    bar.append(statusSelect, categorySelect, exceptionSelect, search, pageSize);
    return bar;
  }

  function renderRowsTable() {
    const section = node("section", { class: "rc-panel rc-workbench-panel" });
    if (!state.rows || !state.rows.rows.length) {
      section.append(
        node("div", { class: "rc-quiet-state" },
          node("strong", { text: "No rows match the current filters" }),
          node("p", { text: "Clear the filters or choose a different status. Unmatched records remain visible in the run." })
        )
      );
      return section;
    }
    const table = node("table", { class: "rc-table rc-workbench-table" });
    table.append(
      node("thead", {},
        node("tr", {},
          ...["Status", "Confidence", "Source A", "Source B", "Party / counterparty", "Amount A", "Amount B", "Difference", "Exception", "Source evidence", ""].map(
            (label) => node("th", { text: label })
          )
        )
      )
    );
    const body = node("tbody");
    for (const row of state.rows.rows) {
      const left = row.left[0] || {};
      const right = row.right[0] || {};
      const amountA = row.left.length ? row.left_amount : null;
      const amountB = row.right.length ? row.right_amount : null;
      const displayRef = (records, value) => {
        if (!records.length) return "—";
        const ref = records[0].reference || records[0].description || records[0].source || "record";
        return records.length > 1 ? `${ref} +${records.length - 1}` : ref;
      };
      const tr = node("tr", {
        class: "rc-clickable",
        tabindex: "0",
        onclick: () => openMatch(row.id),
        onkeydown: (event) => {
          if (event.key === "Enter" || event.key === " ") openMatch(row.id);
        },
      });
      const exceptionStatuses = (row.exceptions || []).map((item) => item.status);
      const tone = STATUS_TONE[row.classification] || STATUS_TONE[row.status] || "muted";
      tr.append(
        node("td", {},
          pill(labelize(row.classification), tone),
          node("span", { class: "rc-subtle rc-block", text: row.match_type === "manual" ? "Manual" : labelize(row.match_type) })
        ),
        node("td", {},
          node("div", { class: "rc-confidence" },
            node("div", { class: "rc-confidence-bar" },
              node("span", { style: { width: `${Number(row.confidence || 0)}%` } })
            ),
            node("span", { class: "rc-mono", text: `${Number(row.confidence || 0)}` })
          )
        ),
        node("td", {},
          node("strong", { class: "rc-mono rc-block", text: displayRef(row.left, left.reference) }),
          node("span", { class: "rc-subtle rc-block", text: `${left.date || "—"} · ${fmtMoney(amountA || (left.amount ?? null), left.currency)}` })
        ),
        node("td", {},
          node("strong", { class: "rc-mono rc-block", text: displayRef(row.right, right.reference) }),
          node("span", { class: "rc-subtle rc-block", text: `${right.date || "—"} · ${fmtMoney(amountB || (right.amount ?? null), right.currency)}` })
        ),
        node("td", { class: "rc-wrap", text: left.party || right.party || "—" }),
        node("td", { class: "rc-num", text: fmtMoney(amountA, left.currency) }),
        node("td", { class: "rc-num", text: fmtMoney(amountB, right.currency) }),
        node("td", { class: "rc-num", text: fmtMoney(row.difference_amount, left.currency || right.currency) }),
        node("td", {},
          ...(row.exceptions || []).slice(0, 2).map((item) => pill(item.category_label || categoryLabel(item.category), STATUS_TONE[item.status] || "warn")),
          !row.exceptions.length ? node("span", { class: "rc-subtle", text: "—" }) : null
        ),
        node("td", { class: "rc-source-cell" },
          node("span", { class: "rc-subtle rc-block rc-wrap", text: [left.file_name, left.source_page ? `p.${left.source_page}` : ""].filter(Boolean).join(" · ") || "—" }),
          node("span", { class: "rc-subtle rc-block rc-wrap", text: [right.file_name, right.source_page ? `p.${right.source_page}` : ""].filter(Boolean).join(" · ") || "—" })
        ),
        node("td", {}, runActionButton("Investigate", () => openMatch(row.id)))
      );
      if (exceptionStatuses.some((item) => ["open", "reopened", "investigating", "assigned"].includes(item))) {
        tr.classList.add("rc-row-attention");
      }
      body.append(tr);
    }
    table.append(body);
    section.append(node("div", { class: "rc-table-wrap rc-table-tall" }, table));
    return section;
  }

  function renderPagination() {
    if (!state.rows) return node("span", { class: "hidden" });
    const info = state.rows;
    const bar = node("div", { class: "rc-pagination" });
    bar.append(
      node("span", {
        class: "rc-subtle",
        text: `${fmtInt(info.total)} row(s) · page ${info.page} of ${info.pages}`,
      }),
      node("div", { class: "rc-pagination-actions" },
        node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Previous",
          disabled: info.page <= 1,
          onclick: () => {
            state.rowFilters.page = Math.max(1, info.page - 1);
            loadRows().then(renderWorkbench);
          },
        }),
        node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Next",
          disabled: info.page >= info.pages,
          onclick: () => {
            state.rowFilters.page = Math.min(info.pages, info.page + 1);
            loadRows().then(renderWorkbench);
          },
        })
      )
    );
    return bar;
  }

  function renderChecks(run) {
    const checks = run.checks || [];
    if (!checks.length) return node("span", { class: "hidden" });
    return node(
      "section",
      { class: "rc-panel rc-check-panel" },
      node("div", { class: "rc-panel-head" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Calculated controls" }),
          node("h2", { text: "Balance and movement checks" })
        ),
        node("span", { class: "rc-subtle", text: "Only calculated when the stored source rows support it" })
      ),
      node("div", { class: "rc-check-grid" },
        ...checks.map((check) =>
          node("div", { class: "rc-check-card" },
            node("div", { class: "rc-check-head" },
              node("strong", { text: check.name || "Check" }),
              pill(labelize(check.status), check.status === "calculated" ? "ok" : "warn")
            ),
            node("p", { class: "rc-subtle", text: check.explanation || "" }),
            node("div", { class: "rc-check-values" },
              node("span", { text: `${check.left_label || "Source A"}: ${fmtMoney(check.left?.closing_balance ?? check.left?.net ?? check.left?.closing)}` }),
              node("span", { text: `${check.right_label || "Source B"}: ${fmtMoney(check.right?.closing_balance ?? check.right?.net ?? check.right?.closing)}` }),
              node("strong", { text: `Difference: ${fmtMoney(check.difference)}` })
            )
          )
        )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Match investigation drawer
  // ---------------------------------------------------------------------

  function recordSummary(record) {
    if (!record) return node("div", { class: "rc-record-missing", text: "No record on this side." });
    return node(
      "div",
      { class: "rc-record" },
      node("div", { class: "rc-record-head" },
        node("div", {},
          node("strong", { class: "rc-mono", text: record.reference || record.description || "Record" }),
          node("span", { class: "rc-subtle rc-block", text: `${record.party || "—"} ${record.gstin ? `· ${record.gstin}` : ""}` })
        ),
        record.currency ? pill(record.currency, "muted") : null
      ),
      node("dl", { class: "rc-record-grid" },
        recordField("Date", record.date),
        recordField("Amount", fmtMoney(record.amount, record.currency)),
        recordField("Taxable", fmtMoney(record.taxable, record.currency)),
        recordField("Tax", fmtMoney(record.tax, record.currency)),
        recordField("Direction", record.direction || "—"),
        recordField("Document type", record.document_type || "—"),
        recordField("Source file", record.file_name || record.source || "—"),
        recordField("Page", record.source_page ? String(record.source_page) : "—"),
        recordField("Source coordinates", record.source_bbox || "—")
      ),
      node("div", { class: "rc-record-actions" },
        record.file_id ? node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Open source file",
          onclick: () => openSourceFile(record.file_id),
        }) : null,
        record.file_id && record.source_page ? node("button", {
          type: "button",
          class: "rc-link-btn",
          text: "Show source page",
          onclick: () => openSourcePage(record),
        }) : null
      ),
      record.raw ? node("details", { class: "rc-raw" },
        node("summary", { text: "Extracted source fields" }),
        node("pre", { text: JSON.stringify(record.raw, null, 2) })
      ) : null
    );
  }

  function recordField(label, value) {
    return node("div", { class: "rc-record-field" },
      node("dt", { text: label }),
      node("dd", { text: value === null || value === undefined || value === "" ? "—" : String(value) })
    );
  }

  async function openMatch(matchId) {
    const result = await call("get_recon_match", matchId);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not load this row.", "bad");
      return;
    }
    renderMatchDrawer(result);
  }

  function renderMatchDrawer(detail) {
    const match = detail.match;
    const run = detail.run || {};
    const drawer = createModal({
      title: match.left[0]?.reference || match.right[0]?.reference || `Row ${match.id}`,
      subtitle: `${run.workflow_label || "Reconciliation"} · ${run.client_name || ""} · ${run.period_label || ""}`,
      drawer: true,
      wide: true,
    });
    const header = node("div", { class: "rc-drawer-summary" },
      pill(labelize(match.classification), STATUS_TONE[match.classification] || "muted"),
      statusPill(match.status),
      node("span", { class: "rc-confidence rc-confidence-inline" },
        node("span", { class: "rc-subtle", text: "Confidence" }),
        node("div", { class: "rc-confidence-bar" }, node("span", { style: { width: `${match.confidence}%` } })),
        node("strong", { class: "rc-mono", text: `${match.confidence}` })
      )
    );
    const explanation = node("p", { class: "rc-explanation", text: match.explanation || "" });
    const actions = node("div", { class: "rc-drawer-actions" });
    if (
      match.left.length &&
      match.right.length &&
      match.classification !== "reversal_candidate" &&
      !["accepted", "manual", "timing_difference", "approved_adjustment"].includes(match.status)
    ) {
      actions.append(
        modalButton("Accept match", "ui-btn-primary", () => decideMatch("accept", match, drawer)),
        modalButton("Reject match", "ui-btn-secondary", () => decideMatch("reject", match, drawer))
      );
    }
    if (["matched", "accepted", "manual", "timing_difference", "approved_adjustment"].includes(match.status)) {
      actions.append(modalButton("Unmatch", "ui-btn-secondary", () => decideMatch("unmatch", match, drawer)));
    }
    if (
      match.left.length &&
      match.right.length &&
      match.classification !== "reversal_candidate" &&
      !["accepted", "manual"].includes(match.status)
    ) {
      actions.append(modalButton("Manual match", "ui-btn-secondary", () => openManualMatch(match)));
    }
    if (!match.left.length || !match.right.length) {
      actions.append(modalButton("Find counterpart", "ui-btn-primary", () => openManualMatch(match)));
    }
    actions.append(modalButton("Add note", "ui-btn-secondary", () => addMatchNote(match, drawer)));
    const content = node("div", { class: "rc-drawer-content" });
    content.append(
      header,
      explanation,
      actions,
      node("div", { class: "rc-drawer-metrics" },
        metricCard("Amount A", match.left.length ? fmtMoney(match.left_amount, match.currency) : "—", "Source A stored value"),
        metricCard("Amount B", match.right.length ? fmtMoney(match.right_amount, match.currency) : "—", "Source B stored value"),
        metricCard("Difference", fmtMoney(match.difference_amount, match.currency), "Absolute difference", match.difference_amount ? "warn" : "ok"),
        metricCard("Date gap", match.differences?.date_days === null || match.differences?.date_days === undefined ? "—" : `${match.differences.date_days} day(s)`, "Stored dates")
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Field-by-field comparison" }),
        renderFieldTable(match)
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Tolerances and evidence" }),
        node("ul", { class: "rc-rule-list" }, ...(match.tolerances || []).map((item) => node("li", { text: item }))),
        ...(match.exception_categories || []).map((category) => pill(categoryLabel(category), "warn"))
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Original source records" }),
        node("div", { class: "rc-record-columns" },
          node("div", {},
            node("p", { class: "rc-eyebrow", text: `Source A · ${run.totals ? "" : ""}${match.left.length} record(s)` }),
            ...match.left.map(recordSummary)
          ),
          node("div", {},
            node("p", { class: "rc-eyebrow", text: `Source B · ${match.right.length} record(s)` }),
            ...match.right.map(recordSummary)
          )
        )
      )
    );
    if ((match.candidates || []).length) {
      const candidates = node("div", { class: "rc-candidate-list" });
      for (const candidate of match.candidates) {
        candidates.append(
          node("div", { class: "rc-candidate" },
            node("div", {},
              node("strong", { class: "rc-mono", text: candidate.reference || candidate.description || "Candidate" }),
              node("span", { class: "rc-subtle rc-block", text: `${candidate.party || ""} · ${candidate.date || ""} · ${fmtMoney(candidate.amount, candidate.currency)}` })
            ),
            node("button", {
              type: "button",
              class: "rc-link-btn",
              text: "Use this candidate",
              onclick: () => openManualMatch(match, candidate),
            })
          )
        );
      }
      content.append(
        node("section", { class: "rc-drawer-section" },
          node("h3", { text: "Candidate records" }),
          node("p", { class: "rc-subtle", text: "These records had similar evidence but were not allocated automatically." }),
          candidates
        )
      );
    }
    if ((match.allocations || []).length) {
      const table = node("table", { class: "rc-table rc-table-compact" });
      table.append(
        node("thead", {}, node("tr", {},
          ...["Source A row", "Source B row", "Allocated amount", "Basis"].map((label) => node("th", { text: label }))
        ))
      );
      const body = node("tbody");
      for (const allocation of match.allocations) {
        body.append(
          node("tr", {},
            node("td", { class: "rc-mono", text: allocation.left_id || "" }),
            node("td", { class: "rc-mono", text: allocation.right_id || "" }),
            node("td", { class: "rc-num", text: fmtMoney(allocation.amount, match.currency) }),
            node("td", { class: "rc-wrap", text: allocation.basis || "" })
          )
        );
      }
      table.append(body);
      content.append(
        node("section", { class: "rc-drawer-section" },
          node("h3", { text: "Allocation" }),
          node("div", { class: "rc-table-wrap" }, table),
          node("p", { class: "rc-subtle", text: "Allocations are persisted and auditable. They never write back to the source." })
        )
      );
    }
    if ((detail.exceptions || []).length) {
      const list = node("div", { class: "rc-exception-list" });
      for (const exception of detail.exceptions) {
        list.append(
          node("div", { class: "rc-exception-item" },
            node("div", {},
              node("strong", { text: exception.title }),
              node("span", { class: "rc-subtle rc-block", text: `${categoryLabel(exception.category)} · ${exception.description || ""}` })
            ),
            statusPill(exception.status),
            node("button", {
              type: "button",
              class: "rc-link-btn",
              text: "Open exception",
              onclick: () => openException(exception.id),
            })
          )
        );
      }
      content.append(node("section", { class: "rc-drawer-section" }, node("h3", { text: "Exceptions" }), list));
    }
    if ((detail.previous_attempts || []).length) {
      const table = node("table", { class: "rc-table rc-table-compact" });
      table.append(node("thead", {}, node("tr", {},
        ...["Attempt", "Status", "Classification", "Confidence", "Reason", "Decision"].map((label) => node("th", { text: label }))
      )));
      const body = node("tbody");
      for (const attempt of detail.previous_attempts) {
        body.append(node("tr", {},
          node("td", { class: "rc-mono", text: attempt.id }),
          node("td", {}, pill(labelize(attempt.status), STATUS_TONE[attempt.status] || "muted")),
          node("td", { text: labelize(attempt.classification) }),
          node("td", { class: "rc-num", text: String(attempt.confidence) }),
          node("td", { class: "rc-wrap", text: attempt.explanation || "" }),
          node("td", { class: "rc-wrap", text: [attempt.decided_by, attempt.decision_reason].filter(Boolean).join(" · ") || "—" })
        ));
      }
      table.append(body);
      content.append(
        node("section", { class: "rc-drawer-section" },
          node("h3", { text: "Previous matching attempts" }),
          node("div", { class: "rc-table-wrap" }, table)
        )
      );
    }
    if ((detail.audit || []).length) {
      content.append(renderAuditList(detail.audit, "Audit trail"));
    }
    drawer.body.append(content);
  }

  function renderFieldTable(match) {
    const fields = match.matched_fields || [];
    if (!fields.length) {
      return node("p", { class: "rc-subtle", text: "No field-level evidence was stored for this row." });
    }
    const table = node("table", { class: "rc-table rc-field-table" });
    table.append(
      node("thead", {}, node("tr", {},
        ...["Field", "Source A", "Source B", "Evidence", "Result"].map((label) => node("th", { text: label }))
      ))
    );
    const body = node("tbody");
    for (const item of fields) {
      const result = item.matched === true ? pill("Agrees", "ok") : item.matched === false ? pill("Differs", "bad") : pill("Not comparable", "muted");
      const isMoney = ["Amount", "Taxable value", "IGST", "CGST", "SGST", "CESS"].includes(item.field);
      body.append(
        node("tr", {},
          node("td", { text: item.field }),
          node("td", { class: isMoney ? "rc-num" : "rc-wrap", text: isMoney ? fmtMoney(item.left, match.currency) : displayValue(item.left) }),
          node("td", { class: isMoney ? "rc-num" : "rc-wrap", text: isMoney ? fmtMoney(item.right, match.currency) : displayValue(item.right) }),
          node("td", { class: "rc-wrap rc-subtle", text: item.note || "" }),
          node("td", {}, result)
        )
      );
    }
    table.append(body);
    return node("div", { class: "rc-table-wrap" }, table);
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    return String(value);
  }

  async function decideMatch(action, match, drawer) {
    const titles = {
      accept: "Accept proposed match",
      reject: "Reject proposed match",
      unmatch: "Unmatch records",
    };
    const notes = {
      accept: "Accepting confirms this evidence. Any linked exceptions are resolved with the same reason.",
      reject: "Rejecting releases both sides back to the queues; it does not delete either record.",
      unmatch: "Unmatching releases the allocated records and creates fresh unmatched rows.",
    };
    const reason = await askReason(titles[action] || "Save decision", "Reason", notes[action], titles[action]);
    if (!reason) return;
    const result = await call("recon_decide", { action, match_id: match.id, reason });
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not save the decision.", "bad");
      return;
    }
    toast("Decision saved to the audit trail.", "ok");
    if (drawer) drawer.close();
    const run = await call("get_recon_run", match.run_id);
    if (run.ok) state.run = run;
    await loadRows();
    renderWorkbench();
  }

  async function addMatchNote(match, drawer) {
    const note = await askReason("Add investigation note", "Note", "Notes are appended to the audit trail and never overwrite prior entries.", "Save note");
    if (!note) return;
    const result = await call("recon_add_note", { match_id: match.id, note });
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not save the note.", "bad");
      return;
    }
    toast("Note added.", "ok");
    openMatch(match.id);
  }

  async function openSourceFile(fileId) {
    const result = await call("open_source_file", fileId);
    if (!result || !result.ok) toast((result && result.error) || "Could not open the source file.", "bad");
  }

  async function openSourcePage(record) {
    const result = await call("get_source_crop", record.file_id, Number(record.source_page) || 1, record.source_bbox || "");
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not load the source page.", "bad");
      return;
    }
    const src = result.data_url || result.path || "";
    const modal = createModal({ title: record.file_name || "Source page", subtitle: `${record.reference || ""} · page ${record.source_page || 1}`, wide: true });
    if (src) {
      modal.body.append(node("img", { src, alt: `Source page ${record.source_page || 1}`, class: "rc-source-image" }));
    } else {
      modal.body.append(emptyState("Source image unavailable", "The stored file could not be rendered.", []));
    }
  }

  // ---------------------------------------------------------------------
  // Manual match
  // ---------------------------------------------------------------------

  async function openManualMatch(match, presetCandidate) {
    if (!state.run) {
      toast("Open the run before making a manual match.", "bad");
      return;
    }
    let leftIds = (match.left || []).map((row) => row.row_id).filter(Boolean);
    let rightIds = (match.right || []).map((row) => row.row_id).filter(Boolean);
    let fixedLeft = leftIds.length > 0;
    let fixedRight = rightIds.length > 0;
    if (presetCandidate && presetCandidate.row_id) {
      if (match.left.length && !match.right.length) {
        rightIds = [presetCandidate.row_id];
        fixedRight = true;
      } else if (match.right.length && !match.left.length) {
        leftIds = [presetCandidate.row_id];
        fixedLeft = true;
      }
    }
    const modal = createModal({
      title: "Manual match",
      subtitle: "Explicit allocation only. Source values are preserved and the decision is audited.",
      wide: true,
    });
    const reason = node("textarea", { class: "rc-textarea", rows: "3", placeholder: "Why are these records the same transaction?" });
    const error = node("p", { class: "error", hidden: true });
    const counterpartBox = node("div", { class: "rc-manual-counterparts" });
    const allocationBox = node("div", { class: "rc-allocation-editor hidden" });
    const selectedCounterparts = new Set();
    const allocationInputs = new Map();
    let counterpartRecords = [];
    let counterpartSide = fixedLeft && !fixedRight ? "right" : fixedRight && !fixedLeft ? "left" : "";

    async function loadCounterparts() {
      if (fixedLeft && fixedRight) return;
      const side = counterpartSide;
      if (!side) return;
      const result = await call("get_recon_run_rows", state.run.id, {
        status: "unmatched",
        page_size: 500,
      });
      if (!result || !result.ok) {
        counterpartBox.append(errorPanel((result && result.error) || "Could not load unmatched records."));
        return;
      }
      const records = [];
      for (const row of result.rows || []) {
        for (const record of row[side] || []) {
          if (record.row_id) records.push({ ...record, match_id: row.id });
        }
      }
      if (presetCandidate && presetCandidate.row_id && !records.some((item) => item.row_id === presetCandidate.row_id)) {
        records.unshift(presetCandidate);
      }
      if (presetCandidate && presetCandidate.row_id) selectedCounterparts.add(presetCandidate.row_id);
      counterpartRecords = records;
      renderCounterparts(side);
    }

    function renderCounterparts(side) {
      clear(counterpartBox);
      if (!counterpartRecords.length) {
        counterpartBox.append(
          node("p", { class: "rc-callout rc-callout-warn", text: `No unmatched ${side === "left" ? "Source A" : "Source B"} records are available. Unmatch a row first or paste a row ID below.` })
        );
      } else {
        const table = node("table", { class: "rc-table rc-table-compact" });
        table.append(
          node("thead", {}, node("tr", {},
            ...["", "Reference", "Party", "Date", "Amount", "Source"].map((label) => node("th", { text: label }))
          ))
        );
        const body = node("tbody");
        for (const record of counterpartRecords.slice(0, 300)) {
          const checked = selectedCounterparts.has(record.row_id);
          const checkbox = node("input", { type: "checkbox", checked });
          checkbox.addEventListener("change", () => {
            if (checkbox.checked) selectedCounterparts.add(record.row_id);
            else selectedCounterparts.delete(record.row_id);
            renderAllocationEditor();
          });
          body.append(
            node("tr", {},
              node("td", {}, checkbox),
              node("td", { class: "rc-mono", text: record.reference || record.description || "" }),
              node("td", { class: "rc-wrap", text: record.party || "" }),
              node("td", { text: record.date || "" }),
              node("td", { class: "rc-num", text: fmtMoney(record.amount, record.currency) }),
              node("td", { class: "rc-subtle rc-wrap", text: [record.file_name, record.source_page ? `p.${record.source_page}` : ""].filter(Boolean).join(" · ") })
            )
          );
        }
        table.append(body);
        counterpartBox.append(node("div", { class: "rc-table-wrap" }, table));
      }
      counterpartBox.append(
        node("div", { class: "rc-manual-id-row" },
          node("span", { class: "rc-subtle", text: "Or paste a row ID:" }),
          ...["left", "right"].map((sideName) => {
            const input = node("input", {
              type: "number",
              class: "rc-input rc-input-small",
              placeholder: `${sideName === "left" ? "Source A" : "Source B"} row id`,
            });
            input.addEventListener("change", () => {
              const value = Number(input.value);
              if (value) {
                selectedCounterparts.add(value);
                renderAllocationEditor();
              }
            });
            return input;
          })
        )
      );
      renderAllocationEditor();
    }

    function selectedIds() {
      if (fixedLeft && fixedRight) return { left: [...leftIds], right: [...rightIds] };
      if (fixedLeft) return { left: [...leftIds], right: [...selectedCounterparts] };
      if (fixedRight) return { left: [...selectedCounterparts], right: [...rightIds] };
      return { left: [], right: [] };
    }

    function renderAllocationEditor() {
      clear(allocationBox);
      allocationInputs.clear();
      const chosen = selectedIds();
      if (chosen.left.length <= 1 && chosen.right.length <= 1) {
        allocationBox.classList.add("hidden");
        return;
      }
      allocationBox.classList.remove("hidden");
      allocationBox.append(node("h3", { text: "Allocation" }), node("p", { class: "rc-subtle", text: "Enter the amount allocated to each source A ↔ source B pair. Every selected record must appear once; the total cannot exceed the smaller side." }));
      const rows = node("div", { class: "rc-allocation-rows" });
      for (const left of chosen.left) {
        for (const right of chosen.right) {
          if (!left || !right) continue;
          const input = node("input", { type: "number", min: "0", step: "0.01", class: "rc-input rc-input-small" });
          allocationInputs.set(`${left}:${right}`, input);
          rows.append(
            node("label", { class: "rc-allocation-row" },
              node("span", { class: "rc-mono", text: `${left} → ${right}` }),
              input
            )
          );
        }
      }
      allocationBox.append(rows);
    }

    const submit = modalButton("Save manual match", "ui-btn-primary", async () => {
      error.hidden = true;
      const text = reason.value.trim();
      if (text.length < 3) {
        error.hidden = false;
        error.textContent = "Explain the evidence before saving.";
        return;
      }
      const chosen = selectedIds();
      const finalLeft = chosen.left;
      const finalRight = chosen.right;
      if (!finalLeft.length || !finalRight.length) {
        error.hidden = false;
        error.textContent = "Choose at least one record on each side.";
        return;
      }
      const allocations = [];
      for (const [key, input] of allocationInputs.entries()) {
        const amount = Number(input.value);
        if (!input.value || amount <= 0) continue;
        const [left, right] = key.split(":").map(Number);
        allocations.push({ left_id: left, right_id: right, amount });
      }
      if ((finalLeft.length > 1 || finalRight.length > 1) && allocations.length === 0) {
        error.hidden = false;
        error.textContent = "Enter an allocation for this split/aggregation.";
        return;
      }
      const result = await call("recon_decide", {
        action: "manual_match",
        run_id: state.run.id,
        left_ids: finalLeft,
        right_ids: finalRight,
        allocations,
        reason: text,
      });
      if (!result || !result.ok) {
        error.hidden = false;
        error.textContent = (result && result.error) || "Could not save the manual match.";
        return;
      }
      modal.close();
      toast("Manual match saved to the audit trail.", "ok");
      const run = await call("get_recon_run", state.run.id);
      if (run.ok) state.run = run;
      await loadRows();
      renderWorkbench();
    });
    modal.footer.append(modalButton("Cancel", "ui-btn-secondary", () => modal.close()), submit);
    modal.body.append(
      node("div", { class: "rc-manual-fixed" },
        node("span", { class: "rc-eyebrow", text: "Fixed records" }),
        node("span", { class: "rc-mono", text: [...leftIds, ...rightIds].join(", ") || "Choose a counterpart below" })
      ),
      node("p", { class: "rc-subtle", text: "Select the records that represent the same transaction. When several records are selected, an allocation is required." }),
      counterpartBox,
      allocationBox,
      field("Reason", reason),
      error
    );
    await loadCounterparts();
    reason.focus();
  }

  // ---------------------------------------------------------------------
  // Exception centre
  // ---------------------------------------------------------------------

  async function loadExceptions() {
    const container = root();
    if (!container) return;
    clear(container);
    container.append(node("p", { class: "rc-loading", text: "Loading exception queue…" }));
    const result = await call("get_recon_exceptions", state.exceptionFilters);
    if (!result || !result.ok) {
      clear(container);
      container.append(errorPanel((result && result.error) || "Could not load the exception queue."));
      return;
    }
    state.exceptions = result;
    renderExceptions();
  }

  function renderExceptions() {
    const container = root();
    if (!container) return;
    clear(container);
    if (!state.exceptions) {
      container.append(emptyState("Exception queue unavailable", "Refresh the workspace.", []));
      return;
    }
    const data = state.exceptions;
    const filters = data.filters || {};
    const bar = node("section", { class: "rc-filterbar rc-exception-filters" });
    const status = optionList(
      [
        { value: "outstanding", label: "Outstanding exceptions" },
        ...["open", "investigating", "assigned", "resolved", "approved", "timing_difference", "approved_adjustment", "reopened", "closed"].map((value) => ({ value, label: statusLabel(value) })),
      ],
      state.exceptionFilters.status,
      undefined
    );
    status.addEventListener("change", () => {
      state.exceptionFilters.status = status.value;
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const category = optionList(
      [{ value: "", label: "All categories" }, ...CATEGORY_ORDER.map((value) => ({ value, label: categoryLabel(value) }))],
      state.exceptionFilters.category,
      undefined
    );
    category.addEventListener("change", () => {
      state.exceptionFilters.category = category.value;
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const client = optionList(
      [{ value: "", label: "All clients" }, ...(filters.clients || []).map((item) => ({ value: item.id, label: item.name }))],
      state.exceptionFilters.client_id,
      undefined
    );
    client.addEventListener("change", () => {
      state.exceptionFilters.client_id = client.value;
      state.exceptionFilters.period_id = "";
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const period = optionList(
      [
        { value: "", label: "All accounting periods" },
        ...(filters.periods || [])
          .filter((item) => !state.exceptionFilters.client_id || String(item.client_id) === String(state.exceptionFilters.client_id))
          .map((item) => ({ value: item.id, label: `${item.client_name} · ${item.label}` })),
      ],
      state.exceptionFilters.period_id,
      undefined
    );
    period.addEventListener("change", () => {
      state.exceptionFilters.period_id = period.value;
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const fy = optionList(
      [{ value: "", label: "All financial years" }, ...(filters.financial_years || []).map((value) => ({ value, label: `FY ${value}` }))],
      state.exceptionFilters.financial_year,
      undefined
    );
    fy.addEventListener("change", () => {
      state.exceptionFilters.financial_year = fy.value;
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const workflow = optionList(
      [{ value: "", label: "All reconciliation types" }, ...(filters.workflows || []).map((item) => ({ value: item.id, label: item.label }))],
      state.exceptionFilters.workflow_id,
      undefined
    );
    workflow.addEventListener("change", () => {
      state.exceptionFilters.workflow_id = workflow.value;
      state.exceptionFilters.page = 1;
      loadExceptions();
    });
    const search = node("input", { type: "search", class: "rc-input", placeholder: "Search exception, client or run", value: state.exceptionFilters.search });
    search.addEventListener("input", () => {
      state.exceptionFilters.search = search.value;
      debounce(() => {
        state.exceptionFilters.page = 1;
        loadExceptions();
      }, 260);
    });
    bar.append(status, category, client, period, fy, workflow, search);
    const summary = node("div", { class: "rc-exception-summary" },
      node("div", {},
        node("p", { class: "rc-eyebrow", text: "Queue" }),
        node("h2", { text: "Exception Management Centre" })
      ),
      node("span", { class: "rc-subtle", text: `${fmtInt(data.total)} exception(s) match the filters. Outstanding is the default.` })
    );
    const table = node("table", { class: "rc-table rc-exception-table" });
    table.append(
      node("thead", {}, node("tr", {},
        ...["ID", "Category", "Exception", "Client / period / type", "Amount", "Status", "Severity", "Assigned", ""].map((label) => node("th", { text: label }))
      ))
    );
    const body = node("tbody");
    for (const item of data.exceptions || []) {
      const tr = node("tr", { class: "rc-clickable", tabindex: "0", onclick: () => openException(item.id) });
      tr.append(
        node("td", { class: "rc-mono", text: item.id }),
        node("td", { text: item.category_label || categoryLabel(item.category) }),
        node("td", { class: "rc-wrap" },
          node("strong", { text: item.title || "" }),
          node("span", { class: "rc-subtle rc-block rc-wrap", text: item.description || "" })
        ),
        node("td", {},
          node("strong", { text: item.client_name || "" }),
          node("span", { class: "rc-subtle rc-block", text: `${item.period_label || ""} · FY ${item.financial_year || ""}` }),
          node("span", { class: "rc-subtle rc-block rc-wrap", text: item.workflow_label || "" })
        ),
        node("td", { class: "rc-num", text: fmtMoney(item.amount, item.currency) }),
        node("td", {}, statusPill(item.status)),
        node("td", {}, pill(labelize(item.severity), item.severity === "high" ? "bad" : item.severity === "medium" ? "warn" : "muted")),
        node("td", { class: "rc-wrap", text: item.assigned_to || "Unassigned" }),
        node("td", {}, runActionButton("Investigate", () => openException(item.id)))
      );
      body.append(tr);
    }
    table.append(body);
    const pagination = node("div", { class: "rc-pagination" },
      node("span", { class: "rc-subtle", text: `Page ${data.page} of ${data.pages}` }),
      node("div", { class: "rc-pagination-actions" },
        node("button", {
          type: "button", class: "rc-link-btn", text: "Previous", disabled: data.page <= 1,
          onclick: () => {
            state.exceptionFilters.page = Math.max(1, data.page - 1);
            loadExceptions();
          },
        }),
        node("button", {
          type: "button", class: "rc-link-btn", text: "Next", disabled: data.page >= data.pages,
          onclick: () => {
            state.exceptionFilters.page = Math.min(data.pages, data.page + 1);
            loadExceptions();
          },
        })
      )
    );
    container.append(
      summary,
      bar,
      node("section", { class: "rc-panel" },
        data.exceptions && data.exceptions.length
          ? node("div", { class: "rc-table-wrap rc-table-tall" }, table)
          : node("div", { class: "rc-quiet-state" },
              node("strong", { text: "No exceptions match these filters" }),
              node("p", { text: "Try Outstanding or clear the filters. Every run keeps its exception history." })
            )
      ),
      pagination
    );
  }

  async function openException(exceptionId) {
    const result = await call("get_recon_exception", exceptionId);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not open this exception.", "bad");
      return;
    }
    renderExceptionDrawer(result);
  }

  function renderExceptionDrawer(detail) {
    const exception = detail.exception;
    const run = detail.run || {};
    const modal = createModal({
      title: exception.title,
      subtitle: `${exception.category_label || categoryLabel(exception.category)} · run ${String(run.run_uuid || "").slice(0, 8)}`,
      drawer: true,
      wide: true,
    });
    const actions = node("div", { class: "rc-drawer-actions" });
    const quick = [
      ["investigating", "Start investigating"],
      ["resolved", "Resolve"],
      ["timing_difference", "Mark timing difference"],
      ["approved_adjustment", "Approved adjustment"],
      ["reopened", "Reopen"],
    ];
    for (const [status, label] of quick) {
      if (status === "reopened" && !["resolved", "approved", "timing_difference", "approved_adjustment", "closed"].includes(exception.status)) continue;
      if (status === "resolved" && ["resolved", "approved", "timing_difference", "approved_adjustment", "closed"].includes(exception.status)) continue;
      actions.append(
        modalButton(label, status === "resolved" ? "ui-btn-primary" : "ui-btn-secondary", async () => {
          const reason = await askReason(label, "Reason", "The status change, your account and timestamp are recorded in the audit trail.", label);
          if (!reason) return;
          const response = await call("recon_update_exception", {
            id: exception.id,
            status,
            reason,
          });
          if (!response || !response.ok) {
            toast((response && response.error) || "Could not update the exception.", "bad");
            return;
          }
          toast("Exception updated.", "ok");
          modal.close();
          openException(exception.id);
        })
      );
    }
    actions.append(modalButton("Open linked row", "ui-btn-secondary", () => {
      if (exception.match_id) {
        modal.close();
        openMatch(exception.match_id);
      }
    }));
    const queue = (state.exceptions && state.exceptions.exceptions) || [];
    const queueIndex = queue.findIndex((item) => item.id === exception.id);
    if (queueIndex > 0) {
      actions.append(modalButton("Previous exception", "ui-btn-secondary", () => {
        modal.close();
        openException(queue[queueIndex - 1].id);
      }));
    }
    if (queueIndex >= 0 && queueIndex < queue.length - 1) {
      actions.append(modalButton("Next exception", "ui-btn-secondary", () => {
        modal.close();
        openException(queue[queueIndex + 1].id);
      }));
    }
    const statusForm = node("div", { class: "rc-inline-form" });
    const statusSelect = optionList(
      ["open", "investigating", "assigned", "resolved", "approved", "timing_difference", "approved_adjustment", "reopened", "closed"].map((value) => ({ value, label: statusLabel(value) })),
      exception.status,
      undefined
    );
    const assignee = node("input", { class: "rc-input", placeholder: "Reviewer email or name", value: exception.assigned_to || "" });
    const reason = node("textarea", { class: "rc-textarea", rows: "3", placeholder: "Reason for this update" });
    const update = modalButton("Save update", "ui-btn-primary", async () => {
      const response = await call("recon_update_exception", {
        id: exception.id,
        status: statusSelect.value,
        assigned_to: assignee.value,
        reason: reason.value,
      });
      if (!response || !response.ok) {
        toast((response && response.error) || "Could not update the exception.", "bad");
        return;
      }
      toast("Exception updated.", "ok");
      modal.close();
      openException(exception.id);
      if (state.tab === "exceptions") loadExceptions();
    });
    statusForm.append(field("Status", statusSelect), field("Assign to", assignee), field("Reason", reason), node("div", { class: "rc-inline-form-actions" }, update));
    const note = node("textarea", { class: "rc-textarea", rows: "3", placeholder: "Add an investigation note" });
    const noteButton = modalButton("Add note", "ui-btn-secondary", async () => {
      const text = note.value.trim();
      if (text.length < 2) {
        toast("Write a note first.", "bad");
        return;
      }
      const response = await call("recon_add_note", { exception_id: exception.id, note: text });
      if (!response || !response.ok) {
        toast((response && response.error) || "Could not save the note.", "bad");
        return;
      }
      toast("Note added to the audit trail.", "ok");
      modal.close();
      openException(exception.id);
    });
    const evidenceLabel = node("input", { class: "rc-input", placeholder: "Evidence label (e.g. supplier confirmation)" });
    const evidenceRef = node("input", { class: "rc-input", placeholder: "Reference, filename or note" });
    const evidenceButton = modalButton("Attach evidence reference", "ui-btn-secondary", async () => {
      if (!evidenceLabel.value.trim() && !evidenceRef.value.trim()) {
        toast("Add a label or reference first.", "bad");
        return;
      }
      const response = await call("recon_update_exception", {
        id: exception.id,
        evidence: [{
          label: evidenceLabel.value.trim(),
          reference: evidenceRef.value.trim(),
          added_at: new Date().toISOString(),
        }],
      });
      if (!response || !response.ok) {
        toast((response && response.error) || "Could not attach evidence.", "bad");
        return;
      }
      toast("Evidence reference attached.", "ok");
      modal.close();
      openException(exception.id);
    });
    const content = node("div", { class: "rc-drawer-content" });
    content.append(
      node("div", { class: "rc-drawer-summary" },
        statusPill(exception.status),
        pill(labelize(exception.severity), exception.severity === "high" ? "bad" : "warn"),
        node("span", { class: "rc-subtle", text: `${fmtMoney(exception.amount, exception.currency)} · ${exception.assigned_to || "Unassigned"}` })
      ),
      node("p", { class: "rc-explanation", text: exception.description || "" }),
      actions,
      node("div", { class: "rc-drawer-metrics" },
        metricCard("Client", run.client_name || "—", run.period_label || ""),
        metricCard("Workflow", run.workflow_label || "—", `Run ${String(run.run_uuid || "").slice(0, 8)}`),
        metricCard("Amount", fmtMoney(exception.amount, exception.currency), exception.currency || ""),
        metricCard("Created", fmtDate(exception.created_at), `Resolved ${exception.resolved_at ? fmtDate(exception.resolved_at) : "—"}`)
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Change status or assign" }),
        statusForm
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Investigation note" }),
        note,
        node("div", { class: "rc-inline-form-actions" }, noteButton)
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Supporting evidence" }),
        (exception.evidence || []).length
          ? node("ul", { class: "rc-evidence-list" }, ...exception.evidence.map((item) => node("li", { text: [item.label, item.reference, item.added_at ? fmtDate(item.added_at) : ""].filter(Boolean).join(" · ") })))
          : node("p", { class: "rc-subtle", text: "No evidence references attached yet. Evidence references do not modify the source file." }),
        node("div", { class: "rc-evidence-form" }, evidenceLabel, evidenceRef, evidenceButton)
      ),
      node("section", { class: "rc-drawer-section" },
        node("h3", { text: "Source references" }),
        (exception.source_refs || []).length
          ? node("div", { class: "rc-source-refs" }, ...exception.source_refs.map((ref) => node("div", { class: "rc-source-ref" },
              node("strong", { class: "rc-mono", text: ref.reference || ref.file_name || "Source" }),
              node("span", { class: "rc-subtle rc-block", text: [ref.file_name, ref.page ? `page ${ref.page}` : "", ref.party, ref.amount ? fmtMoney(ref.amount) : ""].filter(Boolean).join(" · ") })
            )))
          : node("p", { class: "rc-subtle", text: "No source reference was recorded." })
      ),
      (detail.audit || []).length ? renderAuditList(detail.audit, "Audit trail") : node("span", { class: "hidden" })
    );
    modal.body.append(content);
  }

  function renderAuditList(events, title) {
    const list = node("div", { class: "rc-audit-list" });
    for (const event of events || []) {
      list.append(
        node("div", { class: "rc-audit-item" },
          node("div", { class: "rc-audit-head" },
            node("strong", { text: labelize(event.action) }),
            node("span", { class: "rc-subtle", text: `${event.actor || "local"} · ${fmtDate(event.created_at)}` })
          ),
          node("p", { text: event.reason || "" }),
          event.previous_status || event.new_status
            ? node("span", { class: "rc-subtle", text: `${event.previous_status ? statusLabel(event.previous_status) : "—"} → ${event.new_status ? statusLabel(event.new_status) : "—"}` })
            : null
        )
      );
    }
    return node("section", { class: "rc-drawer-section" }, node("h3", { text: title || "Audit trail" }), list);
  }

  // ---------------------------------------------------------------------
  // History
  // ---------------------------------------------------------------------

  async function loadHistory() {
    const container = root();
    if (!container) return;
    clear(container);
    container.append(node("p", { class: "rc-loading", text: "Loading reconciliation history…" }));
    const result = await call("list_recon_runs", state.historyFilters);
    if (!result || !result.ok) {
      clear(container);
      container.append(errorPanel((result && result.error) || "Could not load run history."));
      return;
    }
    state.history = result;
    renderHistory();
  }

  function renderHistory() {
    const container = root();
    if (!container) return;
    clear(container);
    const data = state.history;
    if (!data) {
      container.append(emptyState("History unavailable", "Refresh the workspace.", []));
      return;
    }
    const filters = state.control?.filters || {};
    const bar = node("section", { class: "rc-filterbar" });
    const runStatus = optionList(
      [{ value: "", label: "All run statuses" }, ...["queued", "running", "completed", "failed", "cancelled"].map((value) => ({ value, label: statusLabel(value) }))],
      state.historyFilters.run_status,
      undefined
    );
    runStatus.addEventListener("change", () => {
      state.historyFilters.run_status = runStatus.value;
      state.historyFilters.page = 1;
      loadHistory();
    });
    const client = optionList(
      [{ value: "", label: "All clients" }, ...(filters.clients || []).map((item) => ({ value: item.id, label: item.name }))],
      state.historyFilters.client_id,
      undefined
    );
    client.addEventListener("change", () => {
      state.historyFilters.client_id = client.value;
      state.historyFilters.page = 1;
      loadHistory();
    });
    const workflow = optionList(
      [{ value: "", label: "All reconciliation types" }, ...(filters.workflows || []).map((item) => ({ value: item.id, label: item.label }))],
      state.historyFilters.workflow_id,
      undefined
    );
    workflow.addEventListener("change", () => {
      state.historyFilters.workflow_id = workflow.value;
      state.historyFilters.page = 1;
      loadHistory();
    });
    const search = node("input", { type: "search", class: "rc-input", placeholder: "Search client, period, workflow or run ID", value: state.historyFilters.search });
    search.addEventListener("input", () => {
      state.historyFilters.search = search.value;
      debounce(() => {
        state.historyFilters.page = 1;
        loadHistory();
      }, 260);
    });
    bar.append(runStatus, client, workflow, search);
    const compareBar = node("div", { class: "rc-compare-bar" },
      node("div", {},
        node("p", { class: "rc-eyebrow", text: "Run comparison" }),
        node("span", { class: "rc-subtle", text: `${state.selectedRuns.length} of 2 runs selected. Compare the same period and workflow.` })
      ),
      node("div", { class: "rc-compare-actions" },
        node("button", {
          type: "button", class: "rc-link-btn", text: "Clear",
          onclick: () => { state.selectedRuns = []; loadHistory(); },
        }),
        node("button", {
          type: "button", class: "ui-btn ui-btn-primary", text: "Compare selected",
          disabled: state.selectedRuns.length !== 2,
          onclick: () => compareSelectedRuns(),
        })
      )
    );
    const table = node("table", { class: "rc-table" });
    table.append(
      node("thead", {}, node("tr", {},
        ...["", "Run", "Client / period", "Type", "Status", "Rules", "Records", "Matched", "Unmatched", "Exceptions", "Created", ""].map((label) => node("th", { text: label }))
      ))
    );
    const body = node("tbody");
    for (const run of data.runs || []) {
      const totals = run.totals || {};
      const checked = state.selectedRuns.includes(run.id);
      const checkbox = node("input", { type: "checkbox", checked, onclick: (event) => event.stopPropagation() });
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          if (!state.selectedRuns.includes(run.id)) state.selectedRuns.push(run.id);
          if (state.selectedRuns.length > 2) state.selectedRuns.shift();
        } else {
          state.selectedRuns = state.selectedRuns.filter((id) => id !== run.id);
        }
        loadHistory();
      });
      const tr = node("tr", { class: "rc-clickable", onclick: () => openRun(run.id) });
      tr.append(
        node("td", {}, checkbox),
        node("td", {},
          node("span", { class: "rc-mono", text: String(run.run_uuid || "").slice(0, 8) }),
          run.parent_run_id ? node("span", { class: "rc-subtle rc-block", text: `re-run of ${run.parent_run_id}` }) : null
        ),
        node("td", {},
          node("strong", { text: run.client_name }),
          node("span", { class: "rc-subtle rc-block", text: `${run.period_label} · FY ${run.financial_year}` })
        ),
        node("td", { class: "rc-wrap", text: run.workflow_label }),
        node("td", {}, runStatusPill(run)),
        node("td", { text: `v${run.ruleset_version || 1}` }),
        node("td", { class: "rc-num", text: fmtInt(totals.records_processed) }),
        node("td", { class: "rc-num", text: fmtInt(totals.matched_records) }),
        node("td", { class: "rc-num", text: fmtInt(totals.unmatched_records) }),
        node("td", { class: "rc-num", text: fmtInt(totals.open_exceptions) }),
        node("td", { text: fmtDate(run.created_at) }),
        node("td", { class: "rc-actions" },
          runActionButton("Open", () => openRun(run.id)),
          runActionButton("Audit", () => openRunAudit(run.id)),
          runActionButton("Export", () => exportRun(run.id))
        )
      );
      body.append(tr);
    }
    table.append(body);
    const pagination = node("div", { class: "rc-pagination" },
      node("span", { class: "rc-subtle", text: `${fmtInt(data.total)} run(s) · page ${data.page} of ${data.pages}` }),
      node("div", { class: "rc-pagination-actions" },
        node("button", {
          type: "button", class: "rc-link-btn", text: "Previous", disabled: data.page <= 1,
          onclick: () => { state.historyFilters.page = Math.max(1, data.page - 1); loadHistory(); },
        }),
        node("button", {
          type: "button", class: "rc-link-btn", text: "Next", disabled: data.page >= data.pages,
          onclick: () => { state.historyFilters.page = Math.min(data.pages, data.page + 1); loadHistory(); },
        })
      )
    );
    container.append(
      node("div", { class: "rc-exception-summary" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Persisted history" }),
          node("h2", { text: "Run history and comparison" })
        ),
        node("span", { class: "rc-subtle", text: "Previous runs are never overwritten. Rules and source evidence are snapshotted per run." })
      ),
      bar,
      compareBar,
      node("section", { class: "rc-panel" },
        (data.runs || []).length
          ? node("div", { class: "rc-table-wrap rc-table-tall" }, table)
          : node("div", { class: "rc-quiet-state" }, node("strong", { text: "No runs match these filters" }), node("p", { text: "Clear filters or start a reconciliation." }))
      ),
      pagination
    );
  }

  async function compareSelectedRuns() {
    if (state.selectedRuns.length !== 2) return;
    const result = await call("compare_recon_runs", state.selectedRuns[0], state.selectedRuns[1]);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not compare these runs.", "bad");
      return;
    }
    const modal = createModal({ title: "Run comparison", subtitle: `${String(result.run_a.run_uuid).slice(0, 8)} → ${String(result.run_b.run_uuid).slice(0, 8)}`, wide: true });
    const delta = result.totals_delta || {};
    const cards = node("div", { class: "rc-drawer-metrics" },
      metricCard("Added positions", fmtInt(result.added), "Records newly matched or present", "ok"),
      metricCard("Removed positions", fmtInt(result.removed), "Records no longer present", "bad"),
      metricCard("Changed positions", fmtInt(result.changed), "Status or classification changed", "warn"),
      metricCard("Records delta", fmtInt(delta.records_processed), `Matched delta ${fmtInt(delta.matched_records)}`)
    );
    const table = node("table", { class: "rc-table rc-table-compact" });
    table.append(node("thead", {}, node("tr", {},
      ...["Record", "Change", "Before", "After"].map((label) => node("th", { text: label }))
    )));
    const body = node("tbody");
    for (const change of result.changes || []) {
      body.append(node("tr", {},
        node("td", { class: "rc-mono", text: change.key }),
        node("td", {}, pill(labelize(change.change), change.change === "added" ? "ok" : change.change === "removed" ? "bad" : "warn")),
        node("td", { class: "rc-wrap", text: change.before ? `${labelize(change.before.status)} · ${change.before.classification}` : "—" }),
        node("td", { class: "rc-wrap", text: change.after ? `${labelize(change.after.status)} · ${change.after.classification}` : "—" })
      ));
    }
    table.append(body);
    modal.body.append(cards);
    if ((result.changes || []).length) {
      modal.body.append(node("div", { class: "rc-table-wrap rc-table-tall" }, table));
    } else {
      modal.body.append(node("p", { class: "rc-subtle", text: "No record-level changes between these runs." }));
    }
    modal.footer.append(modalButton("Close", "ui-btn-secondary", () => modal.close()));
  }

  async function openRunAudit(runId) {
    const result = await call("get_recon_audit", runId);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not load the audit trail.", "bad");
      return;
    }
    const modal = createModal({ title: "Audit trail", subtitle: `Run ${String(result.run.run_uuid).slice(0, 8)} · ${result.run.client_name} · ${result.run.period_label}`, wide: true });
    modal.body.append(renderAuditList(result.events, "Complete audit history"));
    modal.footer.append(modalButton("Close", "ui-btn-secondary", () => modal.close()));
  }

  // ---------------------------------------------------------------------
  // Rules
  // ---------------------------------------------------------------------

  async function loadRules() {
    const container = root();
    if (!container) return;
    clear(container);
    container.append(node("p", { class: "rc-loading", text: "Loading reconciliation rules…" }));
    const result = await call("get_recon_rules", "");
    if (!result || !result.ok) {
      clear(container);
      container.append(errorPanel((result && result.error) || "Could not load reconciliation rules."));
      return;
    }
    state.rules = result;
    renderRules();
  }

  function renderRules() {
    const container = root();
    if (!container) return;
    clear(container);
    if (!state.rules) {
      container.append(emptyState("Rules unavailable", "Refresh the workspace.", []));
      return;
    }
    const defaults = state.rules.defaults || {};
    const workflows = state.rules.workflows || [];
    const rulesets = state.rules.rulesets || [];
    const selected = state.rulesDraft || null;
    const editor = node("section", { class: "rc-panel rc-rule-editor" });
    editor.append(
      node("div", { class: "rc-panel-head" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Configuration" }),
          node("h2", { text: selected ? `${selected.name} · v${selected.version}` : "Create a rule set" })
        ),
        node("button", { type: "button", class: "rc-link-btn", text: "Use built-in defaults", onclick: () => { state.rulesDraft = null; renderRules(); } })
      )
    );
    const name = node("input", { class: "rc-input", value: selected ? selected.name : "Firm reconciliation rules" });
    const workflow = optionList(
      [{ value: "*", label: "All workflows" }, ...workflows.map((item) => ({ value: item.id, label: item.label }))],
      selected ? selected.workflow_id : "*",
      undefined
    );
    const config = selected ? selected.config : defaults;
    const tolerance = node("input", { class: "rc-input", type: "number", min: "0", step: "0.01", value: config.amount_tolerance });
    const dateTolerance = node("input", { class: "rc-input", type: "number", min: "0", step: "1", value: config.date_tolerance_days });
    const bankDate = node("input", { class: "rc-input", type: "number", min: "0", step: "1", value: config.bank_date_tolerance_days });
    const fuzzyDate = node("input", { class: "rc-input", type: "number", min: "0", step: "1", value: config.fuzzy_date_tolerance_days });
    const reviewThreshold = node("input", { class: "rc-input", type: "number", min: "0", max: "100", value: config.review_threshold });
    const autoThreshold = node("input", { class: "rc-input", type: "number", min: "0", max: "100", value: config.auto_accept_threshold });
    const maxAllocation = node("input", { class: "rc-input", type: "number", min: "2", max: "8", value: config.max_allocation_items });
    const toggle = (key, labelText) => {
      const input = node("input", { type: "checkbox", checked: Boolean(config[key]) });
      return { key, input, node: node("label", { class: "rc-toggle" }, input, node("span", { text: labelText })) };
    };
    const toggles = [
      toggle("allow_one_to_many", "Allowed: one-to-many allocation"),
      toggle("allow_many_to_one", "Allowed: many-to-one aggregation"),
      toggle("allow_partial", "Detect partial settlements"),
      toggle("detect_duplicates", "Detect duplicates"),
      toggle("detect_reversals", "Detect reversal candidates"),
      toggle("normalize_references", "Normalise references"),
      toggle("gstin_validation", "Validate GSTIN structure"),
    ];
    const weights = config.weights || defaults.weights || {};
    const weightInputs = {};
    const weightGrid = node("div", { class: "rc-weight-grid" });
    for (const key of ["reference", "gstin", "amount", "date", "party", "tax"]) {
      weightInputs[key] = node("input", { class: "rc-input", type: "number", min: "0", step: "1", value: weights[key] });
      weightGrid.append(field(labelize(key), weightInputs[key]));
    }
    const error = node("p", { class: "error", hidden: true });
    const save = modalButton("Save new version", "ui-btn-primary", async () => {
      error.hidden = true;
      const payload = {
        name: name.value.trim(),
        workflow_id: workflow.value,
        client_id: selected ? selected.client_id : null,
        is_default: true,
        config: {
          amount_tolerance: Number(tolerance.value),
          date_tolerance_days: Number(dateTolerance.value),
          bank_date_tolerance_days: Number(bankDate.value),
          fuzzy_date_tolerance_days: Number(fuzzyDate.value),
          review_threshold: Number(reviewThreshold.value),
          auto_accept_threshold: Number(autoThreshold.value),
          max_allocation_items: Number(maxAllocation.value),
          weights: Object.fromEntries(Object.entries(weightInputs).map(([key, input]) => [key, Number(input.value)])),
          ...Object.fromEntries(toggles.map((item) => [item.key, item.input.checked])),
        },
      };
      if (!payload.name) {
        error.hidden = false;
        error.textContent = "Give the rule set a name.";
        return;
      }
      const result = await call("save_recon_rules", payload);
      if (!result || !result.ok) {
        error.hidden = false;
        error.textContent = (result && result.error) || "Could not save the rule set.";
        return;
      }
      toast("Rule set saved as a new version.", "ok");
      state.rulesDraft = result.ruleset;
      await loadRules();
    });
    editor.append(
      node("div", { class: "rc-rule-form" },
        field("Rule set name", name),
        field("Applies to", workflow),
        field("Amount tolerance (₹)", tolerance, "Absolute difference allowed before an amount is flagged."),
        field("Date tolerance (days)", dateTolerance, "Used for invoice and register dates."),
        field("Bank reference window (days)", bankDate, "Bank/UTR/cheque reference matching window."),
        field("Fuzzy bank window (days)", fuzzyDate, "Amount + party + nearby date candidates only; never auto-confirmed."),
        field("Review threshold", reviewThreshold, "Minimum evidence score for a proposed match."),
        field("Auto-confirm threshold", autoThreshold, "Exact/strong evidence at or above this score can be matched automatically."),
        field("Maximum allocation items", maxAllocation, "Maximum records combined in one split/aggregation proposal."),
        node("div", { class: "rc-toggle-grid" }, ...toggles.map((item) => item.node)),
        node("div", { class: "rc-rule-weights" }, node("h3", { text: "Evidence weights" }), node("p", { class: "rc-subtle", text: "Scores are computed from actual matching fields; these weights control their relative importance." }), weightGrid),
        error,
        node("div", { class: "rc-inline-form-actions" }, save)
      )
    );
    const list = node("section", { class: "rc-panel rc-rule-list-panel" });
    list.append(
      node("div", { class: "rc-panel-head" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Versions" }),
          node("h2", { text: "Saved rule sets" })
        )
      )
    );
    if (!rulesets.length) {
      list.append(node("p", { class: "rc-subtle", text: "No saved rule sets yet. The built-in defaults are used and snapshotted for every run." }));
    } else {
      const rows = node("div", { class: "rc-ruleset-list" });
      for (const item of rulesets) {
        rows.append(
          node("div", { class: "rc-ruleset-item" },
            node("div", { class: "rc-ruleset-main" },
              node("strong", { text: item.name }),
              node("span", { class: "rc-subtle rc-block rc-wrap", text: item.notes || "" }),
              node("span", { class: "rc-subtle rc-block rc-wrap", text: item.workflow_id === "*" ? "All workflows" : (workflows.find((flow) => flow.id === item.workflow_id)?.label || item.workflow_id) })
            ),
            node("div", { class: "rc-ruleset-meta" },
              pill(`v${item.version}`, "muted"),
              item.is_default ? pill("Default", "ok") : pill("Historical", "muted"),
              runActionButton("Edit as new", () => {
                state.rulesDraft = item;
                renderRules();
              })
            )
          )
        );
      }
      list.append(rows);
    }
    list.append(
      node("div", { class: "rc-defaults-note" },
        node("h3", { text: "Built-in safe defaults" }),
        node("ul", { class: "rc-rule-list" }, ...(state.rules.default_summary || []).map((item) => node("li", { text: item })))
      )
    );
    container.append(
      node("div", { class: "rc-exception-summary" },
        node("div", {},
          node("p", { class: "rc-eyebrow", text: "Explainable matching" }),
          node("h2", { text: "Reconciliation rules and configuration" })
        ),
        node("span", { class: "rc-subtle", text: "Saving creates a new version. Every run keeps the exact rules snapshot it used." })
      ),
      node("div", { class: "rc-rules-layout" }, editor, list)
    );
  }

  // ---------------------------------------------------------------------
  // Export / rerun
  // ---------------------------------------------------------------------

  async function exportRun(runId) {
    toast("Building the Excel evidence pack and PDF summary…", "ok");
    const result = await call("export_recon_run", runId);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not export this run.", "bad");
      return;
    }
    const exported = result.export || {};
    const modal = createModal({ title: "Reconciliation export created", subtitle: "The export contains the persisted run snapshot and source references." });
    modal.body.append(
      node("div", { class: "rc-export-result" },
        node("p", {}, node("strong", { text: "Excel pack" }), node("span", { class: "rc-subtle rc-block rc-wrap", text: exported.xlsx || "" })),
        node("p", {}, node("strong", { text: "PDF summary" }), node("span", { class: "rc-subtle rc-block rc-wrap", text: exported.pdf || "" })),
        node("p", {}, node("strong", { text: "Folder" }), node("span", { class: "rc-subtle rc-block rc-wrap", text: exported.folder || "" }))
      )
    );
    modal.footer.append(
      modalButton("Open Excel", "ui-btn-primary", async () => {
        const opened = await call("open_recon_export", runId);
        if (!opened || !opened.ok) toast((opened && opened.error) || "Could not open the export.", "bad");
      }),
      modalButton("Close", "ui-btn-secondary", () => modal.close())
    );
  }

  async function rerun(runId) {
    const result = await call("rerun_reconciliation", runId);
    if (!result || !result.ok) {
      toast((result && result.error) || "Could not re-run this reconciliation.", "bad");
      return;
    }
    toast("New reconciliation run started. The previous run is preserved.", "ok");
    const modal = createModal({ title: "Re-run started", subtitle: "A new run is queued with the same rules snapshot. The original history remains intact." });
    const progress = node("div", { class: "rc-progress" }, node("div", { class: "rc-progress-bar" }));
    const text = node("p", { class: "rc-progress-text", text: "Queued…" });
    modal.body.append(progress, text);
    const timer = setInterval(async () => {
      const run = await call("get_recon_run", result.id);
      if (!run || !run.ok) return;
      progress.firstChild.style.width = `${Math.max(2, Number(run.progress || 0))}%`;
      text.textContent = `${statusLabel(run.status)} · ${run.progress || 0}%`;
      if (run.status === "completed") {
        clearInterval(timer);
        modal.close();
        toast("Re-run completed.", "ok");
        openRun(result.id);
      } else if (run.status === "failed") {
        clearInterval(timer);
        text.textContent = run.error_message || "The re-run failed.";
      }
    }, 900);
  }

  // ---------------------------------------------------------------------
  // Wire up
  // ---------------------------------------------------------------------

  function wire() {
    document.getElementById("recon-tabs")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-rc-tab]");
      if (!button) return;
      switchTab(button.dataset.rcTab);
    });
    document.getElementById("recon-refresh")?.addEventListener("click", () => refresh());
    document.getElementById("recon-run-button")?.addEventListener("click", openRunModal);
    document.getElementById("recon-export-button")?.addEventListener("click", () => {
      if (state.run) {
        exportRun(state.run.id);
        return;
      }
      const latest = (state.control?.recent_runs || [])[0];
      if (latest) exportRun(latest.id);
      else toast("Open or start a reconciliation run before exporting.", "bad");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  window.CAReconCentre = {
    open,
    refresh,
    openRun,
    openMatch,
    openException,
    openRunModal,
    switchTab,
    exportRun,
  };
})();
