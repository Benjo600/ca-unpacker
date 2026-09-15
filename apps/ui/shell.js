const CLIENTS = [
  { id: "sree", name: "Sree Traders", gstin: "29ABCDE1234F1Z5", period: "Aug 2026", files: 8, state: "held", stateLabel: "2 to review", src: "D:\\Clients\\Sree_Traders\\Aug2026" },
  { id: "anand", name: "Anand Textiles Pvt Ltd", gstin: "29AAACA1122B1ZQ", period: "Aug 2026", files: 6, state: "running", stateLabel: "Parsing", src: "D:\\Clients\\Anand_Textiles\\Aug2026" },
  { id: "kaveri", name: "Kaveri Agro Foods", gstin: "29AAGCK7788C1Z3", period: "Aug 2026", files: 7, state: "held", stateLabel: "4 to review", src: "D:\\Clients\\Kaveri_Agro\\Aug2026" },
  { id: "deccan", name: "Deccan Hardware & Tools", gstin: "29AADCD3344E1ZP", period: "Aug 2026", files: 5, state: "ready", stateLabel: "Ready", src: "D:\\Clients\\Deccan_Hardware\\Aug2026" },
  { id: "nova", name: "Nova Pharma Distributors", gstin: "29AABCN9911F1ZR", period: "Aug 2026", files: 4, state: "failed", stateLabel: "Parse failed", src: "D:\\Clients\\Nova_Pharma\\Aug2026" },
  { id: "lakshmi", name: "Sri Lakshmi Jewellers", gstin: "29AAJCS5566G1ZT", period: "Aug 2026", files: 3, state: "ready", stateLabel: "Ready", src: "D:\\Clients\\Lakshmi_Jewellers\\Aug2026" },
  { id: "vaishnavi", name: "Vaishnavi Engineers", gstin: "29AAFCV2233H1ZM", period: "Aug 2026", files: 6, state: "ready", stateLabel: "Ready", src: "D:\\Clients\\Vaishnavi_Engg\\Aug2026" },
  { id: "metro", name: "Metro Auto Spares", gstin: "29AAGCM6677J1ZK", period: "Aug 2026", files: 4, state: "held", stateLabel: "1 to review", src: "D:\\Clients\\Metro_Auto\\Aug2026" },
];

const FILES = [
  { name: "HDFC_Bank_Aug2026.pdf", kind: "Bank stmt", icon: "i-bank", rows: "412", period: "01–31 Aug", conf: "99.2%", state: "ok", stateLabel: "Parsed" },
  { name: "ICICI_OD_Aug2026.pdf", kind: "Bank stmt", icon: "i-bank", rows: "208", period: "01–31 Aug", conf: "98.7%", state: "ok", stateLabel: "Parsed" },
  { name: "Sales_Register_Aug2026.xlsx", kind: "Sales reg", icon: "i-sheet", rows: "1,204", period: "01–31 Aug", conf: "99.8%", state: "ok", stateLabel: "Parsed" },
  { name: "Purchase_Register_Aug2026.xlsx", kind: "Purchase reg", icon: "i-sheet", rows: "986", period: "01–31 Aug", conf: "99.6%", state: "ok", stateLabel: "Parsed" },
  { name: "GSTR2B_Aug2026.json", kind: "GSTR-2B", icon: "i-braces", rows: "312", period: "Jul–Aug", conf: "100%", state: "ok", stateLabel: "Parsed" },
  { name: "Invoice_Scans_Box1.zip", kind: "Invoices", icon: "i-archive", rows: "64", period: "01–18 Aug", conf: "87.4%", state: "warn", stateLabel: "6 to review" },
  { name: "Cash_Vouchers_Aug2026.xlsx", kind: "Vouchers", icon: "i-sheet", rows: "143", period: "01–31 Aug", conf: "91.0%", state: "warn", stateLabel: "Held" },
  { name: "TDS_Challans_Aug2026.pdf", kind: "TDS", icon: "i-doc", rows: "6", period: "07 Aug", conf: "99.1%", state: "ok", stateLabel: "Parsed" },
];

const RECON = [
  { supplier: "Anand Textiles", gstin: "29AAACA1122B1ZQ", inv: "AT/2026/841", a: "1,18,000.00", b: "1,18,000.00", diff: "0.00", state: "ok", action: "Matched" },
  { supplier: "Ganesh Packaging", gstin: "29AAGCG4545K1Z9", inv: "GP-2291", a: "42,600.00", b: "42,600.00", diff: "0.00", state: "ok", action: "Matched" },
  { supplier: "Shakti Steels", gstin: "29AAJPS1120L1ZD", inv: "SS/778", a: "0.00", b: "18,240.00", diff: "18,240.00", state: "warn", action: "In books only" },
  { supplier: "Bharath Logistics", gstin: "29AABCB3344M1ZF", inv: "BL-90114", a: "6,780.00", b: "0.00", diff: "6,780.00", state: "warn", action: "In 2B only" },
  { supplier: "Sunrise Chemicals", gstin: "29AACCS8899N1ZH", inv: "SC/117", a: "76,300.00", b: "76,300.00", diff: "0.00", state: "ok", action: "Matched" },
  { supplier: "Royal Papers", gstin: "29AAECR5566P1ZJ", inv: "RP-3390", a: "23,140.00", b: "23,100.00", diff: "40.00", state: "warn", action: "Rate mismatch" },
];

