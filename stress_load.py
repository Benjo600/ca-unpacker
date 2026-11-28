"""Intense load test for CA Unpacker.

Runs a throwaway library through volume, giant-file, concurrency, churn and
cancel scenarios, measuring wall time and peak memory and checking the
invariants that matter: every job ends, no exception escapes, packs open,
the database stays sound and settings stay readable.

Run:
    .venv\\Scripts\\python.exe stress_load.py --scenario all

Output: stress-dump/load-<timestamp>/report.json, report.html, report.csv
The real library under %LOCALAPPDATA%\\CAUnpacker is never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "stress-dump" / "corpus"
LONG_STATEMENT = ROOT / "stress-dump" / "01-banks-stress" / "HDFC_Long300_Jul2026.pdf"

TERMINAL = {"done", "failed", "cancelled", "done_with_warnings"}
ACTIVE = {"queued", "routing", "parsing", "cancel_requested"}


def human(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f} min"


class RssMonitor:
    """Sample this process's resident memory every half second."""

    def __init__(self) -> None:
        self.peak = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "RssMonitor":
        import psutil

        process = psutil.Process()

        def sample() -> None:
            while not self._stop.wait(0.5):
                try:
                    self.peak = max(self.peak, process.memory_info().rss / (1024 * 1024))
                except Exception:
                    return

        self._thread = threading.Thread(target=sample, name="rss-monitor", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def _terminal(status: str) -> bool:
    return str(status or "") in TERMINAL


def _dump_thread_stacks(tag: str) -> None:
    """Print where the worker threads are, so a silent stall is diagnosable."""
    import sys

    frames = sys._current_frames()
    for thread in threading.enumerate():
        if thread is threading.main_thread():
            continue
        frame = frames.get(thread.ident)
        if frame is None:
            continue
        print(f"--- stack {tag} thread={thread.name}", flush=True)
        print("".join(traceback.format_stack(frame)[-10:]), flush=True)


def wait_for_job(
    api,
    job_id: int,
    timeout: float = 2400.0,
    sample_ui: bool = False,
    sample_stacks: bool = False,
) -> dict:
    """Poll the bridge until a job ends. Records bridge latency when asked."""
    started = time.monotonic()
    latencies: list[float] = []
    last_status = ""
    last_dump = 0.0
    while time.monotonic() - started < timeout:
        job = api.get_job(job_id)
        if not job.get("ok"):
            raise RuntimeError(job.get("error") or "get_job failed")
        payload = job.get("job") or {}
        last_status = payload.get("status") or ""
        elapsed = time.monotonic() - started
        if sample_stacks and elapsed - last_dump >= 60:
            last_dump = elapsed
            _dump_thread_stacks(f"job {job_id} {last_status} {elapsed:.0f}s")
        if sample_ui:
            before = time.monotonic()
            api.get_state()
            latencies.append((time.monotonic() - before) * 1000)
        if _terminal(last_status):
            time.sleep(0.3)
            return {
                "status": last_status,
                "seconds": time.monotonic() - started,
                "ui_latency_ms_max": round(max(latencies), 1) if latencies else None,
                "ui_latency_ms_avg": round(sum(latencies) / len(latencies), 1) if latencies else None,
                "ui_samples": len(latencies),
            }
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} still {last_status or 'unknown'} after {timeout:.0f}s")


def pack_check(period_id: int) -> dict:
    """Validate every workbook in a period's pack folder."""
    from apps.engine.pipeline import get_period_pack

    pack = get_period_pack(period_id) or {}
    folder = Path(pack.get("path") or "")
    opened = []
    bad = []
    if pack.get("exists") and folder.is_dir():
        from openpyxl import load_workbook

        for path in sorted(folder.glob("*.xlsx")):
            try:
                book = load_workbook(path, read_only=True)
                opened.append({"file": path.name, "sheets": len(book.sheetnames)})
                book.close()
            except Exception as exc:  # a corrupt pack is a finding
                bad.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "exists": bool(pack.get("exists")),
        "folder": str(folder) if str(folder) else "",
        "row_count": int(pack.get("row_count") or 0),
        "outputs": len(pack.get("outputs") or []),
        "workbooks": opened,
        "bad_workbooks": bad,
    }


