"""Scanning & extraction benchmark suite (Phase 13).

Synthetic financial documents with verified ground truth, measured with
financial-critical metrics: monetary-amount accuracy and debit/credit
classification are graded separately from general text CER, because a
scanner that reads 99% of prose but misreads 5% of amounts is unacceptable.

Run the full suite:  python -m apps.engine.benchmarks
Results are stored as JSON so future code changes can be compared.
"""

from apps.engine.benchmarks.runner import run_all

__all__ = ["run_all"]