const SRC = {
  bank: {
    page: "page 3 of 11",
    line: 5,
    value: "1,24,500.00",
    sum: "9f2a41c8",
    rule: "hdfc-current-v3",
    lines: [
      "HDFC Bank — Statement of Account",
      "A/C 50100XXXXXX741 · MG Road",
      "Period 01-08 to 31-08-2026",
      "Date     Particulars    Amount",
      "01-08-26 UPI/408112 1,24,500.00",
      "01-08-26 UPI/408119        8,240.00",
      "03-08-26 NEFT KAVERI     2,86,400.00",
      "04-08-26 GANESH PACKAG     42,600.00",
      "07-08-26 ANAND TEXTILES    88,120.00",
      "11-08-26 CHQ 004512        42,000.00",
      "13-08-26 SALARY DISB     2,10,000.00",
      "16-08-26 LAKSHMI JEWEL      96,300.00",
      "19-08-26 METRO AUTO      1,05,750.00",
      "24-08-26 BHARATH LOGI      15,400.00",
      "27-08-26 GST CHALLAN       36,900.00",
      "31-08-26 CLOSING BAL    4,71,330.00",
    ],
  },
  sheet: {
    page: "sheet 1 of 1",
    line: 4,
    value: "1,24,500.00",
    sum: "4c81be02",
    rule: "generic-xlsx-v2",
    lines: [
      "Sales_Register (9 columns)",
      "Header detected at row 1",
      "Row Party           Invoice",
      "  2 Sree Enterprises 1,24,500.00",
      "  3 Kaveri Agro        50,000.00",
      "  4 Metro Auto       1,05,750.00",
      "  5 Anand Textiles   2,86,400.00",
      "  6 Lakshmi Jewel      96,300.00",
      "  7 Deccan Hardware    40,000.00",
      "  8 Vaishnavi Engg   1,40,000.00",
      "  9 Nova Pharma        65,000.00",
    ],
  },
  json: {
    page: "return period Jul–Aug 2026",
    line: 5,
    value: "1,18,000.00",
    sum: "b7710fa3",
    rule: "gstr2b-v1",
    lines: [
      "{",
      '  "rtnprd": "082026",',
      '  "gstin": "29ABCDE1234F1Z5",',
      '  "b2b": [ {',
      '    "val": 118000.00,',
      '    "itcavl": "Y",',
      '    "inum": "AT/2026/0841",',
      '    "ctin": "29AAACA1122B"',
      "  }, {",
      '    "val": 42600.00,',
      '    "inum": "GP-2291"',
      "  } ]",
      "}",
    ],
  },
};

const state = { client: "sree", file: 0, view: "intake", filter: "all", tie: true, theme: "dark" };

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderClients() {
  const q = $("#client-search").value.trim().toLowerCase();
  const list = CLIENTS.filter((c) => {
    if (q && !(c.name.toLowerCase().includes(q) || c.gstin.toLowerCase().includes(q))) return false;
    if (state.filter === "attention") return c.state === "held" || c.state === "failed";
    if (state.filter === "ready") return c.state === "ready";
    return true;
  });
  $("#client-list").innerHTML =
    list.length === 0
      ? '<div class="empty"><p>No clients match that filter.</p></div>'
      : list
          .map(
            (c) => `
        <button type="button" class="client" data-client="${c.id}" data-state="${c.state}" aria-current="${c.id === state.client}">
          <span class="client-mark"></span>
          <span class="client-main">
            <span class="client-name">${esc(c.name)}</span>
            <span class="client-meta mono num">${c.gstin} · ${c.period}</span>
          </span>
          <span class="client-side">
            <span class="client-files num">${c.files} files</span>
            <span class="client-state">${esc(c.stateLabel)}</span>
          </span>
        </button>`
          )
          .join("");
  $("#client-list")
    .querySelectorAll(".client")
    .forEach((el) => el.addEventListener("click", () => selectClient(el.dataset.client)));
}

