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
from apps.engine.parsers.bank.parser import _balance_near
from apps.engine.parsers.bank.patterns import CLOSING_RE, OPENING_RE
from apps.engine.parsers.bank.profiles import detect_profile
from apps.engine.pdf_extract import ExtractedPdf, LineBox, PageText, WordBox


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
