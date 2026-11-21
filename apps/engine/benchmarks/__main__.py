import sys

from apps.engine.benchmarks.runner import RESULTS_DIR, print_report, run_all

if __name__ == "__main__":
    report = run_all(label="manual")
    print_report(report)
    print(f"Results written to {RESULTS_DIR / 'last_run.json'}")
    failed = report["totals"]["errors"] + report["totals"].get("failed_checks", 0)
    sys.exit(0 if failed == 0 else 1)
