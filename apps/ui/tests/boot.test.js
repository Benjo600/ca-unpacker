"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const boot = require("../boot.js");
const {
  bootShellStateFor,
  settleBootShell,
  deferredModules,
  deferredModuleNames,
  modulesForPane,
  ensureModules,
  ensureForPane,
  mark,
  markOnce,
  measure,
} = boot;

const uiDir = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(uiDir, "index.html"), "utf8");
const appSource = fs.readFileSync(path.join(uiDir, "app.js"), "utf8");

// ---- the first-paint shell decision -------------------------------------

// A real screen means the branded shell has done its job and must go, with no
// busy state left behind.
for (const screen of ["login", "setup", "welcome", "desk"]) {
  assert.deepEqual(bootShellStateFor(screen), { hidden: true, busy: false });
}

// Anything else (no screen chosen yet, or a desk pane name) leaves the shell up
// and marked busy.
for (const screen of ["", null, undefined, "clients", "reports"]) {
  assert.deepEqual(bootShellStateFor(screen), { hidden: false, busy: true });
}

// With no browser the settle call still reports the decision instead of throwing,
// which is what lets the rest of the boot logic stay testable.
assert.deepEqual(settleBootShell("desk"), { hidden: true, busy: false });
assert.deepEqual(settleBootShell("clients"), { hidden: false, busy: true });

// ---- which deferred modules a pane needs --------------------------------

assert.deepEqual(modulesForPane("recon"), ["practice-summary", "recon-centre"]);
assert.deepEqual(modulesForPane("dashboard"), ["practice-summary"]);
assert.deepEqual(modulesForPane("dump"), ["preflight-summary"]);
assert.deepEqual(modulesForPane("clients"), []);
assert.deepEqual(modulesForPane("periods"), []);
assert.deepEqual(modulesForPane(null), []);

// Callers get a copy, so a stray push cannot change what a later click loads.
const recon = modulesForPane("recon");
recon.push("not-a-module");
assert.deepEqual(modulesForPane("recon"), ["practice-summary", "recon-centre"]);

// ---- the deferred registry ----------------------------------------------

const names = deferredModuleNames().slice().sort();
assert.deepEqual(names, [
  "practice-summary",
  "preflight-summary",
  "recon-centre",
  "update-state",
]);
for (const eager of ["format", "clients-view", "reports-view"]) {
  assert.equal(names.includes(eager), false, `${eager} must stay eager`);
}
for (const entry of deferredModules()) {
  assert.ok(entry.src.endsWith(".js"), `${entry.name} has a script file`);
  assert.equal(entry.src, `${entry.name}.js`);
  assert.ok(entry.global, `${entry.name} exposes a global`);
}

// ---- index.html: the shell and the manifest -----------------------------

assert.ok(html.includes('id="boot-shell"'), "index.html needs the first-paint shell");
assert.ok(
  /id="boot-shell"[^>]*aria-busy="true"/.test(html),
  "the first-paint shell starts busy"
);
assert.ok(html.includes('role="status"'), "the shell announces itself politely");
assert.ok(html.includes("Opening your desk"), "the quiet boot line is on screen");
assert.ok(
  html.indexOf('id="boot-shell"') < html.indexOf('id="auth-gate"'),
  "the shell paints before the sign-in gate can appear"
);

const manifestMatch = html.match(/<template id="deferred-modules"[\s\S]*?<\/template>/);
assert.ok(manifestMatch, "index.html carries the deferred module manifest");
const manifest = manifestMatch[0];
const eagerHtml = html.replace(manifest, "");

for (const entry of deferredModules()) {
  assert.ok(
    manifest.includes(`src="${entry.src}"`),
    `${entry.src} is listed in the manifest the desktop contract test reads`
  );
  assert.ok(
    manifest.includes(`data-module="${entry.name}"`),
    `${entry.name} is named in the manifest`
  );
  assert.equal(
    eagerHtml.includes(`src="${entry.src}"`),
    false,
    `${entry.src} must not be loaded before the first paint`
  );
  assert.ok(
    appSource.includes(`"${entry.name}"`),
    `app.js should load ${entry.name} on first use`
  );
}

// ---- index.html: eager order and deferred execution ---------------------

for (const eager of ["format.js", "clients-view.js", "reports-view.js"]) {
  assert.ok(eagerHtml.includes(`src="${eager}"`), `${eager} stays eager`);
}

const bootAt = eagerHtml.indexOf('src="boot.js"');
const appAt = eagerHtml.indexOf('src="app.js"');
assert.ok(bootAt >= 0, "boot.js is loaded");
assert.ok(appAt > bootAt, "boot.js runs before app.js");
for (const helper of ["format.js", "clients-view.js", "reports-view.js"]) {
  assert.ok(
    eagerHtml.indexOf(`src="${helper}"`) < appAt,
    `${helper} loads before app.js still owns it`
  );
}

for (const match of eagerHtml.matchAll(/<script src="([^"]+)"(\s[^>]*)?>/g)) {
  assert.ok(
    (match[2] || "").includes("defer"),
    `${match[1]} should defer so parsing and the first paint come first`
  );
}

assert.ok(
  appSource.includes("settleBootShell"),
  "app.js hands the shell over when a screen is chosen"
);
assert.ok(
  appSource.includes("markDeskReady"),
  "app.js marks the desk as ready for the boot timings"
);

