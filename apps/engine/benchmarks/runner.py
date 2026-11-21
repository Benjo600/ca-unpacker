"""Benchmark runner: scenarios, measurement, and persisted results.

Each scenario generates its ground-truth document, runs the *real* pipeline
(the same parsers the app uses), and scores the result.  Nothing is graded
against the parser's own output — expectations come from the generator.
"""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from decimal import Decimal
from pathlib import Path

from apps.engine.benchmarks import metrics, synth

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _tmp_dir() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="caunpacker_bench_"))


def _amounts_from_rows(rows: list[dict]) -> list:
    out = []
    for row in rows:
        for key in ("debit", "credit", "balance", "invoice_value", "taxable_value", "taxable", "tax", "amount"):
            value = row.get(key)
            if value is not None:
                out.append(value)
    return out


def _extract_full_text(parsed: dict) -> str:
    parts = []
    for row in parsed.get("rows") or []:
        parts.append(str(row.get("raw_text") or ""))
        parts.append(str(row.get("description") or ""))
    return "\n".join(part for part in parts if part)


# --- scenarios -------------------------------------------------------------


def scenario_clean_searchable_invoice(tmp: Path) -> dict:
    path = synth.make_searchable_invoice(tmp / "invoice_searchable.pdf")
    truth = synth.INVOICE_TRUTH

    start = time.perf_counter()
    from apps.engine.parsers.invoice import parse_invoice_file

    parsed = parse_invoice_file(path, path.name)
    elapsed = time.perf_counter() - start

    rows = parsed.get("rows") or []
    line_items = parsed.get("line_items") or []
    header = next((row for row in rows if not row.get("description")), rows[0] if rows else {})

    expected_amounts = [
        truth["taxable_value"], truth["cgst"], truth["sgst"], truth["invoice_value"],
        Decimal("13568.00"), Decimal("12720.00"), Decimal("9540.00"),
    ]
    actual_amounts = [
        header.get("taxable_value"), header.get("invoice_value"), header.get("cgst"), header.get("sgst"),
    ] + [item.get("amount") for item in line_items]
    checks = {
        "invoice_number": metrics.field_match(truth["invoice_number"], header.get("invoice_number")),
        "invoice_date": metrics.field_match(truth["invoice_date"], header.get("invoice_date")),
        "supplier_gstin": metrics.field_match(truth["supplier_gstin"], header.get("supplier_gstin")),
        "taxable_value": metrics.field_match(truth["taxable_value"], header.get("taxable_value")),
        "invoice_value": metrics.field_match(truth["invoice_value"], header.get("invoice_value")),
        "line_items": len(line_items) == truth["line_items"],
    }
    checks["total_maths_ok"] = all(
        check.get("status") == "ok" for check in header.get("checks") or []
    )
    return {
        "scenario": "clean_searchable_invoice",
        "input": "searchable pdf",
        "checks": checks,
        "field_accuracy": round(sum(1 for value in checks.values() if value) / len(checks), 4),
        "amount_accuracy": round(metrics.amount_accuracy(expected_amounts, actual_amounts), 4),
        "seconds": round(elapsed, 3),
    }


def scenario_scanned_invoice(tmp: Path) -> dict:
    path = synth.make_scanned_invoice(tmp / "invoice_scanned.png")
    truth = synth.INVOICE_TRUTH

    start = time.perf_counter()
    from apps.engine.parsers.invoice import parse_invoice_file

    parsed = parse_invoice_file(path, path.name)
    elapsed = time.perf_counter() - start

    rows = parsed.get("rows") or []
    line_items = parsed.get("line_items") or []
    header = next((row for row in rows if not row.get("description")), rows[0] if rows else {})
    checks = {
        "invoice_number": metrics.field_match(truth["invoice_number"], header.get("invoice_number")),
        "taxable_value": metrics.field_match(truth["taxable_value"], header.get("taxable_value")),
        "invoice_value": metrics.field_match(truth["invoice_value"], header.get("invoice_value")),
        "line_items": len(line_items) == truth["line_items"],
    }
    actual_amounts = [
        header.get("taxable_value"), header.get("invoice_value"),
    ] + [item.get("amount") for item in line_items]
    return {
        "scenario": "scanned_invoice_ocr",
        "input": "96dpi jpeg-softened image",
        "checks": checks,
        "field_accuracy": round(sum(1 for value in checks.values() if value) / len(checks), 4),
        "amount_accuracy": round(metrics.amount_accuracy(
            [
                truth["taxable_value"], truth["invoice_value"],
                Decimal("13568.00"), Decimal("12720.00"), Decimal("9540.00"),
            ],
            actual_amounts,
        ), 4),
        "seconds": round(elapsed, 3),
    }