def outcome_counts(period_id: int) -> dict:
    from apps.engine.dump import list_period_files

    counts: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for row in list_period_files(period_id):
        outcome = str(row.get("parse_outcome") or "unknown")
        counts[outcome] = counts.get(outcome, 0) + 1
        kind = str(row.get("kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"outcomes": counts, "kinds": kinds}


def _corpus_files(family: str, limit: int | None = None) -> list[Path]:
    folder = CORPUS / family
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    # Mirror the intake rules: hidden names, README files and legacy .xls are
    # skipped or refused before an import starts.
    skip = {"readme.md", "readme.txt", "thumbs.db", "desktop.ini"}
    files = [
        path
        for path in files
        if not path.name.startswith(".")
        and path.name.lower() not in skip
        and path.suffix.lower() != ".xls"
    ]
    return files[:limit] if limit else files


def _bulk_paths() -> list[Path]:
    """Every unique family file (mixed folders are copies of these)."""
    return (
        _corpus_files("banks")
        + _corpus_files("invoices")
        + _corpus_files("gst")
        + _corpus_files("books")
        + _corpus_files("junk")
    )


def _mixed_paths() -> list[Path]:
    return _corpus_files("mixed")


def _small_mix(seed: int, size: int) -> list[Path]:
    """A deterministic mix for concurrency periods (no scans, no huge blobs)."""
    pools = [
        [
            p
            for p in _corpus_files("banks")
            if p.suffix.lower() != ".png" and p.stat().st_size < 5 * 1024 * 1024
        ],
        _corpus_files("invoices"),
        _corpus_files("gst"),
        _corpus_files("books"),
        [p for p in _corpus_files("junk") if p.stat().st_size < 5 * 1024 * 1024],
    ]
    picked: list[Path] = []
    index = 0
    while len(picked) < size:
        pool = pools[index % len(pools)]
        if pool:
            picked.append(pool[(seed * 7 + index * 3) % len(pool)])
        index += 1
    return picked


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_bulk(api, report: dict) -> None:
    """400 files in one period, then 200 mixed files in a second period."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period
    from apps.engine.dump import list_period_files

    result: dict = {"name": "bulk_600", "details": {}}

    client = create_client("Bulk Files Client")
    period = create_period(client["id"], "Jan 2027")
    paths = _bulk_paths()
    result["details"]["batch_1_files"] = len(paths)
    with RssMonitor() as monitor:
        started = time.monotonic()
        first = api.start_dump(period["id"], [str(p) for p in paths])
        if not first.get("ok"):
            raise RuntimeError(first.get("error") or "start_dump refused the 400-file batch")
        result["details"]["batch_1_job"] = wait_for_job(
            api, first["job_id"], sample_ui=True, sample_stacks=True
        )
        result["details"]["batch_1_seconds"] = time.monotonic() - started
        result["details"]["batch_1_peak_rss_mb"] = round(monitor.peak, 1)

        mixed_client = create_client("Mixed Month Client")
        mixed_period = create_period(mixed_client["id"], "Feb 2027")
        mixed = _mixed_paths()
        result["details"]["batch_2_files"] = len(mixed)
        started2 = time.monotonic()
        second = api.start_dump(mixed_period["id"], [str(p) for p in mixed])
        if not second.get("ok"):
            raise RuntimeError(second.get("error") or "start_dump refused the 200-file batch")
        result["details"]["batch_2_job"] = wait_for_job(
            api, second["job_id"], sample_ui=True, sample_stacks=True
        )
        result["details"]["batch_2_seconds"] = time.monotonic() - started2
        result["details"]["peak_rss_mb"] = round(monitor.peak, 1)

    result["details"]["batch_1_files_stored"] = len(list_period_files(period["id"]))
    result["details"]["batch_2_files_stored"] = len(list_period_files(mixed_period["id"]))
    result["details"]["batch_1_outcomes"] = outcome_counts(period["id"])
    result["details"]["batch_2_outcomes"] = outcome_counts(mixed_period["id"])
    result["details"]["batch_1_pack"] = pack_check(period["id"])
    result["details"]["batch_2_pack"] = pack_check(mixed_period["id"])
    report["scenarios"].append(result)


def scenario_limit(api, report: dict) -> None:
    """401 files must be refused cleanly, with nothing copied."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period
    from apps.engine.dump import list_period_files

    client = create_client("Limit Client")
    period = create_period(client["id"], "Mar 2027")
    paths = _bulk_paths() + _corpus_files("mixed", 3)
    result = {"name": "401_file_limit", "details": {"paths": len(paths)}}
    started = time.monotonic()
    response = api.start_dump(period["id"], [str(p) for p in paths])
    result["details"]["response_ok"] = bool(response.get("ok"))
    result["details"]["error"] = response.get("error") or ""
    result["details"]["files_stored"] = len(list_period_files(period["id"]))
    result["details"]["seconds"] = round(time.monotonic() - started, 2)
    if response.get("ok"):
        # Never leave a load job running just because an assertion fired.
        try:
            api.cancel_job(response["job_id"])
            wait_for_job(api, response["job_id"], timeout=120)
        except Exception:
            pass
        raise AssertionError("401 files were accepted; the guard did not fire")
    if result["details"]["files_stored"]:
        raise AssertionError("files were copied before the 401 refusal")
    report["scenarios"].append(result)


def scenario_giants(api, report: dict) -> None:
    """One huge document at a time: GST 5,000 invoices, 1.5 MB Tally, 50 MB blob, 300-row statement."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period
    from apps.engine.dump import list_period_files

    cases = [
        ("gstr_5000", CORPUS / "gst" / "GSTR-2B_large_5000.json", "Apr 2027"),
        ("tally_1_5mb", CORPUS / "books" / "Tally_Daybook_tally_xml_001.xml", "May 2027"),
        ("blob_50mb", CORPUS / "junk" / "01-binary" / "large_blob_50mb.bin", "Jun 2027"),
    ]
    if LONG_STATEMENT.is_file():
        cases.append(("statement_300_rows", LONG_STATEMENT, "Jul 2027"))

    client = create_client("Giant Files Client")
    result = {"name": "giant_files", "details": {"cases": []}}
    for label, path, period_label in cases:
        if not path.is_file():
            result["details"]["cases"].append({"case": label, "skipped": "missing"})
            continue
        period = create_period(client["id"], period_label)
        with RssMonitor() as monitor:
            started = time.monotonic()
            response = api.start_dump(period["id"], [str(path)])
            if not response.get("ok"):
                raise RuntimeError(f"{label}: {response.get('error')}")
            job = wait_for_job(api, response["job_id"])
        files = list_period_files(period["id"])
        rows = sum(int(row.get("parse_row_count") or 0) for row in files)
        result["details"]["cases"].append(
            {
                "case": label,
                "file_mb": round(path.stat().st_size / (1024 * 1024), 2),
                "seconds": round(time.monotonic() - started, 1),
                "peak_rss_mb": round(monitor.peak, 1),
                "job": job,
                "rows": rows,
                "outcomes": outcome_counts(period["id"])["outcomes"],
            }
        )
    report["scenarios"].append(result)


def scenario_concurrency(api, report: dict) -> None:
    """Six periods importing at once through the real engine (not the bridge)."""
    from apps.engine.clients import create_client
    from apps.engine.dump import ingest_paths, list_period_files, start_job
    from apps.engine.periods import create_period

    result = {"name": "concurrent_6_periods", "details": {"periods": []}}
    client = create_client("Concurrent Client")
    jobs: list[tuple[str, int, int, list[Path]]] = []
    for index in range(6):
        period = create_period(client["id"], f"{['Aug','Sep','Oct','Nov','Dec'][index]} 2027" if index < 5 else "Jan 2028")
        paths = _small_mix(index + 1, 40)
        jobs.append((period["label"], period["id"], start_job(period["id"])["id"], paths))

    errors: list[str] = []
    outcomes: dict[int, dict] = {}
    lock = threading.Lock()

    def run(label: str, period_id: int, job_id: int, paths: list[Path]) -> None:
        try:
            started = time.monotonic()
            ingest_paths(job_id, [str(p) for p in paths])
            with lock:
                outcomes[job_id] = {
                    "period": label,
                    "seconds": round(time.monotonic() - started, 1),
                    "files": len(list_period_files(period_id)),
                }
        except Exception as exc:
            with lock:
                errors.append(f"{label}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")

    started = time.monotonic()
    with RssMonitor() as monitor:
        threads = [threading.Thread(target=run, args=item, name=f"load-{item[0]}") for item in jobs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1800)
    wall = time.monotonic() - started

    from apps.engine.db import Job, get_session

    session = get_session()
    try:
        statuses = {
            job.id: job.status for job in session.query(Job).filter(Job.id.in_([j[2] for j in jobs])).all()
        }
    finally:
        session.close()

    result["details"].update(
        {
            "wall_seconds": round(wall, 1),
            "peak_rss_mb": round(monitor.peak, 1),
            "errors": errors,
            "jobs": statuses,
            "outcomes": outcomes,
            "packs": [pack_check(item[1]) for item in jobs],
        }
    )
    if errors:
        raise AssertionError(f"{len(errors)} concurrent import(s) raised: {errors[0][:300]}")
    report["scenarios"].append(result)


def scenario_churn(api, report: dict) -> None:
    """Rebuild the same period's pack five times; rows and settings must stay stable."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period
    from apps.engine.dump import list_period_files

    client = create_client("Churn Client")
    period = create_period(client["id"], "Feb 2028")
    paths = _small_mix(11, 60)
    first = api.start_dump(period["id"], [str(p) for p in paths])
    if not first.get("ok"):
        raise RuntimeError(first.get("error"))
    first_job = wait_for_job(api, first["job_id"])
    baseline_files = len(list_period_files(period["id"]))
    baseline_rows = sum(int(row.get("parse_row_count") or 0) for row in list_period_files(period["id"]))

    runs = []
    for _ in range(4):
        started = time.monotonic()
        response = api.reparse_period(period["id"])
        if not response.get("ok"):
            raise RuntimeError(response.get("error"))
        job = wait_for_job(api, response["job_id"])
        files = list_period_files(period["id"])
        rows = sum(int(row.get("parse_row_count") or 0) for row in files)
        runs.append(
            {
                "seconds": round(time.monotonic() - started, 1),
                "job": job,
                "files": len(files),
                "rows": rows,
            }
        )
    result = {
        "name": "reparse_churn",
        "details": {
            "initial_job": first_job,
            "baseline_files": baseline_files,
            "baseline_rows": baseline_rows,
            "runs": runs,
            "pack": pack_check(period["id"]),
        },
    }
    if any(run["files"] != baseline_files or run["rows"] != baseline_rows for run in runs):
        raise AssertionError("file or row counts drifted across re-parses")
    report["scenarios"].append(result)


def scenario_cancel(api, report: dict) -> None:
    """Cancel a 300-file import, then prove the period still works."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period
    from apps.engine.dump import list_period_files

    client = create_client("Cancel Client")
    period = create_period(client["id"], "Mar 2028")
    paths = _bulk_paths()[:300]
    started = time.monotonic()
    response = api.start_dump(period["id"], [str(p) for p in paths])
    if not response.get("ok"):
        raise RuntimeError(response.get("error"))
    time.sleep(1.0)
    cancelled = api.cancel_job(response["job_id"])
    job = wait_for_job(api, response["job_id"], timeout=300)
    after = api.start_dump(period["id"], [str(p) for p in _small_mix(21, 5)])
    if not after.get("ok"):
        raise RuntimeError(f"period unusable after cancel: {after.get('error')}")
    after_job = wait_for_job(api, after["job_id"], timeout=600)
    result = {
        "name": "cancel_mid_import",
        "details": {
            "cancel_response": cancelled,
            "cancelled_job": job,
            "seconds_before_cancel": round(time.monotonic() - started - job["seconds"], 1),
            "files_after_cancel": len(list_period_files(period["id"])),
            "recovery_job": after_job,
            "recovery_outcomes": outcome_counts(period["id"]),
        },
    }
    if job["status"] not in {"cancelled", "done", "failed"}:
        raise AssertionError(f"unexpected status after cancel: {job['status']}")
    report["scenarios"].append(result)


def scenario_scale(api, report: dict) -> None:
    """100 clients at once: the desk payload and dashboard must stay fast."""
    from apps.engine.clients import create_client
    from apps.engine.periods import create_period

    started = time.monotonic()
    for index in range(100):
        client = create_client(f"Scale Client {index + 1:03d}")
        create_period(client["id"], "Apr 2028")
    created_in = time.monotonic() - started

    latencies = []
    for _ in range(5):
        before = time.monotonic()
        state = api.get_state()
        latencies.append((time.monotonic() - before) * 1000)
    before = time.monotonic()
    dashboard = api.get_dashboard()
    dashboard_ms = (time.monotonic() - before) * 1000
    result = {
        "name": "100_clients",
        "details": {
            "clients_created_seconds": round(created_in, 1),
            "clients_payload": len((state or {}).get("clients") or []),
            "state_latency_ms": [round(value, 1) for value in latencies],
            "dashboard_ok": bool(dashboard.get("ok")),
            "dashboard_latency_ms": round(dashboard_ms, 1),
        },
    }
    if len((state or {}).get("clients") or []) < 100:
        raise AssertionError("client list is missing rows")
    report["scenarios"].append(result)


def final_checks(report: dict) -> None:
    """Database, settings, stuck jobs and disk use after every scenario."""
    from sqlalchemy import text

    from apps.engine.db import Job, get_session
    from apps.engine.library import get_library_path
    from apps.engine.settings import load_settings, settings_path

    session = get_session()
    try:
        integrity = session.execute(text("PRAGMA integrity_check")).scalar()
        stuck = (
            session.query(Job)
            .filter(Job.status.in_(tuple(ACTIVE)))
            .count()
        )
        job_total = session.query(Job).count()
    finally:
        session.close()

    settings_ok = True
    try:
        json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        settings_ok = False

    root = get_library_path()
    size_mb = 0.0
    files = 0
    for path in root.rglob("*"):
        if path.is_file():
            files += 1
            try:
                size_mb += path.stat().st_size / (1024 * 1024)
            except OSError:
                pass

    report["final"] = {
        "db_integrity": integrity,
        "settings_parses": settings_ok,
        "stuck_jobs": stuck,
        "jobs_total": job_total,
        "library_files": files,
        "library_mb": round(size_mb, 1),
    }
    if str(integrity).lower() != "ok":
        raise AssertionError(f"database integrity check said {integrity!r}")
    if not settings_ok:
        raise AssertionError("settings.json is not valid JSON after the load test")
    if stuck:
        raise AssertionError(f"{stuck} job(s) left in an active state")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_report(report: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    rows = []
    for scenario in report["scenarios"]:
        details = scenario.get("details") or {}
        seconds = details.get("batch_1_seconds")
        if seconds is None:
            seconds = details.get("wall_seconds")
        if seconds is None and details.get("runs"):
            seconds = sum(item.get("seconds") or 0 for item in details["runs"])
        rows.append(
            {
                "scenario": scenario["name"],
                "seconds": round(seconds, 1) if isinstance(seconds, (int, float)) else "",
                "peak_rss_mb": details.get("peak_rss_mb") or details.get("batch_1_peak_rss_mb") or "",
                "error": scenario.get("error") or "",
            }
        )
    with (out / "report.csv").open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=["scenario", "seconds", "peak_rss_mb", "error"])
        writer.writeheader()
        writer.writerows(rows)

    esc = lambda value: (
        str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    body = []
    for scenario in report["scenarios"]:
        status = "FAIL" if scenario.get("error") else "PASS"
        body.append(
            f"<h2>{esc(scenario['name'])} <span class='{status.lower()}'>{status}</span></h2>"
        )
        if scenario.get("error"):
            body.append(f"<pre class='error'>{esc(scenario['error'])}</pre>")
        details = scenario.get("details") or {}
        body.append("<table>")
        for key, value in details.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            body.append(f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>")
        body.append("</table>")
    final = report.get("final") or {}
    html = f"""<!doctype html><meta charset="utf-8">
<title>CA Unpacker load test</title>
<style>
body{{font:14px/1.5 Segoe UI,Arial;margin:32px;max-width:1100px;color:#1f1f1d}}
h1{{font:600 24px Georgia,serif}} h2{{font:600 18px Georgia,serif;margin-top:28px}}
table{{border-collapse:collapse;width:100%;margin:8px 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #d8d5cc;vertical-align:top}}
th{{width:240px;color:#6b6b66;font-weight:600}}
.pass{{color:#2a6b3f}} .fail{{color:#c15f3c}}
pre.error{{background:#fbf1ec;padding:12px;white-space:pre-wrap}}
</style>
<h1>CA Unpacker load test</h1>
<p>Generated {esc(report['started'])} - {esc(human(report['seconds']))} wall time.</p>
<h2>Final checks</h2><table>
{''.join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k, v in final.items())}
</table>
{''.join(body)}
"""
    (out / "report.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


SCENARIOS = {
    "bulk": scenario_bulk,
    "limit": scenario_limit,
    "giants": scenario_giants,
    "concurrency": scenario_concurrency,
    "churn": scenario_churn,
    "cancel": scenario_cancel,
    "scale": scenario_scale,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--out", default="")
    parser.add_argument("--keep", action="store_true", help="keep the temporary library")
    args = parser.parse_args()

    if not CORPUS.is_dir():
        print("stress-dump/corpus missing; run build_corpus.py first")
        return 2

    temp = tempfile.mkdtemp(prefix="ca-load-")
    os.environ["LOCALAPPDATA"] = temp
    os.environ["CA_UNPACKER_DEV"] = "1"
    os.environ["CA_UNPACKER_REQUIRE_AUTH"] = "0"

    from apps.engine.db import reset_engine
    from apps.engine.license import activate_key
    from apps.engine.settings import save_settings
    from apps.desktop.app import DesktopApi

    reset_engine()
    try:
        activate_key("PRO-TEST")
    except Exception:
        save_settings({"license_plan": "pro", "license_key": "PRO-TEST"})

    started_at = datetime.now()
    report: dict = {
        "started": started_at.isoformat(timespec="seconds"),
        "corpus": str(CORPUS),
        "scenarios": [],
        "seconds": 0.0,
    }
    clock = time.monotonic()
    api = DesktopApi()
    chosen = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    try:
        for name in chosen:
            print(f"== {name}", flush=True)
            before = time.monotonic()
            try:
                SCENARIOS[name](api, report)
                print(f"   done in {human(time.monotonic() - before)}", flush=True)
            except Exception as exc:
                report["scenarios"].append(
                    {
                        "name": name,
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                )
                print(f"   FAILED: {type(exc).__name__}: {exc}", flush=True)
        try:
            final_checks(report)
        except Exception as exc:
            report["final"] = {"error": f"{type(exc).__name__}: {exc}"}
        report["seconds"] = round(time.monotonic() - clock, 1)
        stamp = started_at.strftime("%Y%m%d-%H%M%S")
        out = Path(args.out) if args.out else ROOT / "stress-dump" / f"load-{stamp}"
        report["out"] = str(out)
        write_report(report, out)
        print(json.dumps(report.get("final") or {}, indent=2))
        print(f"report: {out}")
        failed = [s for s in report["scenarios"] if s.get("error")]
        print(f"scenarios: {len(report['scenarios']) - len(failed)} passed, {len(failed)} failed")
        return 1 if failed else 0
    finally:
        reset_engine()
        if not args.keep:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