// ---- timings are recorded for manual checking ---------------------------

assert.equal(typeof mark("test-start"), "number");
const end = mark("test-end");
assert.equal(typeof end, "number");
const span = measure("test-span", "test-start", "test-end");
assert.equal(typeof span, "number");
assert.ok(span >= 0);
assert.equal(globalThis.__bootTimings.measures["test-span"], span);
assert.equal(typeof globalThis.__bootTimings.marks["test-start"], "number");
assert.equal(globalThis.__bootTimings.marks["test-start"] <= globalThis.__bootTimings.marks["test-end"], true);

// A measure with a missing endpoint is skipped rather than reported as NaN.
assert.equal(measure("test-missing", "test-start", "test-nowhere"), null);
assert.equal(measure("", "test-start", "test-end"), null);

// First-event marks keep their first number.
const firstOnce = markOnce("test-once");
assert.equal(markOnce("test-once"), firstOnce);

// ---- first-paint shell with a minimal stand-in document ----------------

function fakeElement(selector) {
  const attrs = {};
  const listeners = {};
  return {
    selector: selector,
    hidden: false,
    src: "",
    setAttribute(name, value) {
      attrs[name] = String(value);
    },
    getAttribute(name) {
      return attrs[name] === undefined ? null : attrs[name];
    },
    addEventListener(type, handler) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(handler);
    },
    dispatch(type) {
      for (const handler of listeners[type] || []) handler({ type: type });
    },
  };
}

function withFakeDocument(run) {
  const shell = fakeElement("boot-shell");
  const appended = [];
  const head = {
    appendChild(element) {
      appended.push(element);
      // A real file would run and then fire load; here the test writes the
      // global it would have exposed and reports success.
      if (element.src === "practice-summary.js") {
        globalThis.CAPracticeSummary = { ready: true };
        element.dispatch("load");
      } else {
        element.dispatch("error");
      }
    },
  };
  globalThis.document = {
    getElementById(selector) {
      return selector === "boot-shell" ? shell : null;
    },
    createElement(tag) {
      return fakeElement(tag);
    },
    head: head,
    body: { appendChild() {} },
  };
  return Promise.resolve()
    .then(() => run({ shell, appended }))
    .finally(() => {
      delete globalThis.document;
      delete globalThis.CAPracticeSummary;
    });
}

// ---- deferred loading guard (no browser) --------------------------------

async function main() {
  await withFakeDocument(async ({ shell, appended }) => {
    // The shell is visible and busy until a real screen is chosen.
    assert.deepEqual(settleBootShell("clients"), { hidden: false, busy: true });
    assert.equal(shell.hidden, false);
    assert.equal(shell.getAttribute("aria-busy"), "true");

    // Choosing a screen hides it in the same call and clears the busy state.
    assert.deepEqual(settleBootShell("desk"), { hidden: true, busy: false });
    assert.equal(shell.hidden, true);
    assert.equal(shell.getAttribute("aria-busy"), "false");

    // The default loader appends the script for a module that is not on the page
    // and resolves true only once the global appears.
    assert.equal(await ensureModules("practice-summary"), true);
    assert.equal(appended.length, 1);
    assert.equal(appended[0].src, "practice-summary.js");
    assert.equal(globalThis.__bootTimings.modules["practice-summary"] >= 0, true);

    // A file that fails to load reports false instead of throwing.
    assert.equal(await ensureModules("update-state"), false);
  });

  let loads = 0;
  const loader = (entry) => {
    assert.ok(entry.src.endsWith(".js"));
    loads += 1;
    return Promise.resolve(true);
  };

  // Two callers racing for the same module share one load.
  const raced = await Promise.all([
    ensureModules("recon-centre", loader),
    ensureModules(["recon-centre"], loader),
  ]);
  assert.deepEqual(raced, [true, true]);
  assert.equal(loads, 1, "one module, one load, even when two callers race");

  await ensureModules("recon-centre", loader);
  assert.equal(loads, 1, "an already-requested module is never fetched twice");

  // A failed load is reported but does not stick: the next click retries.
  let attempts = 0;
  const failing = () => {
    attempts += 1;
    return Promise.resolve(false);
  };
  assert.equal(await ensureModules("update-state", failing), false);
  assert.equal(attempts, 1);
  assert.equal(await ensureModules("update-state", failing), false);
  assert.equal(attempts, 2, "a failed module is retried on the next use");

  // A module already on the page resolves without touching the network.
  globalThis.CAPreflightSummary = { ready: true };
  let preflightLoads = 0;
  assert.equal(
    await ensureModules("preflight-summary", () => {
      preflightLoads += 1;
      return Promise.resolve(false);
    }),
    true
  );
  assert.equal(preflightLoads, 0, "an already-loaded module is not fetched again");
  delete globalThis.CAPreflightSummary;

  // Unknown names are ignored, never fatal.
  assert.equal(
    await ensureModules("not-a-real-module", () => {
      throw new Error("an unknown module must never load");
    }),
    true
  );

  // A pane with no deferred needs resolves immediately.
  assert.equal(await ensureForPane("clients", failing), true);
}

main()
  .then(() => {
    console.log("boot behavior tests passed");
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