function updateCounts() {
  const list = currentFiles();
  const rows = list.reduce((n, f) => n + (parseInt(String(f.rows).replace(/[^0-9]/g, ""), 10) || 0), 0);
  document.querySelector("#stages .stage:nth-child(1) .stage-val").textContent = `${list.length} files`;
  document.querySelector("#stages .stage:nth-child(2) .stage-val").textContent = `${rows.toLocaleString("en-IN")} rows`;
  document.querySelector('.tab[data-view="intake"] .count').textContent = list.length;
}

function selectClient(id) {
  state.client = id;
  state.file = 0;
  const c = CLIENTS.find((x) => x.id === id);
  $("#crumb-client").textContent = c.name;
  $("#crumb-period").textContent = c.period;
  $("#work-name").textContent = c.name;
  $("#work-gstin").textContent = c.gstin;
  $("#work-period").textContent = c.period;
  $("#work-source").textContent = c.src;
  updateCounts();
  renderClients();
  renderFiles();
  renderInspector();
}

function currentFiles() {
  const c = CLIENTS.find((x) => x.id === state.client) || CLIENTS[0];
  return FILES.slice(0, c.files);
}

function renderFiles() {
  const list = currentFiles();
  if (state.file > list.length - 1) state.file = 0;
  $("#file-rows").innerHTML = list.map(
    (f, i) => `
    <tr data-file="${i}" aria-selected="${i === state.file}">
      <td class="file" title="${esc(f.name)}"><span class="ftype"><svg class="ico"><use href="#${f.icon}"/></svg>${esc(f.name)}</span></td>
      <td style="color:var(--text-2)">${esc(f.kind)}</td>
      <td class="r"><span class="fig">${f.rows}</span></td>
      <td style="color:var(--text-2)" class="num">${esc(f.period)}</td>
      <td class="r"><span class="fig">${f.conf}</span></td>
      <td><span class="state" data-s="${f.state}"><span class="sdot"></span>${esc(f.stateLabel)}</span></td>
    </tr>`
  ).join("");
  $("#file-rows")
    .querySelectorAll("tr")
    .forEach((tr) => tr.addEventListener("click", () => selectFile(Number(tr.dataset.file))));
}

function renderRecon() {
  $("#recon-rows").innerHTML = RECON.map(
    (r) => `
    <tr>
      <td class="file">${esc(r.supplier)}</td>
      <td class="mono num" style="color:var(--text-2)">${esc(r.inv)}</td>
      <td class="r"><span class="fig">${r.a}</span></td>
      <td class="r"><span class="fig">${r.b}</span></td>
      <td class="r"><span class="fig" style="color:${r.state === "warn" ? "var(--warn)" : "var(--text-2)"}">${r.diff}</span></td>
      <td><span class="tag ${r.state === "warn" ? "warn" : "ok"}">${esc(r.action)}</span></td>
    </tr>`
  ).join("");
}

function srcFor(index) {
  const f = currentFiles()[index] || currentFiles()[0];
  if (f.icon === "i-sheet") return SRC.sheet;
  if (f.icon === "i-braces") return SRC.json;
  return SRC.bank;
}

function renderInspector() {
  const list = currentFiles();
  const f = list[state.file] || list[0];
  const s = srcFor(state.file);
  $("#insp-file").textContent = f.name;
  $("#insp-sub").textContent = `${f.kind} · ${f.rows} parsed rows · ${s.page}`;
  $("#insp-line").textContent = `line ${s.line}`;
  $("#insp-val").textContent = s.value;
  $("#insp-sum").textContent = s.sum;
  const tieLine = s.lines[s.line - 1] || "";
  $("#src-view").innerHTML = s.lines
    .map((ln, i) => {
      const n = i + 1;
      const isTie = state.tie && n === s.line;
      return `<div class="src-line${isTie ? " tie" : ""}"><span class="src-no">${n}</span><span class="src-tx">${esc(ln)}</span>${isTie ? '<span class="tie-marker">TIE-OUT</span>' : ""}</div>`;
    })
    .join("");
  if (state.tie) {
    const el = $("#src-view").querySelector(".src-line.tie");
    const scroller = el && el.closest(".inspect-scroll");
    if (el && scroller) scroller.scrollTop = el.offsetTop - scroller.clientHeight / 2 + el.clientHeight / 2;
  }
}

function selectFile(i) {
  state.file = i;
  renderFiles();
  renderInspector();
}

function setView(v) {
  state.view = v;
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", t.dataset.view === v));
  document.querySelectorAll(".view").forEach((p) => (p.hidden = p.id !== `view-${v}`));
}

function setTheme(t) {
  state.theme = t;
  document.documentElement.setAttribute("data-theme", t);
  const btn = $("#theme-toggle");
  btn.setAttribute("aria-pressed", t === "light");
  btn.setAttribute("title", t === "light" ? "Switch to dark mode" : "Switch to light mode");
  btn.querySelector("use").setAttribute("href", t === "light" ? "#i-sun" : "#i-moon");
  try { localStorage.setItem("caunpacker-theme", t); } catch (e) {}
}