def _statement_common(path, truth_rows, input_label: str, timed_fn) -> dict:
    start = time.perf_counter()
    parsed = timed_fn(path)
    elapsed = time.perf_counter() - start
    rows = parsed.get("rows") or []
    expected_keys = [
        {row["date"], row["balance"], row["debit"], row["credit"]}
        for row in truth_rows
    ]
    actual_keys = [
        {row.get("date"), row.get("balance"), row.get("debit"), row.get("credit")}
        for row in rows
    ]
    dr_cr_correct = 0
    dr_cr_total = 0
    actual_by_date = {}
    for row in rows:
        actual_by_date.setdefault(str(row.get("date")), []).append(row)
    for truth in truth_rows:
        candidates = actual_by_date.get(str(truth["date"])) or []
        best = min(
            candidates,
            key=lambda row: abs(Decimal(str(row.get("balance") or 0)) - truth["balance"]),
            default=None,
        )
        if best is None:
            dr_cr_total += 1
            continue
        dr_cr_total += 1
        truth_debit, truth_credit = truth["debit"], truth["credit"]
        if (best.get("debit") is not None) == (truth_debit is not None) and (
            best.get("credit") is not None
        ) == (truth_credit is not None):
            dr_cr_correct += 1
    return {
        "scenario": timed_fn.__name__.replace("bench_", ""),
        "input": input_label,
        "row_recall": round(metrics.row_recall(expected_keys, actual_keys), 4),
        "duplicate_rate": round(metrics.duplicate_rate(rows), 4),
        "dr_cr_accuracy": round(dr_cr_correct / dr_cr_total, 4) if dr_cr_total else 1.0,
        "balance_status": (parsed.get("check") or {}).get("status") if isinstance(parsed.get("check"), dict) else parsed.get("balance_status"),
        "amount_accuracy": round(metrics.amount_accuracy(
            [value for row in truth_rows for value in (row["debit"], row["credit"], row["balance"]) if value is not None],
            _amounts_from_rows(rows),
        ), 4),
        "seconds": round(elapsed, 3),
    }


def bench_clean_statement(path: Path) -> dict:
    from apps.engine.parsers.bank.parser import parse_bank_statement

    return parse_bank_statement(path, path.name)


def bench_lowres_statement(path: Path) -> dict:
    from apps.engine.parsers.bank.parser import parse_bank_statement

    return parse_bank_statement(path, path.name)


def bench_rotated_statement(path: Path) -> dict:
    from apps.engine.parsers.bank.parser import parse_bank_statement

    return parse_bank_statement(path, path.name)


def bench_multipage_statement(path: Path) -> dict:
    from apps.engine.parsers.bank.parser import parse_bank_statement

    return parse_bank_statement(path, path.name)


def scenario_clean_statement(tmp: Path) -> dict:
    path = synth.make_searchable_statement(tmp / "statement.pdf")
    return _statement_common(path, synth.STATEMENT_TRUTH_ROWS, "searchable pdf", bench_clean_statement)


def scenario_lowres_statement(tmp: Path) -> dict:
    path = synth.make_lowres_statement(tmp / "statement_lowres.png")
    return _statement_common(path, synth.STATEMENT_TRUTH_ROWS, "100dpi blurred image", bench_lowres_statement)


def scenario_rotated_statement(tmp: Path) -> dict:
    path = synth.make_rotated_statement(tmp / "statement_rotated.png")
    return _statement_common(path, synth.STATEMENT_TRUTH_ROWS, "120dpi image rotated 2.5°", bench_rotated_statement)


def scenario_multipage_statement(tmp: Path) -> dict:
    path = synth.make_multipage_statement(tmp / "statement_multipage.pdf")
    result = _statement_common(
        path,
        synth.STATEMENT_TRUTH_ROWS,
        "2-page pdf, repeated header, wrapped narration",
        bench_multipage_statement,
    )
    result["scenario"] = "multipage_statement_continuation"
    return result


def scenario_mixed_pdf(tmp: Path) -> dict:
    path = synth.make_mixed_pdf(tmp / "invoice_mixed.pdf")

    start = time.perf_counter()
    from apps.engine.pdf_extract import extract_pdf

    extracted = extract_pdf(path)
    elapsed = time.perf_counter() - start
    ocr_pages = set((extracted.page_methods or {}).keys())
    return {
        "scenario": "mixed_pdf_per_page_routing",
        "input": "page 1 text layer + page 2 scanned image",
        "checks": {
            "page1_native": 1 not in ocr_pages,
            "page2_ocr": 2 in ocr_pages,
            "both_pages_have_text": all(
                (page.text or "").strip() for page in extracted.pages
            ),
        },
        "seconds": round(elapsed, 3),
    }


