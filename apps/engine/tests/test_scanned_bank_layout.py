"""Scanned-statement layout regressions.

These reproduce defects seen on a real OCR-only Kotak statement:

* the row serial (``#``) column leaked into the narration,
* the closing balance sat on the line *after* its label, so it was lost,
* the bank profile was decided by a UPI narration (".../hdfc/...") instead of
  the letterhead.
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.parsers.bank import layout
from apps.engine.parsers.bank.parser import _balance_near, parse_bank_pdf
from apps.engine.parsers.bank.patterns import CLOSING_RE, OPENING_RE
from apps.engine.parsers.bank.profiles import detect_profile
from apps.engine.pdf_extract import ExtractedPdf, LineBox, PageText, WordBox
from apps.engine.validators.balance import check_balance


def word(text: str, x: float, y: float, page: int = 1, width: float = 40.0) -> WordBox:
    return WordBox(page=page, text=text, x=x, y=y, width=width, height=8.0)


def kotak_words() -> list[WordBox]:
    """Words for one OCR page: header row, then two transactions."""
    words: list[WordBox] = []
    header_y = 700.0
    for text, x in (
        ("Date", 40.0),
        ("Description", 146.0),
        ("Withdrawal", 385.0),
        ("Deposit", 452.0),
        ("Balance", 514.0),
    ):
        words.append(word(text, x, header_y))

    first = [
        word("1", 16.0, 680.0, width=10.0),
        word("05", 40.0, 680.0, width=18.0),
        word("Jul", 62.0, 680.0, width=16.0),
        word("2026", 82.0, 680.0, width=24.0),
        word("UPI/VISWANATH", 146.0, 680.0, width=70.0),
        word("B", 220.0, 680.0, width=8.0),
        word("UPI-618682727471", 232.0, 680.0, width=80.0),
        word("4,000.00", 452.0, 680.0, width=46.0),
        word("4,011.71", 514.0, 680.0, width=46.0),
    ]
    second = [
        word("2", 16.0, 660.0, width=10.0),
        word("05", 40.0, 660.0, width=18.0),
        word("Jul", 62.0, 660.0, width=16.0),
        word("2026", 82.0, 660.0, width=24.0),
        word("UPI/ALIAKBAR", 146.0, 660.0, width=68.0),
        word("C/YESB/655281313839/UPI", 218.0, 660.0, width=120.0),
        word("UPI-618682731260", 342.0, 660.0, width=76.0),
        word("3,800.00", 385.0, 660.0, width=46.0),
        word("211.71", 514.0, 660.0, width=40.0),
    ]
    words.extend(first)
    words.extend(second)
    return words


class ScannedNarrationTests(unittest.TestCase):
    def test_serial_column_stays_out_of_narration(self) -> None:
        words = kotak_words()
        profile = detect_profile("Kotak Mahindra Bank", "statement.pdf")
        rows = layout.rows_from_words(words, profile, "statement.pdf")

        self.assertEqual(len(rows), 2)
        descriptions = [row["description"] for row in rows]
        self.assertFalse(
            any(text.startswith("1 ") for text in descriptions),
            f"serial leaked into narration: {descriptions}",
        )
        self.assertTrue(descriptions[0].startswith("UPI/VISWANATH"), descriptions[0])
        self.assertTrue(descriptions[1].startswith("UPI/ALIAKBAR"), descriptions[1])


class GluedDateMergeTests(unittest.TestCase):
    """A date with one OCR-glued digit must not swallow the next printed row.

    Reproduces ``Axis_scanned_image_128_Jul2026.png`` from the stress corpus:
    OCR returned ``07/07/20261`` for the date, ``DATE_RE`` found no date, and
    the whole 07/07 transaction was folded into the 04/07 row.  The merged row
    then carried a debit of 1,20,394.25 instead of 1,767.25 and 589.25, and an
    inferred-from-balance row hid the mistake.
    """

    def axis_words(self) -> list[WordBox]:
        return [
            word("Axis Bank Account Statement", 105.7, 2176.3, width=502.5),
            word("Account Number 7999619530955", 105.7, 2115.0, width=520.1),
            word("IFSC UTIB0000123", 108.0, 2054.9, width=298.2),
            word("Statement Period 01/07/2026 to 31/07/2026", 106.8, 1992.4, width=759.6),
            word("Opening Balance 119111.00", 106.8, 1931.1, width=463.7),
            word("Date", 104.5, 1869.8, width=83.4),
            word("Narration", 329.9, 1872.1, width=170.2),
            word("Type", 826.5, 1866.2, width=83.4),
            word("Amount", 1190.4, 1871.0, width=118.6),
            word("Balance", 1462.8, 1868.6, width=138.5),
            word("01/07/2026 NEFT CR ACME TRADERS INV", 108.0, 1809.7, width=673.9),
            word("Deposit", 826.5, 1806.1, width=138.5),
            word("3050.50", 1171.7, 1808.5, width=137.4),
            word("122161.50", 1428.8, 1810.8, width=170.2),
            word("04/07/2026", 108.0, 1749.5, width=194.9),
            word("5 UPI merchant LAKSHMI PRI", 286.5, 1749.5, width=490.7),
            word("Withdrawal", 828.8, 1748.4, width=190.2),
            word("1767.25", 1171.7, 1747.2, width=137.4),
            word("120394.25", 1427.6, 1749.5, width=172.6),
            # The defect: one stray OCR digit stuck to the date token.
            word("07/07/20261", 109.2, 1688.2, width=228.9),
            word("UPI merchant NORTH RETAI", 327.5, 1690.6, width=448.5),
            word("Withdrawal", 827.7, 1687.1, width=191.4),
            word("589.25", 1190.4, 1689.4, width=117.4),
            word("119805.00", 1428.8, 1688.2, width=170.2),
            word("10/07/2026", 106.8, 1626.9, width=196.1),
            word("NEFT CR SHREE STEELS INV", 326.4, 1626.9, width=452.0),
            word("Deposit", 826.5, 1623.4, width=137.4),
            word("3729.50", 1171.7, 1624.6, width=136.2),
            word("123534.50", 1428.8, 1625.7, width=170.2),
            word("13/07/2026 UPI merchant KIRAN AGENC", 106.8, 1564.4, width=671.5),
            word("Withdrawal", 828.8, 1564.4, width=190.2),
            word("1701.25", 1171.7, 1563.3, width=137.4),
            word("121833.25", 1427.6, 1563.3, width=173.8),
            word("Closing Balance 121833.25", 106.8, 1503.1, width=464.9),
        ]

    def extracted(self) -> ExtractedPdf:
        words = self.axis_words()
        text = "\n".join(item.text for item in sorted(words, key=lambda item: -item.y))
        lines = [
            LineBox(page=1, text=item.text, x=item.x, y=item.y, width=item.width, height=item.height)
            for item in words
        ]
        return ExtractedPdf(
            pdf_type="image_based",
            page_count=1,
            pages=[PageText(page=1, text=text)],
            lines=lines,
            words=words,
            engine="rapidocr",
            page_methods={1: "rapidocr"},
        )

    def test_glued_date_is_recognised_and_does_not_over_match(self) -> None:
        from apps.engine.parsers.bank.money import date_match

        self.assertEqual(date_match("07/07/20261 UPI merchant").group(1), "07/07/2026")
        self.assertIsNone(date_match("05/07/2026123"))  # a real reference number
        self.assertEqual(
            date_match("05/07/2026 1 UPI merchant").group(1), "05/07/2026"
        )  # normally spaced date still matches the plain form

    def test_two_printed_rows_stay_separate(self) -> None:
        profile = detect_profile("Axis Bank Account Statement", "statement.png")
        rows = layout.rows_from_words(self.axis_words(), profile, "statement.png")

        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [row["date"] for row in rows],
            ["2026-07-01", "2026-07-04", "2026-07-07", "2026-07-10", "2026-07-13"],
        )
        by_date = {row["date"]: row for row in rows}
        self.assertEqual(by_date["2026-07-04"]["debit"], 1767.25)
        self.assertEqual(by_date["2026-07-07"]["debit"], 589.25)
        self.assertEqual(by_date["2026-07-04"]["balance"], 120394.25)
        self.assertFalse(
            any(row["debit"] == 120394.25 for row in rows),
            "the merged amount is still being emitted",
        )

    def test_totals_and_balance_come_from_the_printed_rows(self) -> None:
        parsed = parse_bank_pdf(Path("Axis_scanned_image_128_Jul2026.png"), extracted=self.extracted())

        self.assertEqual(len(parsed["rows"]), 5)
        self.assertEqual(parsed["inferred_count"], 0, "a balance repair papered over a lost row")
        self.assertAlmostEqual(
            sum(row["debit"] or 0 for row in parsed["rows"]), 4057.75, places=2
        )
        self.assertAlmostEqual(
            sum(row["credit"] or 0 for row in parsed["rows"]), 6780.00, places=2
        )
        check = check_balance(
            parsed["rows"], parsed["opening_balance"], parsed["stated_closing"]
        )
        self.assertEqual(check["status"], "match", check)
        self.assertEqual(parsed["warnings"], [])


class ClosingBalanceTests(unittest.TestCase):
    def summary_pdf(self) -> ExtractedPdf:
        lines = [
            LineBox(page=6, text="Account Summary", x=0, y=760, width=200, height=10),
            LineBox(
                page=6,
                text="Particulars Opening Balance Closing Balance",
                x=0,
                y=740,
                width=400,
                height=10,
            ),
            LineBox(
                page=6,
                text="Savings Account (SA): 11.71 1,177.74",
                x=0,
                y=720,
                width=400,
                height=10,
            ),
        ]
        return ExtractedPdf(
            pdf_type="scanned",
            page_count=6,
            pages=[
                PageText(page=1, text="Opening Balance 11.71"),
                PageText(page=6, text="Closing Balance 1,177.74"),
            ],
            lines=lines,
        )

    def test_closing_balance_read_from_summary_block(self) -> None:
        pdf = self.summary_pdf()
        self.assertEqual(_balance_near(pdf, CLOSING_RE), Decimal("1177.74"))

    def test_opening_balance_does_not_pick_the_closing_column(self) -> None:
        pdf = self.summary_pdf()
        # The parser asks for the first amount on a two-value summary row.
        self.assertEqual(_balance_near(pdf, OPENING_RE, pick="first"), Decimal("11.71"))


class ProfileLetterheadTests(unittest.TestCase):
    def test_upi_narration_does_not_override_the_letterhead(self) -> None:
        header = "\n".join(
            [
                "kotak8ll kotak",
                "Kotak Mahindra Bank",
                "Account Statement 01 Jul 2026 - 31 Jul 2026",
                "MICR560485102IFSC CodeKKBK0008120",
                "Savings Account Transactions",
                "1 05 Jul 2026 palac/hdfc/655731252662/upi 3,199.00 66.71",
            ]
        )
        self.assertEqual(detect_profile(header, "statement.pdf").key, "kotak")


if __name__ == "__main__":
    unittest.main()
