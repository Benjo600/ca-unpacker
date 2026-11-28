"""Cold-start benchmark for CA Unpacker (no window, no user data).

Measures what the desktop shell pays before a CA can click anything:
import of ``apps.desktop.app``, constructing the bridge object, and the first
``get_state`` call. Each run uses a throwaway LOCALAPPDATA so no library is
reused, which is the true cold start.

Usage (repo root, project venv):

    .venv\\Scripts\\python.exe boot_bench.py
    .venv\\Scripts\\python.exe boot_bench.py --runs 5
    .venv\\Scripts\\python.exe boot_bench.py --importtime
    .venv\\Scripts\\python.exe boot_bench.py --main

``--importtime`` adds the top 20 modules by cumulative import time.
``--main`` also times the real startup path (library, database, interrupted-job
reconcile) up to the moment the window would be created, with window creation
stubbed out. No pywebview window is ever opened; ``--main`` does let pywebview
initialise its GUI backend, exactly as the app does.
``--signed-in`` also times the first state read as a signed-in CA, once normally
and once with the network stalled at its 3 s timeout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Modules a cold first paint must not need. Reported so the lazy-import work
# is measurable, not assumed.
HEAVY_MODULES = (
    "openpyxl",
    "sqlalchemy",
    "httpx",
    "numpy",
    "fitz",
    "pymupdf",
    "pdfplumber",
    "cryptography",
    "webview",
    "PIL",
)

CHILD_SOURCE = r"""
import json
import sys
import time

started = time.perf_counter()
import apps.desktop.app as app_module
after_import = time.perf_counter()

api = app_module.DesktopApi()
after_construct = time.perf_counter()

api.get_state()
after_state = time.perf_counter()

heavy = {}
for name in %(heavy)r:
    module = sys.modules.get(name)
    heavy[name] = module is not None

# Optional: time the real startup path (library, engine, interrupted-job
# reconcile) up to the moment the shell would call webview.create_window.
# The window is never created and no protocol handler is written, so this is
# safe to run on a machine that already has the app installed.
ready = None
if %(measure_main)r:
    class _Ready(BaseException):
        pass

    def _fake_create_window(*_args, **_kwargs):
        global ready
        ready = time.perf_counter() - started
        raise _Ready()


    original = {
        name: getattr(app_module, name)
        for name in (
            "_show_fatal",
            "_schedule_startup_update_check",
            "ensure_registered",
        )
    }
    original_create = app_module.webview.create_window
    original_start = app_module.webview.start
    app_module._show_fatal = lambda _message: None
    app_module._schedule_startup_update_check = lambda: None
    app_module.ensure_registered = lambda: (True, None)
    app_module.webview.create_window = _fake_create_window
    app_module.webview.start = lambda **_kwargs: None
    try:
        app_module.main()
    except _Ready:
        pass
    finally:
        app_module.webview.create_window = original_create
        app_module.webview.start = original_start
        for name, value in original.items():
            setattr(app_module, name, value)

# Optional: the first state read as a signed-in CA, and again with the network
# stalled at its full 3 s timeout. The second number is what a CA on a dead
# connection pays before the desk appears.
signed_in = None
if %(measure_signed_in)r:
    from apps.engine import auth as auth_module

    auth_module.login_via_tokens("bench.header.sig", "bench-refresh-token")

    before = time.perf_counter()
    api.get_state()
    normal = time.perf_counter() - before

    original_probe = auth_module._network_available

    def _stalled_network():
        time.sleep(3.0)
        return False

    auth_module._network_available = _stalled_network
    try:
        before = time.perf_counter()
        api.get_state()
        stalled = time.perf_counter() - before
    finally:
        auth_module._network_available = original_probe

    signed_in = {"normal": normal, "stalled": stalled}