const COMMANDS = [
  { label: "Run extraction for this client", hint: "Intake", icon: "i-play" },
  { label: "Export Tally import (XML)", hint: "Export", icon: "i-download" },
  { label: "Open reconciliation exceptions", hint: "Reconcile", icon: "i-alert" },
  { label: "Toggle source tie-out", hint: "Inspector", icon: "i-tie" },
  { label: "Reveal source folder on disk", hint: "Local", icon: "i-folder" },
  { label: "Switch theme", hint: "Appearance", icon: "i-sun" },
];

function renderPalette(q = "") {
  const items = COMMANDS.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()));
  const clients = CLIENTS.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 4);
  $("#palette-list").innerHTML =
    items
      .map((c) => `<button type="button" class="palette-item"><svg class="ico"><use href="#${c.icon}"/></svg>${esc(c.label)}<span class="where">${esc(c.hint)}</span></button>`)
      .join("") +
    clients
      .map((c) => `<button type="button" class="palette-item" data-client="${c.id}"><svg class="ico"><use href="#i-search"/></svg>${esc(c.name)}<span class="where mono num">${c.gstin}</span></button>`)
      .join("");
  $("#palette-list")
    .querySelectorAll("[data-client]")
    .forEach((el) =>
      el.addEventListener("click", () => {
        selectClient(el.dataset.client);
        closePalette();
      })
    );
  $("#palette-list")
    .querySelectorAll(".palette-item:not([data-client])")
    .forEach((el, i) =>
      el.addEventListener("click", () => {
        if (i === 1) setView("preview");
        if (i === 2) setView("recon");
        if (i === 3) toggleTie();
        if (i === 5) setTheme(state.theme === "dark" ? "light" : "dark");
        closePalette();
      })
    );
}

function openPalette() {
  $("#palette").hidden = false;
  $("#palette-input").value = "";
  renderPalette();
  $("#palette-input").focus();
}
function closePalette() {
  $("#palette").hidden = true;
}

function toggleTie() {
  state.tie = !state.tie;
  $("#tie-btn").setAttribute("aria-pressed", String(state.tie));
  $("#tie-btn").lastChild.textContent = state.tie ? " Tie-out on" : " Tie-out off";
  renderInspector();
}

function init() {
  try {
    const saved = localStorage.getItem("caunpacker-theme");
    if (saved) setTheme(saved);
  } catch (e) {}

  updateCounts();
  renderClients();
  renderFiles();
  renderRecon();
  renderInspector();

  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => setView(t.dataset.view)));
  document.querySelectorAll(".seg button").forEach((b) =>
    b.addEventListener("click", () => {
      state.filter = b.dataset.filter;
      document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      renderClients();
    })
  );
  $("#client-search").addEventListener("input", renderClients);
  $("#theme-toggle").addEventListener("click", () => setTheme(state.theme === "dark" ? "light" : "dark"));
  $("#tie-btn").addEventListener("click", toggleTie);
  $("#cmd-open").addEventListener("click", openPalette);
  $("#rail-toggle").addEventListener("click", () => {
    const open = document.body.classList.toggle("inspect-open");
    $("#rail-toggle").setAttribute("aria-pressed", String(open));
  });
  $("#palette").addEventListener("click", (e) => { if (e.target.id === "palette") closePalette(); });
  $("#palette-input").addEventListener("input", (e) => renderPalette(e.target.value));

  document.querySelectorAll(".checkbox").forEach((c) =>
    c.addEventListener("click", () => c.setAttribute("aria-checked", c.getAttribute("aria-checked") !== "true"))
  );

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      $("#palette").hidden ? openPalette() : closePalette();
      return;
    }
    if (e.key === "Escape") {
      closePalette();
      document.body.classList.remove("inspect-open");
      $("#rail-toggle").setAttribute("aria-pressed", "false");
    }
    if ($("#palette").hidden && e.key.toLowerCase() === "t" && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== "INPUT") toggleTie();
  });

  try {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    if (!localStorage.getItem("caunpacker-theme") && mq.matches) setTheme("light");
  } catch (e) {}

  applyHash();
  window.addEventListener("hashchange", applyHash);
}

function applyHash() {
  if (!location.hash) return;
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("theme")) setTheme(h.get("theme"));
  if (h.get("client") && CLIENTS.some((c) => c.id === h.get("client"))) selectClient(h.get("client"));
  if (h.get("file") != null && !Number.isNaN(Number(h.get("file")))) selectFile(Number(h.get("file")));
  if (h.get("view")) setView(h.get("view"));
}

document.addEventListener("DOMContentLoaded", init);
