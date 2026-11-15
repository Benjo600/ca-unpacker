"""Tolerances: a few days of slack on dates, a few rupees on amounts.

The pure reconcile tests need no database. The saved-tolerance tests build a
firm, client and period inside a throw-away LOCALAPPDATA so nothing touches
the real library.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"


def _books(**overrides) -> dict:
    row = {
        "supplier_gstin": GSTIN,
        "invoice_number": "INV/001",
        "invoice_date": "2026-07-12",
        "invoice_value": Decimal("11800.00"),
        "supplier_name": "Acme Traders",
        "source": "bill.pdf",
    }
    row.update(overrides)
    return row


def _gstr(**overrides) -> dict:
    row = {
        "gstin": GSTIN,
        "invoice_number": "INV-1",
        "invoice_date": "12-07-2026",
        "invoice_value": Decimal("11800.00"),
        "trade_name": "Acme Traders",
        "source": "GSTR-2B.json#b2b[0]",
        "document_type": "B2B",
    }
    row.update(overrides)
    return row


def _statuses(result: dict) -> list[str]:
    return [row["status"] for row in result["rows"]]


class DateToleranceTests(unittest.TestCase):
    def test_three_days_apart_needs_the_day_allowance(self) -> None:
        from apps.engine.recon import reconcile

        books = [_books(invoice_date="2026-07-12")]
        portal = [_gstr(invoice_date="15-07-2026")]

        strict = reconcile(books, portal, date_tolerance_days=0)
        self.assertEqual(strict["counts"]["matched"], 0)
        self.assertEqual(sorted(_statuses(strict)), ["books_only", "portal_only"])

        slack = reconcile(books, portal, date_tolerance_days=7)
        self.assertEqual(slack["counts"]["matched"], 1)
        self.assertEqual(_statuses(slack), ["matched"])


class AmountToleranceTests(unittest.TestCase):
    def test_forty_rupees_needs_the_rupee_allowance(self) -> None:
        from apps.engine.recon import reconcile

        books = [_books(invoice_value=Decimal("11800.00"))]
        portal = [_gstr(invoice_value=Decimal("11840.00"))]

        strict = reconcile(books, portal)
        self.assertEqual(strict["counts"]["amount_mismatch"], 1)
        self.assertEqual(_statuses(strict), ["amount_mismatch"])

        slack = reconcile(books, portal, amount_tolerance=Decimal("50"))
        self.assertEqual(slack["counts"]["matched"], 1)
        self.assertEqual(_statuses(slack), ["matched"])

    def test_likely_pair_still_works_under_tolerance(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [_books(invoice_number="AB12", invoice_date="2026-07-12")],
            [
                _gstr(
                    invoice_number="AB12345",
                    invoice_date="15-07-2026",
                    invoice_value=Decimal("11840.00"),
                )
            ],
            date_tolerance_days=7,
            amount_tolerance=Decimal("50"),
        )

        self.assertEqual(result["counts"]["likely"], 1)
        self.assertEqual(_statuses(result), ["likely"])


class _IsolatedDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _client_and_period(self) -> tuple[dict, dict]:
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Tolerance firm")
        client = create_client("Tolerance client")
        period = create_period(client["id"], "Jul 2026")
        return client, period


class SavedToleranceTests(_IsolatedDatabase):
    def test_client_tolerances_are_saved_and_read_back(self) -> None:
        from apps.engine.clients import get_client, set_client_tolerances

        client, _period = self._client_and_period()
        returned = set_client_tolerances(client["id"], 7, 250.5)
        self.assertEqual(returned["tolerance_days"], 7)
        self.assertEqual(returned["tolerance_amount"], 250.5)

        saved = get_client(client["id"])
        assert saved is not None
        self.assertEqual(saved["tolerance_days"], 7)
        self.assertEqual(saved["tolerance_amount"], 250.5)

    def test_period_override_wins_then_falls_back_to_the_client(self) -> None:
        from apps.engine.clients import set_client_tolerances
        from apps.engine.periods import effective_tolerances, set_period_tolerances

        client, period = self._client_and_period()
        set_client_tolerances(client["id"], 7, 250.5)
        self.assertEqual(effective_tolerances(period["id"]), (7, 250.5))

        set_period_tolerances(period["id"], 2, 10)
        self.assertEqual(effective_tolerances(period["id"]), (2, 10.0))

        # Clearing the override must hand control back to the client.
        set_period_tolerances(period["id"])
        self.assertEqual(effective_tolerances(period["id"]), (7, 250.5))

    def test_invalid_client_tolerances_are_rejected(self) -> None:
        from apps.engine.clients import set_client_tolerances

        client, _period = self._client_and_period()
        cases = (
            ("negative days", -1, 1),
            ("more than 30 days", 31, 1),
            ("negative rupees", 7, -1),
            ("more than 1000 rupees", 7, 1001),
            ("text days", "as soon as possible", 1),
            ("text rupees", 7, "a little"),
        )
        for label, days, amount in cases:
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    set_client_tolerances(client["id"], days, amount)

    def test_invalid_period_overrides_are_rejected(self) -> None:
        from apps.engine.periods import set_period_tolerances

        _client, period = self._client_and_period()
        with self.assertRaises(ValueError):
            set_period_tolerances(period["id"], -1, 1)
        with self.assertRaises(ValueError):
            set_period_tolerances(period["id"], 31, 1)
        with self.assertRaises(ValueError):
            set_period_tolerances(period["id"], 7, 1001)
        with self.assertRaises(ValueError):
            set_period_tolerances(period["id"], "many", 1)


class EndToEndToleranceTests(_IsolatedDatabase):
    def test_saved_client_allowance_makes_the_three_day_gap_match(self) -> None:
        from apps.engine.clients import set_client_tolerances
        from apps.engine.periods import effective_tolerances
        from apps.engine.recon import reconcile

        client, period = self._client_and_period()
        set_client_tolerances(client["id"], 7, 1)
        days, amount = effective_tolerances(period["id"])
        self.assertEqual(days, 7)

        books = [_books(invoice_date="2026-07-12")]
        portal = [_gstr(invoice_date="15-07-2026")]

        with_saved_allowance = reconcile(
            books, portal, date_tolerance_days=days, amount_tolerance=amount
        )
        self.assertEqual(with_saved_allowance["counts"]["matched"], 1)
        self.assertEqual(_statuses(with_saved_allowance), ["matched"])

        # Proof the allowance is what made the difference, not a loose default.
        without_allowance = reconcile(books, portal)
        self.assertEqual(without_allowance["counts"]["matched"], 0)


if __name__ == "__main__":
    unittest.main()
