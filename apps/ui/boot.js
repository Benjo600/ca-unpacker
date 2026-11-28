/* CA Unpacker - first-paint shell, boot timings and deferred modules.
 *
 * Loaded before app.js and after the view helpers. Everything here is local:
 * no network, no telemetry, no dependencies. The static shell in index.html
 * paints before any of this runs, so a slow Python bridge never shows the
 * person a blank window.
 */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CABoot = api;
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  // A screen in this list means the app has chosen a real surface, so the
  // first-paint shell has done its job and must go.
  const SETTLING_SCREENS = ["login", "setup", "welcome", "desk"];

  // Modules that only matter once the desk is open. index.html carries the same
  // list inertly in <template id="deferred-modules">; this copy is the fallback
  // if that manifest is ever missing.
  const FALLBACK_MODULES = [
    {
      name: "practice-summary",
      src: "practice-summary.js",
      global: "CAPracticeSummary",
    },
    {
      name: "preflight-summary",
      src: "preflight-summary.js",
      global: "CAPreflightSummary",
    },
    { name: "update-state", src: "update-state.js", global: "CAUpdateState" },
    {
      name: "recon-centre",
      src: "recon-centre.js",
      global: "CAReconCentre",
    },
  ];

  // What each desk pane cannot render without. openPeriod, loadDashboard and
  // showReconciliation wait on these, so an early click can never render a
  // pane against a module that has not arrived yet.
  const PANE_MODULES = {
    dashboard: ["practice-summary"],
    recon: ["practice-summary", "recon-centre"],
    dump: ["preflight-summary"],
  };

  const clock = (root.__bootTimings = root.__bootTimings || {});
  const marks = (clock.marks = clock.marks || {});
  const measures = (clock.measures = clock.measures || {});
  const moduleTimes = (clock.modules = clock.modules || {});
  const pending = new Map();
  let moduleList = null;

  /* ---------------------------------------------------------------- */
  /* Timings: performance.mark/measure, mirrored into window.__bootTimings */
  /* ---------------------------------------------------------------- */

  function perf() {
    const api = root.performance;
    return api && typeof api.now === "function" ? api : null;
  }

  function round(value) {
    return Math.round(value * 10) / 10;
  }

  function mark(name) {
    const key = name === null || name === undefined ? "" : String(name);
    if (!key) return null;
    const api = perf();
    if (!api) return null;
    const at = round(api.now());
    marks[key] = at;
    if (typeof api.mark === "function") {
      try {
        api.mark("ca-unpacker:" + key);
      } catch (error) {
        // A duplicate mark is harmless; the number is already recorded.
      }
    }
    return at;
  }

  function measure(name, from, to) {
    const key = name === null || name === undefined ? "" : String(name);
    const start = marks[from];
    const end = marks[to];
    if (!key || start === undefined || end === undefined) return null;
    const api = perf();
    if (api && typeof api.measure === "function") {
      try {
        api.measure("ca-unpacker:" + key, "ca-unpacker:" + from, "ca-unpacker:" + to);
      } catch (error) {
        // Older engines need both marks in the same document; the number below
        // is still trustworthy.
      }
    }
    measures[key] = round(Math.max(0, end - start));
    return measures[key];
  }

  // For marks that describe the first time something happened (the desk
  // opening after a library reset, for instance).
  function markOnce(name) {
    const key = name === null || name === undefined ? "" : String(name);
    if (!key || marks[key] !== undefined) return marks[key];
    return mark(key);
  }

  // The head script records the first clock tick before this file exists, so
  // hand that number to the browser's own timeline as well.
  function claimHeadMark() {
    const api = perf();
    if (!api || marks.html === undefined || typeof api.mark !== "function") return;
    try {
      if (typeof api.clearMarks === "function") api.clearMarks("ca-unpacker:html");
      api.mark("ca-unpacker:html", { startTime: marks.html });
    } catch (error) {
      // startTime support is optional; window.__bootTimings still carries it.
    }
  }

  /* ---------------------------------------------------------------- */
  /* First-paint shell                                                 */
  /* ---------------------------------------------------------------- */

  function shellElement() {
    if (typeof document === "undefined" || !document.getElementById) return null;
    return document.getElementById("boot-shell");
  }

  function bootShellStateFor(screen) {
    const settled = SETTLING_SCREENS.indexOf(String(screen || "")) >= 0;
    return { hidden: settled, busy: !settled };
  }

  function markScreen(screen) {
    const name = String(screen || "");
    const key = "screen-" + name;
    if (!name || marks[key] !== undefined) return;
    mark(key);
    measure("paint-to-" + name, "first-paint", key);
    measure("scripts-to-" + name, "scripts", key);
  }

  // Called by app.js the moment a real screen is chosen. Hiding the shell and
  // revealing the screen happen in the same task, so there is one paint and no
  // layout shift. The shell holds no focusable element, so it never traps focus.
  function settleBootShell(screen) {
    const state = bootShellStateFor(screen);
    const el = shellElement();
    if (el) {
      el.hidden = state.hidden;
      el.setAttribute("aria-busy", state.busy ? "true" : "false");
    }
    if (state.hidden) {
      if (marks["shell-hidden"] === undefined) {
        mark("shell-hidden");
        measure("shell-visible", "first-paint", "shell-hidden");
      }
      markScreen(screen);
    }
    return state;
  }

  /* ---------------------------------------------------------------- */
  /* Deferred modules                                                  */
  /* ---------------------------------------------------------------- */

  function globalFor(name) {
    for (let index = 0; index < FALLBACK_MODULES.length; index += 1) {
      if (FALLBACK_MODULES[index].name === name) return FALLBACK_MODULES[index].global;
    }
    return "";
  }

  // index.html keeps the deferred list in a <template>, whose contents are
  // never fetched or executed. Reading it here keeps the document and the
  // loader agreeing on one file list.
  function readManifest() {
    if (typeof document === "undefined" || !document.getElementById) return null;
    const holder = document.getElementById("deferred-modules");
    const content = holder && holder.content;
    if (!content || typeof content.querySelectorAll !== "function") return null;
    const nodes = content.querySelectorAll("script[src]");
    const list = [];
    for (let index = 0; index < nodes.length; index += 1) {
      const node = nodes[index];
      const name = node.getAttribute("data-module") || "";
      const src = node.getAttribute("src") || "";
      if (!name || !src) continue;
      list.push({
        name: name,
        src: src,
        global: node.getAttribute("data-global") || globalFor(name),
      });
    }
    return list.length ? list : null;
  }

  function deferredModules() {
    if (!moduleList) moduleList = readManifest() || FALLBACK_MODULES.slice();
    return moduleList.map((entry) => ({ name: entry.name, src: entry.src, global: entry.global }));
  }

  function moduleFor(name) {
    const wanted = String(name || "");
    const list = deferredModules();
    for (let index = 0; index < list.length; index += 1) {
      if (list[index].name === wanted) return list[index];
    }
    return null;
  }

  function deferredModuleNames() {
    return deferredModules().map((entry) => entry.name);
  }

  function modulesForPane(pane) {
    const list = PANE_MODULES[String(pane || "")];
    return Array.isArray(list) ? list.slice() : [];
  }

  function defaultLoader(entry) {
    return new Promise(function (resolve) {
      if (typeof document === "undefined" || !document.createElement) {
        resolve(false);
        return;
      }
      if (root[entry.global]) {
        resolve(true);
        return;
      }
      const startedAt = perf() ? perf().now() : 0;
      const script = document.createElement("script");
      script.src = entry.src;
      script.async = true;
      script.addEventListener("load", function () {
        if (perf()) moduleTimes[entry.name] = round(perf().now() - startedAt);
        resolve(Boolean(root[entry.global]));
      });
      script.addEventListener("error", function () {
        // A failed file must not poison the cache: the next click retries.
        moduleTimes[entry.name] = -1;
        resolve(false);
      });
      (document.head || document.body).appendChild(script);
    });
  }

  // Loads a set of modules once. Unknown names are ignored rather than fatal.
  // The optional loader exists so the guard is testable without a browser.
  function ensureModules(names, loader) {
    const wanted = Array.isArray(names) ? names : [names];
    const load = typeof loader === "function" ? loader : defaultLoader;
    const work = [];
    for (let index = 0; index < wanted.length; index += 1) {
      const entry = moduleFor(wanted[index]);
      if (!entry) continue;
      if (root[entry.global]) {
        work.push(Promise.resolve(true));
        continue;
      }
      if (!pending.has(entry.name)) {
        const job = Promise.resolve()
          .then(function () {
            return load(entry);
          })
          .then(function (ok) {
            if (!ok) pending.delete(entry.name);
            return Boolean(ok);
          })
          .catch(function () {
            pending.delete(entry.name);
            return false;
          });
        pending.set(entry.name, job);
      }
      work.push(pending.get(entry.name));
    }
    if (!work.length) return Promise.resolve(true);
    return Promise.all(work).then(function (results) {
      return results.every(Boolean);
    });
  }

  function ensureForPane(pane, loader) {
    return ensureModules(modulesForPane(pane), loader);
  }

  /* ---------------------------------------------------------------- */
  /* Scheduling                                                        */
  /* ---------------------------------------------------------------- */

  function whenIdle(callback, timeout) {
    const wait = typeof timeout === "number" ? timeout : 1200;
    if (typeof root.requestIdleCallback === "function") {
      root.requestIdleCallback(function () {
        callback();
      }, { timeout: wait });
      return;
    }
    if (typeof root.setTimeout === "function") root.setTimeout(callback, 60);
    else callback();
  }

  function afterFirstPaint(callback) {
    if (typeof root.requestAnimationFrame === "function") {
      root.requestAnimationFrame(function () {
        root.requestAnimationFrame(function () {
          callback();
        });
      });
      return;
    }
    if (typeof root.setTimeout === "function") root.setTimeout(callback, 0);
    else callback();
  }

  function prefetchDeferred() {
    whenIdle(function () {
      ensureModules(deferredModuleNames());
    }, 1500);
  }

  function start() {
    claimHeadMark();
    mark("scripts");
    afterFirstPaint(function () {
      mark("first-paint");
      measure("shell-paint", "scripts", "first-paint");
      if (marks["shell-hidden"] !== undefined) {
        measure("shell-visible", "first-paint", "shell-hidden");
      }
      prefetchDeferred();
    });
  }

  if (typeof document !== "undefined") start();

  return {
    screens: function () {
      return SETTLING_SCREENS.slice();
    },
    bootShellStateFor: bootShellStateFor,
    settleBootShell: settleBootShell,
    deferredModules: deferredModules,
    deferredModuleNames: deferredModuleNames,
    modulesForPane: modulesForPane,
    ensureModules: ensureModules,
    ensureForPane: ensureForPane,
    prefetchDeferred: prefetchDeferred,
    whenIdle: whenIdle,
    afterFirstPaint: afterFirstPaint,
    mark: mark,
    markOnce: markOnce,
    measure: measure,
    timings: function () {
      return { marks: marks, measures: measures, modules: moduleTimes };
    },
  };
});
