from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ocr_available() -> bool:
    try:
        from apps.engine.ocr import ocr_available

        return bool(ocr_available())
    except Exception:
        return False


class BenchmarkSmokeTests(unittest.TestCase):
    """Fast subset with strict thresholds; writes its own results artifact.

    The full suite runs via ``python -m apps.engine.benchmarks`` into
    results/last_run.json; the smoke run must never clobber that artifact.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from apps.engine.benchmarks import runner

        scenarios = [runner.scenario_clean_searchable_invoice]
        if _ocr_available():
            scenarios.append(runner.scenario_mixed_pdf)
        cls.report = runner.run_all(scenarios, label="pytest-smoke", out_name="pytest_smoke.json")

    def test_all_scenarios_complete_without_error(self) -> None:
        problems = [
            item
            for item in self.report["results"]
            if item.get("status") in {"error", "failed_checks"}
        ]
        self.assertEqual(problems, [], problems)

    def test_clean_searchable_invoice_fields_and_maths(self) -> None:
        result = next(
            item
            for item in self.report["results"]
            if item.get("scenario") == "clean_searchable_invoice"
        )
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["field_accuracy"], 0.99, result)
        self.assertGreaterEqual(result["amount_accuracy"], 0.99, result)
        for check, value in result.get("checks", {}).items():
            self.assertTrue(value, f"check {check} failed")

    @unittest.skipUnless(_ocr_available(), "no local OCR engine available")
    def test_mixed_pdf_routes_per_page(self) -> None:
        result = next(
            item for item in self.report["results"] if item.get("scenario") == "mixed_pdf_per_page_routing"
        )
        self.assertEqual(result["status"], "ok")
        for check, value in result.get("checks", {}).items():
            self.assertTrue(value, f"check {check} failed")

    def test_results_are_persisted_separately(self) -> None:
        results_dir = Path(__file__).resolve().parent.parent / "benchmarks" / "results"
        smoke = results_dir / "pytest_smoke.json"
        self.assertTrue(smoke.is_file())
        self.assertIn("pytest-smoke", smoke.read_text(encoding="utf-8")[:200])


class FullBenchmarkSuiteTests(unittest.TestCase):
    """Every scenario asserted — the suite must bind all eight results."""

    @classmethod
    def setUpClass(cls) -> None:
        from apps.engine.benchmarks import runner

        cls.report = runner.run_all(SCENARIOS_OVERRIDE or runner.SCENARIOS, label="pytest-full")

    def test_every_scenario_succeeds_with_no_failed_checks(self) -> None:
        problems = [
            item
            for item in self.report["results"]
            if item.get("status") in {"error", "failed_checks"}
        ]
        self.assertEqual(problems, [], problems)

    def test_statement_scenarios_recall_all_rows(self) -> None:
        for scenario, minimum in (
            ("clean_statement", 0.99),
            ("lowres_statement", 0.99),
            ("rotated_statement", 0.99),
            ("multipage_statement_continuation", 0.99),
        ):
            result = next(
                item for item in self.report["results"] if item.get("scenario") == scenario
            )
            self.assertGreaterEqual(
                result.get("row_recall", 0.0), minimum, f"{scenario}: {result}"
            )
            self.assertGreaterEqual(
                result.get("dr_cr_accuracy", 0.0), 0.99, f"{scenario}: {result}"
            )
            self.assertGreaterEqual(
                result.get("amount_accuracy", 0.0), 0.99, f"{scenario}: {result}"
            )
            self.assertLessEqual(result.get("duplicate_rate", 1.0), 0.01, f"{scenario}: {result}")

    @unittest.skipUnless(_ocr_available(), "no local OCR engine available")
    def test_scanned_invoice_ocr_reads_money(self) -> None:
        result = next(
            item for item in self.report["results"] if item.get("scenario") == "scanned_invoice_ocr"
        )
        self.assertGreaterEqual(result.get("field_accuracy", 0.0), 0.99, result)
        self.assertGreaterEqual(result.get("amount_accuracy", 0.0), 0.99, result)

    def test_ledger_rows_and_directions(self) -> None:
        result = next(
            item for item in self.report["results"] if item.get("scenario") == "ledger_table_extraction"
        )
        self.assertGreaterEqual(result.get("row_recall", 0.0), 0.99, result)
        self.assertGreaterEqual(result.get("amount_accuracy", 0.0), 0.99, result)
        self.assertGreaterEqual(result.get("dr_cr_accuracy", 0.0), 0.99, result)


def _scenarios() -> tuple:
    from apps.engine.benchmarks import runner

    if not _ocr_available():
        from apps.engine.benchmarks import synth

        # Without an OCR engine the image scenarios cannot be graded; drop
        # them explicitly rather than letting them fail noisily.
        return tuple(
            scenario
            for scenario in runner.SCENARIOS
            if scenario.__name__ not in {
                "scenario_scanned_invoice",
                "scenario_lowres_statement",
                "scenario_rotated_statement",
            }
        )
    return runner.SCENARIOS


SCENARIOS_OVERRIDE = _scenarios()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
