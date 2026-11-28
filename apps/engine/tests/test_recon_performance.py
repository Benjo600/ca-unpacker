"""Reconciliation must stay usable as a month grows.

The load test that produced these bounds: 100 rows took 59 seconds, 200 rows
never finished, and a 398-file month sat in "parsing" for over 40 minutes while
holding the database.  The split-merge rule was trying every pair and triple of
candidate bills and re-reading each amount on every attempt; then bank hinting
took over, scoring and re-parsing every bank line for every row.

These tests pin the answers (the same counts, totals and bank hints as the day
of each fix) and the speed.  The 5,000-row reconcile run is deliberately not in
the suite: set ``CA_RECON_PERF=1`` to run the 2,000-row timing too.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GSTIN = "27AAPFU0939F1ZV"
OTHER_GSTIN = "29AADCH8449J1Z0"
LOAD_TEST = os.environ.get("CA_RECON_PERF") == "1"


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
        "invoice_number": "INV/001",
        "invoice_date": "12-07-2026",
        "invoice_value": Decimal("11800.00"),
        "trade_name": "Acme Traders",
        "source": "GSTR-2B.json#b2b",
        "document_type": "B2B",
    }
    row.update(overrides)
    return row


def _month(rows: int) -> tuple[list[dict], list[dict]]:
    """One books row and one portal row per invoice, unique numbers each side.

    The invoice numbers never agree across the two sides, which is what put
    every book row in front of every portal row as a split-merge candidate.
    """
    books: list[dict] = []
    portal: list[dict] = []
    for index in range(rows):
        amount = 100 + index
        books.append(
            {
                "supplier_gstin": GSTIN,
                "invoice_number": f"INV/{index:05d}",
                "invoice_date": "2026-07-12",
                "invoice_value": amount,
                "supplier_name": "Acme Traders",
                "source": "books.xlsx",
            }
        )
        portal.append(
            {
                "gstin": GSTIN,
                "invoice_number": f"GST-{index:05d}",
                "invoice_date": "12-07-2026",
                "invoice_value": amount,
                "trade_name": "Acme Traders",
                "source": "GSTR-2B.json",
                "document_type": "B2B",
            }
        )
    return books, portal


def _mixed_month() -> tuple[list[dict], list[dict]]:
    """One row per status: match, split, merge, likely, mismatch, duplicate..."""
    books = [
        _books(),
        _books(invoice_number="SPLIT-B", invoice_value=Decimal("5900.00")),
        _books(invoice_number="MERGE-1", invoice_value=Decimal("5000.00")),
        _books(invoice_number="MERGE-2", invoice_value=Decimal("4000.00")),
        _books(invoice_number="AB12", invoice_value=Decimal("700.00")),
        _books(invoice_number="MISMATCH-1", invoice_value=Decimal("900.00")),
        _books(invoice_number="TAX-1", invoice_value=Decimal("1180.00"), cgst=Decimal("90.00")),
        _books(invoice_number="DUP-1", invoice_value=Decimal("600.00")),
        _books(invoice_number="DUP-1", invoice_value=Decimal("600.00")),
        _books(invoice_number="ONLY-BOOKS", invoice_value=Decimal("450.00")),
        _books(invoice_number="ACME/26-27/0142", invoice_value=Decimal("11800.00")),
        _books(invoice_number="PUR-88", invoice_value=Decimal("11800.00")),
        _books(
            supplier_gstin=OTHER_GSTIN,
            invoice_number="OTHER-GSTIN",
            invoice_value=Decimal("300.00"),
        ),
    ]
    portal = [
        _gstr(),
        _gstr(invoice_number="SPLIT-B", invoice_value=Decimal("2950.00")),
        _gstr(invoice_number="SPLIT-B", invoice_value=Decimal("2950.00")),
        _gstr(invoice_number="INV-MERGE", invoice_value=Decimal("9000.00")),
        _gstr(invoice_number="AB12-EXTENDED", invoice_value=Decimal("700.00")),
        _gstr(invoice_number="MISMATCH-1", invoice_value=Decimal("1200.00")),
        _gstr(invoice_number="TAX-1", invoice_value=Decimal("1180.00"), cgst=Decimal("85.00")),
        _gstr(invoice_number="ONLY-PORTAL", invoice_value=Decimal("250.00")),
        _gstr(invoice_number="CN-77", document_type="CDNR", invoice_value=Decimal("-1180.00")),
        _gstr(invoice_number="INV/001", invoice_value=Decimal("11800.00")),
        _gstr(invoice_number="UNMATCHED-PORTAL", invoice_value=Decimal("5000.00")),
    ]
    return books, portal


def _counts(result: dict) -> dict:
    return {key: value for key, value in result["counts"].items() if value}


def _timed(rows: int) -> tuple[float, dict]:
    from apps.engine.recon import reconcile

    books, portal = _month(rows)
    started = time.perf_counter()
    result = reconcile(books, portal)
    return time.perf_counter() - started, result


# ---------------------------------------------------------------------------
# Bank hints
#
# The reference below is the bank-hint rule as it stood before the index: read
# every bank line for every row, parsing each line's date and amounts on every
# comparison.  It is kept only so the tests can prove the fast path chooses the
# same line, the same score and the same text.
# ---------------------------------------------------------------------------

BANK_STATEMENT = [
    # Two near-amount lines score the same for an 11,800 row.  The amount order
    # puts index 1 first, so only the file-order rule keeps index 0 winning.
    {"date": "2026-07-02", "narration": "NEFT ACME TRADERS", "debit": 11800.40, "credit": None},
    {"date": "2026-07-14", "narration": "UPI REF 4471", "debit": 11799.80, "credit": None},
    # Inside the rupee allowance of a 2,500.40 row.
    {"date": "2026-07-12", "narration": "BETA ENTERPRISES", "debit": 2500.00, "credit": None},
    # 2.40 away from a 2,505.40 row: outside the allowance.
    {"date": "2026-07-12", "narration": "BETA ENTERPRISES", "debit": 2503.00, "credit": None},
    # Money on the credit side only.
    {"date": "2026-07-19", "narration": "GAMMA SUPPLIES", "debit": None, "credit": 900.00},
    # Same amount twice: the later line scores higher and must win.
    {"date": "2026-07-13", "narration": "UPI REF 1001", "debit": 5000.00, "credit": None},
    {"date": "2026-07-15", "narration": "NEFT ACME TRADERS", "debit": 5000.00, "credit": None},
    # Same amount, same score: the earlier line must win.
    {"date": "2026-07-14", "narration": "UPI REF 2002", "debit": 6400.00, "credit": None},
    {"date": "2026-07-02", "narration": "NEFT ACME TRADERS", "debit": 6400.00, "credit": None},
    # A line with no readable date still hints on amount and party.
    {"date": "", "narration": "GAMMA SUPPLIES", "debit": 4000.00, "credit": None},
    # A zero debit must not count as a debit; the credit carries the money.
    {"date": "2026-07-12", "narration": "BETA ENTERPRISES PAYMENT", "debit": 0, "credit": 3200.00},
]

#: amount, party.  Every amount is more than a rupee away from every other.
HINT_CASES = [
    (Decimal("11800.00"), "Acme Traders"),      # near-amount tie, earliest line
    (Decimal("2500.40"), "Beta Enterprises"),   # inside the rupee allowance
    (Decimal("2505.40"), "Beta Enterprises"),   # outside it: no hint
    (Decimal("900.00"), "Gamma Supplies"),      # credit side
    (Decimal("5000.00"), "Acme Traders"),       # later line scores higher
    (Decimal("6400.00"), "Acme Traders"),       # equal scores, earliest line
    (Decimal("4000.00"), "Gamma Supplies"),     # bank line has no date
    (Decimal("3200.00"), "Beta Enterprises"),   # zero debit, credit money
    (Decimal("7500.00"), "Delta Industries"),   # no line like it: no hint
    (Decimal("1200.00"), "Nobody At All"),      # no line like it: no hint
]


def _legacy_bank_score(line: dict, amount, when, party: str, tolerance=None) -> int:
    from apps.engine.recon import AMOUNT_TOLERANCE, money, parse_recon_date

    score = 0
    limit = tolerance if tolerance is not None else AMOUNT_TOLERANCE
    debit = money(line.get("debit"))
    credit = money(line.get("credit"))
    line_amt = debit if debit not in (None, Decimal("0")) else credit
    if amount is not None and line_amt is not None and (amount - line_amt).copy_abs() <= limit:
        score += 50
    line_date = parse_recon_date(line.get("date"))
    if when is not None and line_date is not None and abs((when - line_date).days) <= 7:
        score += 20
    narr = str(line.get("narration") or line.get("description") or "")
    party_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", (party or "").upper())}
    narr_tokens = {tok for tok in re.findall(r"[A-Za-z]{3,}", narr.upper())}
    if party_tokens & narr_tokens:
        score += 20
    if debit not in (None, Decimal("0")):
        score += 10
    return score


def _legacy_bank_hint(row: dict, book: dict, portal: dict, bank_rows: list[dict], tolerance=None) -> str:
    """The pre-index hint: scan every bank line, re-parsing it each time."""
    from apps.engine.recon import (
        _books_amount,
        _books_date,
        _gstr_amount,
        _gstr_date,
        money,
        parse_recon_date,
    )

    if not bank_rows:
        return ""
    amount = _books_amount(book) if book else None
    if amount is None and portal:
        amount = _gstr_amount(portal)
    when = _books_date(book) if book else None
    if when is None and portal:
        when = _gstr_date(portal)
    party = str(row.get("party") or "")
    best_score = 0
    best_line: dict | None = None
    for line in bank_rows:
        score = _legacy_bank_score(line, amount, when, party, tolerance)
        if score > best_score:
            best_score = score
            best_line = line
    if best_score < 70 or best_line is None:
        return ""
    line_date = parse_recon_date(best_line.get("date"))
    debit = money(best_line.get("debit"))
    credit = money(best_line.get("credit"))
    shown = debit if debit else credit
    narr = str(best_line.get("narration") or best_line.get("description") or "").strip()
    snippet = re.sub(r"\s+", " ", narr)[:40]
    parts = []
    if line_date:
        parts.append(line_date.isoformat())
    if shown is not None:
        parts.append(f"{shown:.2f}")
    if snippet:
        parts.append(snippet)
    return " | ".join(parts)


def _hint_rows(count: int) -> tuple[list[dict], list[dict]]:
    """``count`` matched books/portal rows cycling through the hint cases."""
    books: list[dict] = []
    portal: list[dict] = []
    for index in range(count):
        amount, party = HINT_CASES[index % len(HINT_CASES)]
        books.append(
            _books(
                invoice_number=f"INV/{index:05d}",
                invoice_value=amount,
                supplier_name=party,
            )
        )
        portal.append(
            _gstr(
                invoice_number=f"INV-{index:05d}",
                invoice_value=amount,
                trade_name=party,
            )
        )
    return books, portal


def _hint_load_rows(rows: int, bank_lines: int) -> tuple[list[dict], list[dict], list[dict]]:
    """A month where every row has a bank line worth hinting about."""
    names = ["Acme Traders", "Beta Enterprises", "Gamma Supplies", "Delta Industries"]
    books: list[dict] = []
    portal: list[dict] = []
    for index in range(rows):
        amount = Decimal(1000 + (index % 900) * 7) + Decimal("0.40")
        name = names[index % len(names)]
        books.append(
            _books(
                invoice_number=f"INV/{index:05d}",
                invoice_value=amount,
                supplier_name=name,
            )
        )
        portal.append(
            _gstr(
                invoice_number=f"INV-{index:05d}",
                invoice_value=amount,
                trade_name=name,
            )
        )
    bank: list[dict] = []
    for index in range(bank_lines):
        amount = Decimal(1000 + (index % 1200) * 7) + Decimal("0.40")
        bank.append(
            {
                "date": f"2026-07-{1 + index % 28:02d}",
                "narration": f"NEFT {names[index % len(names)].upper()} PAYMENT",
                "debit": amount if index % 3 else None,
                "credit": None if index % 3 else amount,
            }
        )
    return books, portal, bank


class ReconAnswersUnchangedTests(unittest.TestCase):
    """The fix is a speed change, so the answers must be exactly as before."""

    def test_fifty_row_month_keeps_its_counts_and_totals(self) -> None:
        from apps.engine.recon import reconcile

        books, portal = _month(50)
        result = reconcile(books, portal)

        self.assertEqual(_counts(result), {"books_only": 50, "portal_only": 50})
        self.assertEqual(result["totals"]["portal_total"], 6225.0)
        self.assertEqual(result["totals"]["books_total"], 6225.0)
        self.assertEqual(result["totals"]["gap"], 0.0)
        self.assertEqual(result["totals"]["credit_at_risk"], 6225.0)
        self.assertEqual(result["totals"]["unsupported_credit"], 6225.0)

    def test_mixed_month_keeps_every_status_and_total(self) -> None:
        from apps.engine.recon import reconcile

        books, portal = _mixed_month()
        result = reconcile(books, portal)

        self.assertEqual(
            _counts(result),
            {
                "matched": 1,
                "books_only": 3,
                "portal_only": 2,
                "likely": 1,
                "tax_mismatch": 1,
                "duplicate": 1,
                "split_merged": 3,
                "credit_note": 1,
                "same_bill": 2,
            },
        )
        self.assertEqual(
            result["totals"],
            {
                "books_total": 26830.0,
                "credit_at_risk": 5250.0,
                "credit_note_total": 1180.0,
                "gap": 20000.0,
                "portal_total": 46830.0,
                "same_bill_total": 23600.0,
                "unsupported_credit": 1650.0,
            },
        )
        self.assertEqual(
            [row["status"] for row in result["rows"]],
            [
                "matched",
                "tax_mismatch",
                "split_merged",
                "split_merged",
                "split_merged",
                "likely",
                "duplicate",
                "same_bill",
                "same_bill",
                "portal_only",
                "portal_only",
                "books_only",
                "books_only",
                "books_only",
                "credit_note",
            ],
        )


class SplitMergeStillWorksTests(unittest.TestCase):
    def test_two_bills_that_add_up_are_still_one_line(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [
                _books(invoice_number="BILL/1", invoice_value=Decimal("5000.00")),
                _books(invoice_number="BILL/2", invoice_value=Decimal("4000.00")),
            ],
            [_gstr(invoice_number="INV-1", invoice_value=Decimal("9000.00"))],
        )

        self.assertEqual(_counts(result), {"split_merged": 1})
        self.assertEqual([row["status"] for row in result["rows"]], ["split_merged"])

    def test_three_bills_that_add_up_are_still_one_line(self) -> None:
        from apps.engine.recon import reconcile

        result = reconcile(
            [
                _books(invoice_number="BILL/1", invoice_value=Decimal("3000.00")),
                _books(invoice_number="BILL/2", invoice_value=Decimal("3000.00")),
                _books(invoice_number="BILL/3", invoice_value=Decimal("3000.00")),
            ],
            [_gstr(invoice_number="INV-1", invoice_value=Decimal("9000.00"))],
        )

        self.assertEqual(_counts(result), {"split_merged": 1})
        row = result["rows"][0]
        self.assertEqual(row["amount_2b"], 9000.0)
        self.assertEqual(row["amount_books"], 3000.0)
        self.assertIn("3 bills", row["reason"])

    def test_group_is_reported_in_file_order(self) -> None:
        from apps.engine.recon import reconcile

        books = [
            _books(invoice_number="BILL/1", invoice_value=Decimal("1000.00")),
            _books(invoice_number="BILL/2", invoice_value=Decimal("4000.00")),
            _books(invoice_number="BILL/3", invoice_value=Decimal("2000.00")),
            _books(invoice_number="BILL/4", invoice_value=Decimal("6000.00")),
        ]
        result = reconcile(books, [_gstr(invoice_number="INV-1", invoice_value=Decimal("10000.00"))])

        # BILL/2 + BILL/4 is the first pair in file order that adds up, so it is
        # the pair reported; the group must not silently reorder itself.
        self.assertEqual(_counts(result), {"split_merged": 1, "books_only": 2})
        self.assertEqual(
            [row["status"] for row in result["rows"]],
            ["split_merged", "books_only", "books_only"],
        )
        row = result["rows"][0]
        self.assertEqual(row["invoice_books"], "BILL/2")
        self.assertEqual(row["amount_2b"], 10000.0)
        self.assertIn("2 bills", row["reason"])
        self.assertEqual(
            [row["invoice_books"] for row in result["rows"][1:]], ["BILL/1", "BILL/3"]
        )

    def test_a_three_bill_split_is_not_guessed_past_the_candidate_cap(self) -> None:
        """An honest fallback: with too many candidates, only pairs are searched.

        Forty books from one supplier on one date are the cap.  Beyond it the
        999-rupee portal line can only be reached by an unusual three-bill
        combination, and the engine says "no split proven" instead of spending
        the month's time proving it.
        """
        from apps.engine.recon import reconcile

        def month(extra_books: int) -> tuple[list[dict], list[dict]]:
            books = [
                _books(invoice_number="BIG/1", invoice_value=Decimal("400.00")),
                _books(invoice_number="BIG/2", invoice_value=Decimal("300.00")),
                _books(invoice_number="BIG/3", invoice_value=Decimal("299.00")),
            ]
            for index in range(extra_books):
                books.append(
                    _books(
                        invoice_number=f"FILLER/{index}",
                        invoice_value=Decimal(100000 + index),
                    )
                )
            portal = [_gstr(invoice_number="INV-1", invoice_value=Decimal("999.00"))]
            return books, portal

        small = reconcile(*month(10))
        self.assertEqual(_counts(small), {"split_merged": 1, "books_only": 10})

        large = reconcile(*month(60))
        self.assertEqual(_counts(large), {"portal_only": 1, "books_only": 63})
        self.assertNotIn(
            "split_merged", [row["status"] for row in large["rows"]]
        )


class ReconSpeedTests(unittest.TestCase):
    def test_five_hundred_rows_reconcile_in_under_ten_seconds(self) -> None:
        elapsed, result = _timed(500)

        # The pairs and splits this dataset produces are the engine's ordinary
        # answer; the point of the test is the time it takes to reach them.
        self.assertEqual(
            _counts(result), {"books_only": 300, "portal_only": 400, "split_merged": 100}
        )
        self.assertLess(elapsed, 10.0, f"500 rows took {elapsed:.2f}s")

    @unittest.skipUnless(
        LOAD_TEST,
        "set CA_RECON_PERF=1 to run the 2,000-row load test",
    )
    def test_two_thousand_rows_reconcile_in_under_sixty_seconds(self) -> None:
        elapsed, result = _timed(2000)

        self.assertEqual(result["counts"]["books_only"], 1050)
        self.assertEqual(result["counts"]["portal_only"], 1525)
        self.assertEqual(result["counts"]["split_merged"], 475)
        self.assertLess(elapsed, 60.0, f"2,000 rows took {elapsed:.2f}s")


class BankHintAnswersTests(unittest.TestCase):
    """Hinting is a speed change, so the chosen line and text must not move."""

    def test_two_hundred_rows_get_exactly_the_old_hint_text(self) -> None:
        from apps.engine.recon import reconcile

        books, portal = _hint_rows(200)
        result = reconcile(books, portal, BANK_STATEMENT)

        self.assertEqual(result["counts"]["matched"], 200)
        self.assertEqual(len(result["rows"]), 200)
        mismatches = []
        for index, row in enumerate(result["rows"]):
            expected = _legacy_bank_hint(row, books[index], portal[index], BANK_STATEMENT)
            if row["bank_hint"] != expected:
                mismatches.append({"row": index, "new": row["bank_hint"], "old": expected})
        self.assertEqual(mismatches, [])

    def test_hint_text_matches_the_pinned_examples(self) -> None:
        from apps.engine.recon import reconcile

        books, portal = _hint_rows(len(HINT_CASES))
        result = reconcile(books, portal, BANK_STATEMENT)

        self.assertEqual(
            [row["bank_hint"] for row in result["rows"]],
            [
                # Two near-amount lines tie; the earlier bank line wins.
                "2026-07-02 | 11800.40 | NEFT ACME TRADERS",
                # Inside the rupee allowance of 2,500.40.
                "2026-07-12 | 2500.00 | BETA ENTERPRISES",
                # 2.40 away: nothing qualifies.
                "",
                # Credit side carries the money.
                "2026-07-19 | 900.00 | GAMMA SUPPLIES",
                # The later line scores higher, so it wins.
                "2026-07-15 | 5000.00 | NEFT ACME TRADERS",
                # Equal scores: the earlier bank line wins.
                "2026-07-14 | 6400.00 | UPI REF 2002",
                # The bank line has no readable date.
                "4000.00 | GAMMA SUPPLIES",
                # A zero debit is not a debit.
                "2026-07-12 | 3200.00 | BETA ENTERPRISES PAYMENT",
                "",
                "",
            ],
        )

    def test_hint_text_is_unchanged_under_a_tighter_and_looser_allowance(self) -> None:
        from apps.engine.recon import reconcile

        books, portal = _hint_rows(len(HINT_CASES) * 2)
        for tolerance in (Decimal("0"), Decimal("50")):
            with self.subTest(tolerance=str(tolerance)):
                result = reconcile(
                    books, portal, BANK_STATEMENT, amount_tolerance=tolerance
                )
                for index, row in enumerate(result["rows"]):
                    expected = _legacy_bank_hint(
                        row, books[index], portal[index], BANK_STATEMENT, tolerance
                    )
                    self.assertEqual(row["bank_hint"], expected, f"row {index}")

    def test_a_row_without_an_amount_never_gets_a_hint(self) -> None:
        from apps.engine.recon import reconcile

        without_amount = [
            {
                "supplier_gstin": GSTIN,
                "invoice_number": "NO-AMOUNT",
                "invoice_date": "2026-07-12",
                "supplier_name": "Acme Traders",
            }
        ]
        result = reconcile(without_amount, [], BANK_STATEMENT)
        self.assertEqual(result["rows"][0]["status"], "books_only")
        self.assertEqual(result["rows"][0]["bank_hint"], "")

        # Control: the same bill with an amount does get the hint.
        with_amount = [dict(without_amount[0], invoice_value=Decimal("11800.00"))]
        result = reconcile(with_amount, [], BANK_STATEMENT)
        self.assertEqual(
            result["rows"][0]["bank_hint"], "2026-07-02 | 11800.40 | NEFT ACME TRADERS"
        )


class BankHintSpeedTests(unittest.TestCase):
    def test_five_thousand_rows_against_two_thousand_bank_lines_under_sixty_seconds(
        self,
    ) -> None:
        from apps.engine.recon import reconcile

        books, portal, bank = _hint_load_rows(5000, 2000)
        started = time.perf_counter()
        result = reconcile(books, portal, bank)
        elapsed = time.perf_counter() - started

        self.assertEqual(result["counts"]["matched"], 5000)
        self.assertEqual(sum(1 for row in result["rows"] if row["bank_hint"]), 5000)
        self.assertLess(
            elapsed,
            60.0,
            f"5,000 rows against 2,000 bank lines took {elapsed:.2f}s",
        )


class SqliteJournalModeTests(unittest.TestCase):
    """A long import must not lock the whole database for everything else."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        if self._previous is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._previous
        self._tmp.cleanup()

    def test_every_connection_opens_the_database_in_wal_mode(self) -> None:
        from sqlalchemy import text

        from apps.engine.db import get_engine

        engine = get_engine()
        for attempt in ("first", "second"):
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("PRAGMA journal_mode")).scalar(),
                    "wal",
                    f"{attempt} connection is not in WAL mode",
                )
                self.assertEqual(
                    connection.execute(text("PRAGMA synchronous")).scalar(), 1
                )
                # The busy timeout lives on the connection, not in the file, so
                # reading it back proves the hook ran for this new connection.
                self.assertEqual(
                    connection.execute(text("PRAGMA busy_timeout")).scalar(),
                    30000,
                    f"{attempt} connection did not get the busy timeout",
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
