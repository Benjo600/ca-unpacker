/*
 * Landing page: point the Download buttons at the newest installer CI published.
 *
 * GitHub's `releases/latest/download/...` URL skips prereleases, and CI publishes
 * every installer as a prerelease, so that path stays frozen on the last full
 * release. The list endpoint does not skip them, so the page reads it once on
 * load and rewrites its own download links.
 *
 * No dependencies. Works as a plain <script> in the browser and as a CommonJS
 * module under node, so the selection logic can be tested without a browser.
 */
(function (global) {
  "use strict";

  var OWNER = "Benjo600";
  var REPO = "ca-unpacker";
  var ASSET_NAME = "CAUnpacker-Setup.exe";
  var API_URL =
    "https://api.github.com/repos/" + OWNER + "/" + REPO + "/releases?per_page=10";
  var FALLBACK_TEXT =
    "Latest build link unavailable — use the download button above.";
  var API_TIMEOUT_MS = 8000;
  var MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
  ];
  // CI names the asset exactly CAUnpacker-Setup.exe. The looser shape is only a
  // safety net in case the workflow ever starts stamping the version into it.
  var SETUP_ASSET = /^caunpacker-setup(?:-[a-z0-9._]+)?\.exe$/i;
  var SETUP_HREF = /(^|\/)caunpacker-setup\.exe$/i;

  /* ---- pure helpers ---------------------------------------------------- */

  // The installer asset inside one release, or null. Exact name wins.
  function findSetupAsset(assets) {
    if (!Array.isArray(assets)) return null;
    var loose = null;
    for (var i = 0; i < assets.length; i++) {
      var asset = assets[i];
      if (!asset || typeof asset.name !== "string") continue;
      if (typeof asset.browser_download_url !== "string" || !asset.browser_download_url) {
        continue;
      }
      var name = asset.name.trim();
      if (name.toLowerCase() === ASSET_NAME.toLowerCase()) return asset;
      if (!loose && SETUP_ASSET.test(name)) loose = asset;
    }
    return loose;
  }

  // "2026-11-23T08:02:39Z" -> "23 Nov 2026". Empty string when unparseable.
  function formatDate(value) {
    var time = Date.parse(value);
    if (isNaN(time)) return "";
    var date = new Date(time);
    return (
      date.getUTCDate() + " " + MONTHS[date.getUTCMonth()] + " " + date.getUTCFullYear()
    );
  }

  // Newest release — prerelease or not — that carries the installer asset.
  // Drafts are skipped: they have no public download URL.
  function pickLatestBuild(releases) {
    if (!Array.isArray(releases)) return null;
    var best = null;
    for (var i = 0; i < releases.length; i++) {
      var release = releases[i];
      if (!release || release.draft === true) continue;
      var asset = findSetupAsset(release.assets);
      if (!asset) continue;
      var created = release.created_at;
      var published = release.published_at || created || "";
      var time = Date.parse(created || published);
      // No usable date: fall back to list position (the API returns newest first).
      var rank = isNaN(time) ? -(i + 1) : time;
      if (best === null || rank > best.rank) {
        best = { rank: rank, release: release, asset: asset, published: published };
      }
    }
    if (best === null) return null;
    var rel = best.release;
    return {
      tag: rel.tag_name || rel.name || "",
      name: rel.name || rel.tag_name || "",
      date: formatDate(best.published || rel.created_at),
      publishedAt: best.published || rel.created_at || "",
      url: best.asset.browser_download_url,
      size: typeof best.asset.size === "number" ? best.asset.size : 0,
      releaseUrl: rel.html_url || ""
    };
  }

  function formatBuildLine(build) {
    if (!build || typeof build.url !== "string" || !build.url) return FALLBACK_TEXT;
    var label = build.tag || build.name || "latest";
    return build.date
      ? "Latest build: " + label + " \u00b7 " + build.date
      : "Latest build: " + label;
  }

  // True for the setup links the page ships with: "/CAUnpacker-Setup.exe" or the
  // relative "CAUnpacker-Setup.exe" used when index.html is opened from disk.
  function isSetupHref(href) {
    if (typeof href !== "string") return false;
    var path = href.split("#")[0].split("?")[0];
    return SETUP_HREF.test(path);
  }

  /* ---- DOM writers ----------------------------------------------------- */

  // Rewrites every setup link in the document. Returns how many changed.
  function applyDownloadLinks(doc, build) {
    if (!doc || !build || typeof build.url !== "string" || !build.url) return 0;
    var links = doc.querySelectorAll("a[href]");
    var updated = 0;
    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if (!isSetupHref(link.getAttribute("href"))) continue;
      link.setAttribute("href", build.url);
      updated += 1;
    }
    return updated;
  }

  // Writes the quiet line under the buttons; reveals it if it was hidden.
  function setBuildLine(doc, text) {
    if (!doc) return 0;
    var nodes = doc.querySelectorAll("[data-build-line]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = text;
      if (nodes[i].hidden) nodes[i].hidden = false;
    }
    return nodes.length;
  }

  /* ---- wiring ---------------------------------------------------------- */

  function init() {
    if (typeof document === "undefined") return;
    var fetchImpl = typeof fetch === "function" ? fetch : null;
    if (!fetchImpl) {
      // Old browser: leave the shipped links alone, say so quietly.
      setBuildLine(document, FALLBACK_TEXT);
      return;
    }

    var options = {
      headers: { Accept: "application/vnd.github+json" },
      cache: "no-store"
    };
    var timer = null;
    if (typeof AbortController === "function") {
      var controller = new AbortController();
      options.signal = controller.signal;
      timer = setTimeout(function () {
        controller.abort();
      }, API_TIMEOUT_MS);
    }
    var done = function () {
      if (timer) clearTimeout(timer);
      timer = null;
    };

    fetchImpl(API_URL, options)
      .then(function (response) {
        if (!response || !response.ok) {
          throw new Error("GitHub API HTTP " + (response && response.status));
        }
        return response.json();
      })
      .then(function (releases) {
        var build = pickLatestBuild(releases);
        if (!build) throw new Error("no installer asset in the last 10 releases");
        applyDownloadLinks(document, build);
        setBuildLine(document, formatBuildLine(build));
      })
      .catch(function () {
        // Keep the shipped /CAUnpacker-Setup.exe link: still a working download.
        setBuildLine(document, FALLBACK_TEXT);
      })
      .then(done, done);
  }

  var api = {
    ASSET_NAME: ASSET_NAME,
    API_URL: API_URL,
    FALLBACK_TEXT: FALLBACK_TEXT,
    findSetupAsset: findSetupAsset,
    formatDate: formatDate,
    pickLatestBuild: pickLatestBuild,
    formatBuildLine: formatBuildLine,
    isSetupHref: isSetupHref,
    applyDownloadLinks: applyDownloadLinks,
    setBuildLine: setBuildLine,
    init: init
  };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    global.CAUnpackerLatestBuild = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