def scenario_ledger_table(tmp: Path) -> dict:
    path = synth.make_ledger_pdf(tmp / "ledger.pdf")
    start = time.perf_counter()
    from apps.engine.parsers.sap.parser import parse_sap_file

    parsed = parse_sap_file(path, path.name)
    elapsed = time.perf_counter() - start
    rows = parsed.get("rows") or []
    # Rows are keyed on reference + amounts: the SAP PDF table reader merges
    # an adjacent posting-key cell into the document number ("5100000012 KR"),
    # which the benchmark records as a known limitation rather than papering
    # over.  Amounts are still graded strictly.
    expected_keys = [
        {"INV-9001", "18540.00"}, {"PAY-1101", "18540.00"},
        {"INV-9077", "7210.25"}, {"PAY-1188", "7210.25"},
    ]
    actual_keys = [
        {str(row.get("reference") or ""), metrics._norm_amount(row.get("debit")) or metrics._norm_amount(row.get("credit")) or ""}
        for row in rows
    ]
    merged_ids = sum(
        1 for row in rows
        if isinstance(row.get("document_number"), str) and " " in str(row.get("document_number"))
    )
    # Direction grading: which of debit/credit is populated is real financial
    # evidence — a column swap must fail even when amounts all match.
    direction_correct = 0
    direction_total = 0
    actual_by_reference = {}
    for row in rows:
        reference = str(row.get("reference") or "")
        actual_by_reference.setdefault(reference, []).append(row)
    for truth in synth.LEDGER_TRUTH_ROWS:
        candidates = actual_by_reference.get(synth.REFERENCE_BY_DOCUMENT[truth["document"]]) or []
        best = min(
            candidates,
            key=lambda row: abs(
                Decimal(str(row.get("debit") or 0)) - Decimal(str(truth["debit"] or 0))
            ) + abs(
                Decimal(str(row.get("credit") or 0)) - Decimal(str(truth["credit"] or 0))
            ),
            default=None,
        )
        direction_total += 1
        if best is not None and (best.get("debit") is not None) == (truth["debit"] is not None) and (
            best.get("credit") is not None
        ) == (truth["credit"] is not None):
            direction_correct += 1
    return {
        "scenario": "ledger_table_extraction",
        "input": "searchable columnar pdf, 7 columns",
        "row_recall": round(metrics.row_recall(expected_keys, actual_keys), 4),
        "amount_accuracy": round(metrics.amount_accuracy(
            [value for row in synth.LEDGER_TRUTH_ROWS for value in (row["debit"], row["credit"]) if value is not None],
            _amounts_from_rows(rows),
        ), 4),
        "dr_cr_accuracy": round(direction_correct / direction_total, 4) if direction_total else 1.0,
        "notes": {"document_number_cells_merged": merged_ids},
        "seconds": round(elapsed, 3),
    }


SCENARIOS = (
    scenario_clean_searchable_invoice,
    scenario_scanned_invoice,
    scenario_clean_statement,
    scenario_lowres_statement,
    scenario_rotated_statement,
    scenario_multipage_statement,
    scenario_mixed_pdf,
    scenario_ledger_table,
)


def run_all(scenarios=SCENARIOS, *, label: str = "", out_name: str = "last_run.json") -> dict:
    tmp = _tmp_dir()
    results = []
    for scenario in scenarios:
        try:
            tracemalloc.start()
            result = scenario(tmp)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            result["peak_memory_mb"] = round(peak / (1024 * 1024), 2)
            failed_checks = [
                key for key, value in (result.get("checks") or {}).items() if not value
            ]
            result["status"] = "failed_checks" if failed_checks else "ok"
            if failed_checks:
                result["failed_checks"] = failed_checks
        except Exception as exc:  # a failing scenario is a result, not a crash
            tracemalloc.stop()
            result = {
                "scenario": getattr(scenario, "__name__", str(scenario)),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
    report = {
        "label": label,
        "engine_version": _engine_version(),
        "results": results,
        "totals": {
            "scenarios": len(results),
            "errors": sum(1 for item in results if item.get("status") == "error"),
            "failed_checks": sum(
                1 for item in results if item.get("status") == "failed_checks"
            ),
            "total_seconds": round(sum(item.get("seconds", 0) or 0 for item in results), 3),
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / out_name
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _engine_version() -> str:
    try:
        from apps.engine.parsers.bank import parser as bank_parser

        return f"bank:{getattr(bank_parser, 'PARSER_VERSION', '1')}"
    except Exception:
        return "unknown"


def print_report(report: dict) -> None:
    for result in report["results"]:
        name = result.get("scenario", "?")
        if result.get("status") == "error":
            print(f"ERROR  {name}: {result.get('error')}")
            continue
        metrics_bits = []
        for key in ("field_accuracy", "amount_accuracy", "row_recall", "dr_cr_accuracy", "duplicate_rate", "text_cer"):
            if key in result:
                metrics_bits.append(f"{key}={result[key]}")
        if result.get("checks"):
            failed = [key for key, value in result["checks"].items() if not value]
            metrics_bits.append("checks_ok" if not failed else f"checks_failed={failed}")
        print(f"{name}: {', '.join(metrics_bits)} · {result.get('seconds', '?')}s · {result.get('peak_memory_mb', '?')} MB")


if __name__ == "__main__":  # pragma: no cover
    report = run_all(label="manual")
    print_report(report)
    print(f"Results written to {RESULTS_DIR / 'last_run.json'}")
    sys.exit(0 if report["totals"]["errors"] == 0 else 1)