print(json.dumps({
    "import": after_import - started,
    "construct": after_construct - after_import,
    "get_state": after_state - after_construct,
    "total": after_state - started,
    "ready": ready,
    "signed_in": signed_in,
    "modules": heavy,
}))
"""


def _child_env(localappdata: str) -> dict:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = localappdata
    env["CA_UNPACKER_DEV"] = "1"
    # A console-less app and a console run should measure the same Python.
    env.pop("PYTHONSTARTUP", None)
    return env


def _run_child(
    importtime: bool = False,
    measure_main: bool = False,
    measure_signed_in: bool = False,
) -> tuple[dict, str]:
    """One fresh interpreter: import, construct, get_state."""
    temp_root = tempfile.mkdtemp(prefix="caunpacker-bench-")
    localappdata = os.path.join(temp_root, "localappdata")
    os.makedirs(localappdata, exist_ok=True)
    source = CHILD_SOURCE % {
        "heavy": HEAVY_MODULES,
        "measure_main": measure_main,
        "measure_signed_in": measure_signed_in,
    }
    command = [sys.executable]
    if importtime:
        command.append("-X")
        command.append("importtime")
    command.extend(["-c", source])
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=_child_env(localappdata),
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "benchmark child failed:\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    return payload, completed.stderr


def _parse_importtime(stderr: str) -> list[tuple[str, float]]:
    """Top modules by cumulative import time from ``-X importtime``."""
    pattern = re.compile(
        r"^import time:\s+(\d+)\s*\|\s*(\d+)\s*\|\s+(.+)$"
    )
    entries: list[tuple[str, float]] = []
    for line in stderr.splitlines():
        cleaned = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        match = pattern.match(cleaned)
        if not match:
            continue
        _self_us, cumulative_us, name = match.groups()
        entries.append((name.strip(), int(cumulative_us) / 1_000_000))
    entries.sort(key=lambda item: item[1], reverse=True)
    return entries


def _print_medians(results: list[dict]) -> None:
    labels = ("import", "construct", "get_state", "total")
    payload = ["| phase | median | runs (s) |", "|---|---|---|"]
    for label in labels:
        values = [run[label] for run in results]
        runs = ", ".join(f"{value:.2f}" for value in values)
        payload.append(f"| {label} | {statistics.median(values):.2f} s | {runs} |")
    ready = [run["ready"] for run in results if run.get("ready") is not None]
    if ready:
        runs = ", ".join(f"{value:.2f}" for value in ready)
        payload.append(
            f"| window ready (main, no window shown) "
            f"| {statistics.median(ready):.2f} s | {runs} |"
        )
    signed = [run["signed_in"] for run in results if run.get("signed_in")]
    if signed:
        normal = ", ".join(f"{run['normal']:.2f}" for run in signed)
        stalled = ", ".join(f"{run['stalled']:.2f}" for run in signed)
        payload.append(
            f"| signed-in first state | "
            f"{statistics.median([r['normal'] for r in signed]):.2f} s | {normal} |"
        )
        payload.append(
            f"| signed-in first state, network stalled at 3 s | "
            f"{statistics.median([r['stalled'] for r in signed]):.2f} s | {stalled} |"
        )
    print("\n".join(payload))


def _print_modules(results: list[dict]) -> None:
    print("\nHeavy modules imported by `import apps.desktop.app`:")
    for name in HEAVY_MODULES:
        loaded = any(run["modules"].get(name) for run in results)
        print(f"  {'LOADED ' if loaded else 'absent '} {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3, help="fresh processes to time")
    parser.add_argument(
        "--importtime",
        action="store_true",
        help="also capture -X importtime and print the top 20 cumulative modules",
    )
    parser.add_argument(
        "--main",
        action="store_true",
        help=(
            "also time the real startup path up to webview.create_window, "
            "with the window creation stubbed out (no window is opened)"
        ),
    )
    parser.add_argument(
        "--signed-in",
        action="store_true",
        help=(
            "also time the first state read as a signed-in CA, and again with "
            "the network stalled at its 3 s timeout"
        ),
    )
    args = parser.parse_args(argv)

    results: list[dict] = []
    print(f"Cold start benchmark — {args.runs} fresh process(es), temp LOCALAPPDATA\n")

    importtimer_stderr = ""
    if args.importtime:
        # A separate process: the top-20 list must describe the module import
        # alone, not the startup work that runs after it.
        _, importtimer_stderr = _run_child(importtime=True)

    for index in range(max(1, args.runs)):
        payload, _ = _run_child(
            measure_main=args.main, measure_signed_in=args.signed_in
        )
        results.append(payload)
        ready = payload.get("ready")
        window = f"  window ready {ready:.2f}s" if ready is not None else ""
        print(
            f"run {index + 1}: import {payload['import']:.2f}s  "
            f"construct {payload['construct']:.2f}s  "
            f"get_state {payload['get_state']:.2f}s  "
            f"total {payload['total']:.2f}s{window}"
        )
        signed = payload.get("signed_in")
        if signed:
            print(
                f"         signed-in first state: {signed['normal']:.2f}s  "
                f"with the network stalled: {signed['stalled']:.2f}s"
            )

    print()
    _print_medians(results)
    _print_modules(results)

    if args.importtime:
        entries = _parse_importtime(importtimer_stderr)
        print("\nTop 20 by cumulative import time:")
        for name, seconds in entries[:20]:
            print(f"  {seconds:7.3f} s  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
