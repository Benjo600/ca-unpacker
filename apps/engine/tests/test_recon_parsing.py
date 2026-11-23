from __future__ import annotations

import ast
import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine import recon, recon_engine
from apps.engine.recon_parsing import parse_date_value, parse_money_value

# (input, expected) pairs.  Both engines must return the expected value and
# therefore must agree with each other.
MONEY_CASES = (
    ("₹1,177.74", Decimal("1177.74")),
    ("1,177.74", Decimal("1177.74")),
    ("1,00,000.50", Decimal("100000.50")),
    ("3800", Decimal("3800")),
    ("$1,177.74", Decimal("1177.74")),
    ("Rs. 1,177.74", Decimal("1177.74")),
    ("1,177.74 Dr", Decimal("1177.74")),
    ("1,177.74 Cr", Decimal("1177.74")),
    ("(500)", Decimal("-500")),
    ("-500", Decimal("-500")),
    ("1 177.74", Decimal("1177.74")),
    (Decimal("11800"), Decimal("11800")),
    (11800, Decimal("11800")),
    (11800.5, Decimal("11800.5")),
    (None, None),
    ("", None),
    ("   ", None),
    ("abc", None),
    ("abc123", None),
    ("12abc34", None),
    ("N/A", None),
    ("nan", None),
    ("inf", None),
    (Decimal("NaN"), None),
    (True, None),
    (False, None),
    ("(500", None),
)

DATE_CASES = (
    ("12-07-2026", date(2026, 7, 12)),
    ("2026-07-12", date(2026, 7, 12)),
    ("12/07/2026", date(2026, 7, 12)),
    ("12.07.2026", date(2026, 7, 12)),
    ("20260712", date(2026, 7, 12)),
    ("12-07-26", date(2026, 7, 12)),
    ("12/07/26", date(2026, 7, 12)),
    ("12 Jul 2026", date(2026, 7, 12)),
    ("12-Jul-2026", date(2026, 7, 12)),
    ("Jul 12, 2026", date(2026, 7, 12)),
    ("2026-07-12T10:00:00", date(2026, 7, 12)),
    ("2026-07-12 10:00:00", date(2026, 7, 12)),
    (date(2026, 7, 12), date(2026, 7, 12)),
    (datetime(2026, 7, 12, 10, 0), date(2026, 7, 12)),
    (None, None),
    ("", None),
    ("   ", None),
    ("not a date", None),
    # A bare number is not read as a date (no Excel-serial guessing).
    ("45000", None),
    (45000, None),
    ("31-02-2026", None),
    ("2026-13-01", None),
)


class SharedMoneyParsingTest(unittest.TestCase):
    def test_engines_agree(self):
        for value, _expected in MONEY_CASES:
            with self.subTest(value=value):
                self.assertEqual(recon.money(value), recon_engine.parse_money(value))

    def test_values(self):
        for value, expected in MONEY_CASES:
            with self.subTest(value=value):
                self.assertEqual(recon.money(value), expected)
                self.assertEqual(recon_engine.parse_money(value), expected)

    def test_shared_helper(self):
        self.assertEqual(parse_money_value("1,177.74"), Decimal("1177.74"))
        self.assertIsNone(parse_money_value("abc123"))


class SharedDateParsingTest(unittest.TestCase):
    def test_engines_agree(self):
        for value, _expected in DATE_CASES:
            with self.subTest(value=value):
                self.assertEqual(
                    recon.parse_recon_date(value), recon_engine.parse_date(value)
                )

    def test_values(self):
        for value, expected in DATE_CASES:
            with self.subTest(value=value):
                self.assertEqual(recon.parse_recon_date(value), expected)
                self.assertEqual(recon_engine.parse_date(value), expected)

    def test_shared_helper(self):
        self.assertEqual(parse_date_value("12-07-2026"), date(2026, 7, 12))
        self.assertIsNone(parse_date_value("45000"))


class DelegationTest(unittest.TestCase):
    """The engine modules must not grow their own copies again."""

    def _returns_shared_helper(self, module_path: Path, function_name: str, helper: str):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                body = [n for n in node.body if not isinstance(n, ast.Expr)]
                self.assertEqual(len(body), 1, f"{function_name} has its own logic")
                returns = body[0]
                if not isinstance(returns, ast.Return) or not isinstance(
                    returns.value, ast.Call
                ):
                    self.fail(f"{function_name} does not return a helper call")
                func = returns.value.func
                if not isinstance(func, ast.Name):
                    self.fail(f"{function_name} does not call a plain helper")
                self.assertEqual(func.id, helper)
                return
        self.fail(f"{function_name} not found in {module_path}")

    def test_recon_delegates(self):
        engine = ROOT / "apps" / "engine" / "recon.py"
        self._returns_shared_helper(engine, "money", "parse_money_value")
        self._returns_shared_helper(engine, "parse_recon_date", "parse_date_value")

    def test_recon_engine_delegates(self):
        engine = ROOT / "apps" / "engine" / "recon_engine.py"
        self._returns_shared_helper(engine, "parse_money", "parse_money_value")
        self._returns_shared_helper(engine, "parse_date", "parse_date_value")


if __name__ == "__main__":
    unittest.main()
