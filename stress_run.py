"""Headless stress run: feed every stress-dump folder through the engine.

Also parses each bank PDF directly and reports running-balance accuracy.

Run: .venv\\Scripts\\python.exe stress_run.py
Uses a throwaway library (temp LOCALAPPDATA); the user's real data is untouched.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SCENARIOS = [
    ("banks", "01-banks-stress"),
    ("invoices", "02-invoices-stress"),
    ("gst", "03-gst-stress"),
    ("books", "04-books-stress"),
    ("junk", "05-junk-stress"),
    ("mixed", "06-mixed-stress"),
]


def find_files(base: Path) -> list[str]:
    return [str(p) for p in sorted(base.iterdir()) if p.is_file() and p.name != "README.md"]


def direct_bank_checks() -> list[dict]:
    from apps.engine.parsers.bank.parser import parse_bank_pdf
    from apps.engine.validators.balance import check_balance

    out = []
    for path in sorted((ROOT / "stress-dump" / "01-banks-stress").glob("*.pdf")):
        try:
            parsed = parse_bank_pdf(path)
            check = check_balance(
                parsed["rows"], parsed["opening_balance"], parsed["stated_closing"]
            )
            out.append(
                {
                    "file": path.name,
                    "profile": parsed["profile"],
                    "strategy": parsed["parse_strategy"],
                    "rows": len(parsed["rows"]),
                    "dropped": parsed["dropped_count"],
                    "balance_status": check.get("status"),
                    "detail": check.get("detail"),
                }
            )
        except Exception as exc:  # parser crash = finding, not a skip
            out.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
    return out


def main() -> int:
    dump_root = ROOT / "stress-dump"
    if not dump_root.exists():
        print("stress-dump/ missing; run build_stress_dump.py first")
        return 2

    report: dict = {"direct_bank_checks": direct_bank_checks(), "pipeline": []}

    tmp = tempfile.mkdtemp(prefix="ca-stress-")
    os.environ["LOCALAPPDATA"] = tmp
    os.environ["CA_UNPACKER_DEV"] = "1"
    from apps.engine.db import reset_engine
    from apps.engine.clients import create_client
    from apps.engine.dump import ingest_paths, list_period_files, start_job
    from apps.engine.periods import create_period
    from apps.engine.pipeline import parse_period

    reset_engine()
    try:
        client = create_client("Stress Client")
        for label, folder in SCENARIOS:
            files = find_files(dump_root / folder)
            if not files:
                report["pipeline"].append({"scenario": label, "error": "no files"})
                continue
            period = create_period(client["id"], f"Stress {label}")
            job = start_job(period["id"])
            ingest_paths(job["id"], files)
            parse_period(period["id"])
            for row in list_period_files(period["id"]):
                report["pipeline"].append(
                    {
                        "scenario": label,
                        "file": row["original_name"],
                        "kind": row["kind"],
                        "outcome": row.get("parse_outcome") or "?",
                        "rows": row.get("parse_row_count"),
                        "reason": row.get("classify_reason") or "",
                        "flags": row.get("parse_warnings") or [],
                    }
                )
            print(f"== {label}: done", flush=True)
    except Exception as exc:
        report["pipeline"].append({"fatal": f"{type(exc).__name__}: {exc}"})
    finally:
        reset_engine()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
