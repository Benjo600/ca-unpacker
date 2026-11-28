"""Feed the generated stress corpus through the real engine and grade it.

Every family folder and every client-month folder in ``--out`` becomes one
period, exactly the way the desktop app would process it.  Each file is then
compared against ``manifest.json``: the kind the generator intended, the number
of rows it wrote, the totals it printed, the balance status and the flags it
deliberately triggered.

The run is sandboxed: ``LOCALAPPDATA`` points at a throw-away folder for the
whole run, so the real library (``%LOCALAPPDATA%\\CAUnpacker``) is never touched.

Usage
-----
    .venv\\Scripts\\python.exe corpus_run.py --profile smoke
    .venv\\Scripts\\python.exe corpus_run.py --family banks,invoices --limit 50
    .venv\\Scripts\\python.exe corpus_run.py --no-isolate   # single process, debugging

Exit code is non-zero on any crash, hang, or manifest mismatch.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CANONICAL_LABEL = "Jul 2026"
SANDBOX_PREFIX = "ca-corpus-"
TOLERANCE = 0.0101

PASS, FAIL, SKIP, WARN = "pass", "fail", "skip", "warn"


# ---------------------------------------------------------------------------
# Engine worker (runs in a child process, or in-process with --no-isolate)
# ---------------------------------------------------------------------------


def run_scenario(root: Path, scenario: str, files: list[str], label: str = CANONICAL_LABEL) -> dict:
    """Ingest and parse one folder through the real engine.

    Returns the raw engine observations; the caller compares them with the
    manifest so this stays free of expectations.
    """
    result: dict = {
        "scenario": scenario,
        "files": [],
        "capabilities": {},
        "job_status": None,
        "error": None,
        "elapsed_s": 0.0,
        "skipped_duplicates": [],
        "ocr_available": False,
    }
    started = time.perf_counter()
    from apps.engine.clients import create_client
    from apps.engine.db import reset_engine
    from apps.engine.dump import get_job, ingest_paths, list_period_files, start_job
    from apps.engine.license import activate_key
    from apps.engine.periods import create_period
    from apps.engine.pipeline import get_period_pack, get_period_preview

    try:
        from apps.engine.ocr import ocr_available

        result["ocr_available"] = bool(ocr_available())
    except Exception:
        result["ocr_available"] = False

    os.environ["CA_UNPACKER_DEV"] = "1"
    reset_engine()
    try:
        activate_key("PRO-TEST")  # unlimited files, this sandbox only
        client = create_client(f"Corpus {scenario}"[:120])
        period = create_period(client["id"], label)
        job = start_job(period["id"])
        job_id = job["id"]
        paths = [str(root / name) for name in files]
        try:
            ingest_paths(job_id, paths)
        except Exception as exc:  # a job-level failure is a finding, not a crash here
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["traceback"] = traceback.format_exc()
        job_row = get_job(job_id) or {}
        result["job_status"] = job_row.get("status")
        result["skipped_duplicates"] = job_row.get("skipped_duplicates") or []
        stored = list_period_files(period["id"])
        preview = get_period_preview(period["id"], limit=1_000_000)
        pack = get_period_pack(period["id"]) or {}
        bank_status = {
            str(item.get("filename") or ""): item.get("status")
            for item in (pack.get("files") or [])
        }
        rows_by_file = {
            item.get("file_id"): item for item in (preview.get("files") or [])
        }
        previous_stamp = None
        for entry in stored:
            stamp_text = entry.get("processed_at")
            stamp = None
            if stamp_text:
                try:
                    stamp = datetime.fromisoformat(stamp_text)
                except ValueError:
                    stamp = None
            approx_ms = None
            if stamp is not None and previous_stamp is not None:
                approx_ms = max(0.0, (stamp - previous_stamp).total_seconds() * 1000.0)
            if stamp is not None:
                previous_stamp = stamp
            group = rows_by_file.get(entry.get("id")) or {}
            result["files"].append(
                {
                    "name": entry.get("original_name"),
                    "file_id": entry.get("id"),
                    "kind": entry.get("kind"),
                    "detected_kind": entry.get("detected_kind"),
                    "outcome": entry.get("parse_outcome"),
                    "reason_code": entry.get("parse_reason_code"),
                    "reason": entry.get("classify_reason"),
                    "rows": entry.get("parse_row_count"),
                    "line_items": len(group.get("preview") or []),
                    "payload_rows": group.get("preview") or [],
                    "flags": entry.get("parse_warnings") or [],
                    "balance_status": bank_status.get(str(entry.get("original_name"))),
                    "needs_password": bool(entry.get("needs_password")),
                    "duplicate_content": bool(entry.get("duplicate_content")),
                    "processed_at": stamp_text,
                    "approx_ms": approx_ms,
                }
            )
    except Exception as exc:  # the scenario itself blew up
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    finally:
        reset_engine()
        result["elapsed_s"] = round(time.perf_counter() - started, 2)
    return result


def _worker(payload_path: str, result_path: str) -> None:
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    try:
        result = run_scenario(
            Path(payload["root"]), payload["scenario"], payload["files"], payload["label"]
        )
    except BaseException as exc:  # never leave the parent without a result
        result = {
            "scenario": payload.get("scenario"),
            "files": [],
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "elapsed_s": 0.0,
            "ocr_available": False,
            "job_status": None,
            "skipped_duplicates": [],
        }
    Path(result_path).write_text(json.dumps(result), encoding="utf-8")


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def _sum_totals(entry: dict, actual_rows: list[dict]) -> dict:
    kind = entry["kind"]

    def number(row: dict, key: str) -> float:
        value = row.get(key)
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    if kind in {"bank", "sap"}:
        return {
            "debit": sum(number(row, "debit") for row in actual_rows),
            "credit": sum(number(row, "credit") for row in actual_rows),
        }
    if kind == "gstr_3b":
        return {"taxable": sum(number(row, "taxable") for row in actual_rows)}
    if kind == "invoice":
        # The preview carries the invoice summary row *and* its line items, so
        # only the summary's own fields are summed here.
        return {
            "value": sum(number(row, "invoice_value") for row in actual_rows),
            "taxable": sum(number(row, "taxable_value") for row in actual_rows),
        }
    if kind in {"gstr_1", "gstr_2b"}:
        return {
            "value": sum(number(row, "invoice_value") for row in actual_rows),
            "taxable": sum(number(row, "taxable") for row in actual_rows),
        }
    if kind in {"tally", "zoho"}:
        return {
            "value": sum(number(row, "invoice_value") for row in actual_rows),
            "taxable": sum(number(row, "taxable_value") for row in actual_rows),
        }
    return {}


def grade(entry: dict, actual: dict | None, skipped_names: set[str], ocr_available: bool,
          refused: bool = False) -> dict:
    """Compare one manifest entry with what the engine did."""
    expected = {
        "kind": entry.get("kind"),
        "outcome": entry.get("outcome"),
        "rows": entry.get("rows"),
        "line_items": entry.get("line_items"),
        "totals": entry.get("totals") or {},
        "balance_status": entry.get("balance_status"),
        "flags": entry.get("flags") or [],
        "requires": entry.get("requires") or [],
    }
    name = Path(entry["path"]).name
    row = {
        "scenario": str(Path(entry["path"]).parent).replace("\\", "/"),
        "path": entry["path"],
        "file": name,
        "family": entry.get("family"),
        "notes": entry.get("notes") or "",
        "expected_kind": expected["kind"],
        "expected_outcome": expected["outcome"],
        "expected_rows": "" if expected["rows"] is None else expected["rows"],
        "expected_line_items": "" if expected["line_items"] is None else expected["line_items"],
        "expected_totals": json.dumps(expected["totals"], sort_keys=True),
        "expected_balance": expected["balance_status"] or "",
        "expected_flags": " ".join(expected["flags"]),
        "actual_kind": "",
        "actual_outcome": "",
        "actual_rows": "",
        "actual_line_items": "",
        "actual_totals": "",
        "actual_balance": "",
        "actual_flags": "",
        "approx_ms": "",
        "result": FAIL,
        "detail": "",
    }
    problems: list[str] = []
    advisory_notes: list[str] = []

    if expected["outcome"] == "skipped_duplicate":
        if name in skipped_names:
            row["actual_outcome"] = "skipped_duplicate"
            row["result"] = PASS
        else:
            row["detail"] = "expected the intake to skip this as a duplicate, but it was not skipped"
        return row

    if expected["outcome"] == "skipped_by_name":
        if actual is None:
            row["actual_outcome"] = "skipped_by_name"
            row["result"] = PASS
            row["detail"] = "intake skips dot-files, as expected"
        else:
            row["detail"] = "expected the intake to skip this hidden file, but it was stored"
        return row

    if expected["outcome"] == "rejected_selection":
        if actual is None and refused:
            row["actual_outcome"] = "rejected_selection"
            row["result"] = PASS
            row["detail"] = "engine refused the folder with its user-facing message (handled)"
        elif actual is not None:
            row["detail"] = "expected the engine to refuse this legacy .xls, but it was stored"
        else:
            row["detail"] = "the folder failed for a different reason; see the crash section"
        return row

    if actual is None:
        row["detail"] = "the engine stored no file with this name"
        return row

    row["actual_kind"] = actual.get("kind") or ""
    row["actual_outcome"] = actual.get("outcome") or ""
    row["actual_rows"] = actual.get("rows") if actual.get("rows") is not None else ""
    payload_rows = actual.get("payload_rows") or []
    if actual.get("kind") == "invoice":
        # Preview holds the invoice row plus its line items.
        line_items = max(0, len(payload_rows) - int(actual.get("rows") or 0))
    else:
        line_items = len(payload_rows)
    row["actual_line_items"] = line_items
    row["actual_balance"] = actual.get("balance_status") or ""
    row["actual_flags"] = " ".join(actual.get("flags") or [])
    row["approx_ms"] = "" if actual.get("approx_ms") is None else round(actual["approx_ms"], 1)

    missing_requirements = [item for item in expected["requires"] if item == "ocr" and not ocr_available]

    def check(ok: bool, message: str, advisory_ok: bool = False) -> None:
        if ok:
            return
        if missing_requirements:
            advisory_notes.append(message + " (not asserted: no OCR engine)")
        elif entry.get("advisory"):
            advisory_notes.append(message)
        else:
            problems.append(message)

    check(row["actual_kind"] == expected["kind"], f"kind {row['actual_kind']!r} != {expected['kind']!r}")
    if expected["outcome"]:
        check(
            row["actual_outcome"] == expected["outcome"],
            f"outcome {row['actual_outcome']!r} != {expected['outcome']!r}",
        )
    if expected["rows"] is not None and not missing_requirements:
        check(
            int(actual.get("rows") or 0) == int(expected["rows"]),
            f"rows {actual.get('rows')} != {expected['rows']}",
        )
    if expected["line_items"] is not None and not missing_requirements:
        check(
            int(line_items) == int(expected["line_items"]),
            f"line items {line_items} != {expected['line_items']}",
        )

    actual_totals = {}
    if expected["totals"] and not missing_requirements:
        actual_totals = _sum_totals(entry, payload_rows)
        for key, expected_value in expected["totals"].items():
            difference = abs(float(actual_totals.get(key, 0.0)) - float(expected_value))
            check(
                difference <= TOLERANCE,
                f"{key} total {actual_totals.get(key, 0.0):.2f} != {float(expected_value):.2f}",
            )
        row["actual_totals"] = json.dumps(
            {key: round(actual_totals.get(key, 0.0), 2) for key in expected["totals"]}, sort_keys=True
        )

    if expected["balance_status"] and not missing_requirements:
        check(
            row["actual_balance"] == expected["balance_status"],
            f"balance {row['actual_balance']!r} != {expected['balance_status']!r}",
        )

    actual_flags = set(actual.get("flags") or [])
    missing_flags = [flag for flag in expected["flags"] if flag not in actual_flags]
    check(not missing_flags, f"missing flags {missing_flags}")

    if problems:
        row["detail"] = "; ".join(problems)
        row["result"] = FAIL
    elif advisory_notes:
        row["detail"] = "; ".join(advisory_notes)
        row["result"] = SKIP if missing_requirements else WARN
    else:
        row["result"] = PASS
    return row


# ---------------------------------------------------------------------------
# Selection, execution, reporting
# ---------------------------------------------------------------------------


def load_manifest(root: Path) -> dict:
    path = root / "manifest.json"
    if not path.exists():
        raise SystemExit(f"No manifest in {root}. Run build_corpus.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_groups(manifest: dict, families: list[str] | None, limit: int | None,
                    matches: list[str] | None = None) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for entry in sorted(manifest["files"], key=lambda item: item["path"]):
        if families and entry.get("family") not in families:
            continue
        if matches and not any(token.lower() in entry["path"].lower() for token in matches):
            continue
        folder = str(Path(entry["path"]).parent).replace("\\", "/")
        groups.setdefault(folder, []).append(entry)
    selected = sorted(groups.items())
    if limit is None:
        return selected
    # --limit caps the total number of files, taking whole folders in order.
    capped: list[tuple[str, list[dict]]] = []
    remaining = limit
    for folder, entries in selected:
        if remaining <= 0:
            break
        take = entries[:remaining]
        if take:
            capped.append((folder, take))
        remaining -= len(take)
    return capped


def execute(
    root: Path,
    groups: list[tuple[str, list[dict]]],
    sandbox: Path,
    *,
    isolate: bool,  # noqa: A002 - mirrors the CLI flag name
    timeout: float,
    label: str = CANONICAL_LABEL,
) -> tuple[list[dict], list[dict], dict]:
    """Run every folder; return (graded rows, crashes, capabilities)."""
    os.environ["LOCALAPPDATA"] = str(sandbox)
    os.environ["CA_UNPACKER_DEV"] = "1"
    graded: list[dict] = []
    crashes: list[dict] = []
    capabilities: dict = {}

    for scenario, entries in groups:
        files = [entry["path"] for entry in entries]
        print(f"== {scenario} ({len(files)} files)", flush=True)
        started = time.perf_counter()
        if isolate:
            payload_file = sandbox / "worker-payload.json"
            result_file = sandbox / "worker-result.json"
            payload_file.write_text(
                json.dumps({"root": str(root), "scenario": scenario, "files": files, "label": label}),
                encoding="utf-8",
            )
            result_file.unlink(missing_ok=True)
            process = multiprocessing.get_context("spawn").Process(
                target=_worker, args=(str(payload_file), str(result_file))
            )
            process.start()
            process.join(timeout)
            if process.is_alive():
                process.terminate()
                process.join(10)
                crashes.append(
                    {
                        "scenario": scenario,
                        "error": f"timeout: no result after {timeout:.0f}s",
                        "files": files,
                        "severity": "hang",
                    }
                )
                for entry in entries:
                    graded.append(grade(entry, None, set(), bool(capabilities.get("ocr"))))
                continue
            if not result_file.exists():
                crashes.append(
                    {
                        "scenario": scenario,
                        "error": f"worker exited with code {process.exitcode} and wrote no result",
                        "files": files,
                        "severity": "crash",
                    }
                )
                for entry in entries:
                    graded.append(grade(entry, None, set(), bool(capabilities.get("ocr"))))
                continue
            result = json.loads(result_file.read_text(encoding="utf-8"))
        else:
            result = run_scenario(root, scenario, files, label)
        capabilities["ocr"] = bool(result.get("ocr_available"))
        elapsed = result.get("elapsed_s") or (time.perf_counter() - started)
        print(
            f"   job={result.get('job_status')} files={len(result.get('files') or [])} "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        if result.get("error"):
            message = str(result["error"])
            handled = any(
                token in message
                for token in ("Legacy .xls", "Choose at most", "no longer exists", "not supported")
            )
            crashes.append(
                {
                    "scenario": scenario,
                    "error": message,
                    "traceback": result.get("traceback") or "",
                    "files": files,
                    "severity": "refused" if handled else "crash",
                }
            )
        skipped = {
            str(item.get("name")) for item in (result.get("skipped_duplicates") or []) if isinstance(item, dict)
        }
        by_name = {row.get("name"): row for row in (result.get("files") or [])}
        refused = any(
            item["scenario"] == scenario and item.get("severity") == "refused" for item in crashes
        )
        for entry in entries:
            name = Path(entry["path"]).name
            graded.append(
                grade(entry, by_name.get(name), skipped, bool(result.get("ocr_available")), refused)
            )
    return graded, crashes, capabilities


def write_reports(root: Path, profile: str, graded: list[dict], crashes: list[dict], capabilities: dict) -> Path:
    csv_path = root / "corpus_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(graded[0].keys()) if graded else ["path"])
        writer.writeheader()
        for row in graded:
            writer.writerow(row)

    counts: dict[str, int] = {}
    for row in graded:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
    failures = [row for row in graded if row["result"] == FAIL]
    warnings = [row for row in graded if row["result"] == WARN]
    skipped = [row for row in graded if row["result"] == SKIP]
    hard_crashes = [item for item in crashes if item.get("severity") != "refused"]
    refusals = [item for item in crashes if item.get("severity") == "refused"]
    slowest = sorted(
        (row for row in graded if row["approx_ms"] not in ("", None)),
        key=lambda row: float(row["approx_ms"]),
        reverse=True,
    )[:20]

    def table(rows: list[dict]) -> str:
        if not rows:
            return "<p class='none'>None.</p>"
        body = "".join(
            "<tr class='{cls}'>"
            "<td class='path'>{path}</td>"
            "<td>{family}</td>"
            "<td>{ek}</td><td>{ak}</td>"
            "<td class='num'>{er}</td><td class='num'>{ar}</td>"
            "<td class='num' nowrap>{et}</td><td class='num' nowrap>{at}</td>"
            "<td>{eb}</td><td>{ab}</td>"
            "<td>{ef}</td><td>{af}</td>"
            "<td>{detail}</td>"
            "</tr>".format(
                cls=html.escape(row["result"]),
                path=html.escape(row["path"]),
                family=html.escape(str(row["family"])),
                ek=html.escape(str(row["expected_kind"])),
                ak=html.escape(str(row["actual_kind"])),
                er=html.escape(str(row["expected_rows"])),
                ar=html.escape(str(row["actual_rows"])),
                et=html.escape(row["expected_totals"] or ""),
                at=html.escape(row["actual_totals"] or ""),
                eb=html.escape(str(row["expected_balance"])),
                ab=html.escape(str(row["actual_balance"])),
                ef=html.escape(row["expected_flags"] or ""),
                af=html.escape(row["actual_flags"] or ""),
                detail=html.escape(row["detail"] or ""),
            )
            for row in rows
        )
        return (
            "<table><thead><tr><th>File</th><th>Family</th><th>Kind</th><th>Actual</th>"
            "<th>Rows</th><th>Actual</th><th>Totals</th><th>Actual</th>"
            "<th>Balance</th><th>Actual</th><th>Flags</th><th>Actual</th><th>Detail</th>"
            "</tr></thead><tbody>" + body + "</tbody></table>"
        )

    crash_html = ""
    for item in crashes:
        crash_html += (
            f"<h3>{html.escape(item['scenario'])}</h3>"
            f"<pre>{html.escape(item.get('error') or '')}</pre>"
            f"<pre>{html.escape(item.get('traceback') or '')}</pre>"
        )

    html_path = root / "corpus_report.html"
    html_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Stress corpus run — {html.escape(profile)}</title>
<style>
 body {{ font: 13px/1.45 system-ui, Segoe UI, sans-serif; margin: 24px; color: #16202a; }}
 h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 15px; margin-top: 28px; }}
 .sub {{ color: #55636f; margin-bottom: 18px; }}
 .cards {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }}
 .card {{ background: #f2f5f8; border: 1px solid #dfe6ec; border-radius: 8px; padding: 10px 16px; min-width: 100px; }}
 .card .n {{ font-size: 22px; font-weight: 650; }}
 .card .l {{ color: #55636f; text-transform: uppercase; letter-spacing: .04em; font-size: 11px; }}
 .card.pass .n {{ color: #1c7c54; }} .card.fail .n {{ color: #b3261e; }}
 .card.warn .n {{ color: #8a5a00; }} .card.skip .n {{ color: #55636f; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border-bottom: 1px solid #e6ebf0; padding: 5px 8px; text-align: left; vertical-align: top; }}
 th {{ background: #fff; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #55636f; }}
 td.path {{ font-family: ui-monospace, Consolas, monospace; font-size: 12px; }}
 td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
 tr.fail td {{ background: #fdf2f1; }}
 tr.warn td {{ background: #fdf8ec; }}
 .none {{ color: #55636f; font-style: italic; }}
 pre {{ background: #fdf2f1; padding: 10px; overflow: auto; font-size: 12px; }}
</style></head><body>
<h1>Stress corpus run</h1>
<div class="sub">Profile <b>{html.escape(profile)}</b> · {len(graded)} files ·
OCR engine: <b>{'yes' if capabilities.get('ocr') else 'no'}</b> ·
generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
<div class="cards">
 <div class="card pass"><div class="n">{counts.get(PASS, 0)}</div><div class="l">pass</div></div>
 <div class="card fail"><div class="n">{counts.get(FAIL, 0)}</div><div class="l">fail</div></div>
 <div class="card warn"><div class="n">{counts.get(WARN, 0)}</div><div class="l">advisory</div></div>
 <div class="card skip"><div class="n">{counts.get(SKIP, 0)}</div><div class="l">skipped</div></div>
 <div class="card"><div class="n">{len(hard_crashes)}</div><div class="l">crashes / hangs</div></div>
 <div class="card"><div class="n">{len(refusals)}</div><div class="l">folders refused</div></div>
</div>
<h2>Mismatches ({len(failures)})</h2>
{table(failures)}
<h2>Crashes and hangs ({len(hard_crashes)})</h2>
{crash_html or "<p class='none'>None.</p>"}
<h2>Folders the engine refused ({len(refusals)})</h2>
{"".join(f"<p><b>{html.escape(item['scenario'])}</b>: {html.escape(item.get('error') or '')}</p>" for item in refusals) or "<p class='none'>None.</p>"}
<h2>Slowest files (approximate, from per-file timestamps)</h2>
<table><thead><tr><th>File</th><th>ms</th><th>Rows</th><th>Result</th></tr></thead><tbody>
{''.join(f"<tr><td class='path'>{html.escape(row['path'])}</td><td class='num'>{row['approx_ms']}</td>"
         f"<td class='num'>{html.escape(str(row['actual_rows']))}</td><td>{row['result']}</td></tr>"
         for row in slowest)}
</tbody></table>
<h2>Advisory differences ({len(warnings)})</h2>
{table(warnings)}
<h2>Not asserted ({len(skipped)})</h2>
{table(skipped)}
</body></html>
""",
        encoding="utf-8",
    )
    return html_path


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; the corpus deliberately contains
    # unicode file names, so never let a print crash the report.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=("smoke", "standard", "brutal"), default="standard")
    parser.add_argument("--family", default="", help="comma separated: banks,invoices,gst,books,junk,mixed")
    parser.add_argument("--seed", type=int, default=0, help="only checked against the manifest")
    parser.add_argument("--out", type=Path, default=ROOT / "stress-dump" / "corpus")
    parser.add_argument("--limit", type=int, default=0, help="cap the total number of files")
    parser.add_argument("--match", default="", help="comma separated path fragments to include")
    parser.add_argument("--timeout", type=float, default=900.0, help="seconds per folder")
    parser.add_argument("--no-isolate", action="store_true", help="run in this process (debugging)")
    parser.add_argument("--keep-sandbox", action="store_true")
    args = parser.parse_args(argv)

    out = args.out if args.out.is_absolute() else (ROOT / args.out)
    out = out.resolve()
    manifest = load_manifest(out)
    if args.profile != manifest.get("profile"):
        print(
            f"Warning: {out} holds the {manifest.get('profile')} profile, not {args.profile}; "
            "the manifest is authoritative (point --out at the corpus you built)."
        )
    if args.seed and args.seed != manifest.get("seed"):
        print(
            f"Warning: manifest seed is {manifest.get('seed')}, --seed is {args.seed}; "
            "the manifest is authoritative."
        )
    families = [item.strip() for item in args.family.split(",") if item.strip()]
    matches = [item.strip() for item in args.match.split(",") if item.strip()]
    groups = scenario_groups(manifest, families or None, args.limit or None, matches or None)
    if not groups:
        print("No files selected.")
        return 2

    sandbox = Path(tempfile.mkdtemp(prefix=SANDBOX_PREFIX))
    print(f"Sandbox: {sandbox}")
    started = time.perf_counter()
    try:
        graded, crashes, capabilities = execute(
            out,
            groups,
            sandbox,
            isolate=not args.no_isolate,
            timeout=args.timeout,
        )
        report = write_reports(out, str(manifest.get("profile")), graded, crashes, capabilities)
    finally:
        if args.keep_sandbox:
            print(f"Kept sandbox: {sandbox}")
        else:
            shutil.rmtree(sandbox, ignore_errors=True)

    failures = [row for row in graded if row["result"] == FAIL]
    skipped = [row for row in graded if row["result"] == SKIP]
    warnings = [row for row in graded if row["result"] == WARN]
    hard_crashes = [item for item in crashes if item.get("severity") != "refused"]
    elapsed = time.perf_counter() - started
    print()
    print(f"{len(graded)} files in {elapsed:.1f}s: "
          f"{len(graded) - len(failures) - len(skipped) - len(warnings)} pass, "
          f"{len(failures)} fail, {len(warnings)} advisory, {len(skipped)} not asserted, "
          f"{len(hard_crashes)} crash/hang, {len(crashes) - len(hard_crashes)} folders refused")
    print(f"Report: {report}")
    for row in failures[:25]:
        print(f"  FAIL {row['path']}: {row['detail']}")
    for item in hard_crashes:
        print(f"  CRASH {item['scenario']}: {item['error']}")
    return 1 if failures or hard_crashes else 0


if __name__ == "__main__":
    raise SystemExit(main())
