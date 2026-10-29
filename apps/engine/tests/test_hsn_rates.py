from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_test_dump import pdf_with_text

VALID_GSTIN = "27AAPFU0939F1ZV"


def _invoice_lines(hsn: str, taxable: str, tax: str) -> list[str]:
    return [
        "TAX INVOICE",
        "Invoice No RATE/26-27/0001",
        "Invoice Date 12/07/2026",
        f"Supplier GSTIN {VALID_GSTIN}",
        "Place of Supply 29-Karnataka",
        f"HSN {hsn}",
        "HSN Qty Rate Taxable Amount",
        f"Goods {hsn} 1 {taxable} {taxable} 11800.00",
        f"Taxable value {taxable}",
        tax,
        "Invoice value 11800.00",
    ]


class HsnRateTableTests(unittest.TestCase):
    def test_table_covers_goods_and_services(self) -> None:
        from apps.engine.validators.hsn_rates import GOODS_RATES, SAC_RATES

        self.assertGreaterEqual(len(GOODS_RATES), 80)
        self.assertLessEqual(len(GOODS_RATES), 110)
        self.assertGreaterEqual(len(SAC_RATES), 20)
        self.assertLessEqual(len(SAC_RATES), 30)
        self.assertFalse(set(GOODS_RATES) & set(SAC_RATES))
        for code, (rate, label) in {**GOODS_RATES, **SAC_RATES}.items():
            self.assertRegex(code, r"^\d{4}$|^\d{6}$")
            self.assertIn(rate, {0, 5, 12, 18, 28, 40})
            self.assertTrue(label.strip())

    def test_lookup_order_six_digit_beats_four_digit(self) -> None:
        from apps.engine.validators.hsn_rates import expected_rate

        # 2202 heading carries 40 (aerated); the 6-digit 220299 sits at 5.
        self.assertEqual(expected_rate("2202"), 40)
        self.assertEqual(expected_rate("220299"), 5)

    def test_lookup_order_four_digit_heading_for_longer_codes(self) -> None:
        from apps.engine.validators.hsn_rates import expected_rate

        self.assertEqual(expected_rate("1006"), 0)
        self.assertEqual(expected_rate("100630"), 0)
        self.assertEqual(expected_rate("10063010"), 0)
        self.assertEqual(expected_rate("998314"), 18)

    def test_lookup_order_prefix_fallback(self) -> None:
        from apps.engine.validators.hsn_rates import GOODS_RATES, expected_rate

        # Only the 6-digit children of 8483 are curated, so 8483 resolves by prefix.
        self.assertNotIn("8483", GOODS_RATES)
        self.assertEqual(expected_rate("8483"), 18)
        self.assertEqual(expected_rate("848340"), 18)
        # 9963 mixes 5% and 18%, so the prefix is ambiguous and must not guess.
        self.assertIsNone(expected_rate("9963"))

    def test_unknown_and_junk_codes_are_none(self) -> None:
        from apps.engine.validators.hsn_rates import expected_rate

        self.assertIsNone(expected_rate(None))
        self.assertIsNone(expected_rate(""))
        self.assertIsNone(expected_rate("abc"))
        self.assertIsNone(expected_rate("12"))
        self.assertIsNone(expected_rate("0000"))
        self.assertIsNone(expected_rate(object()))


class HsnRateFlagTests(unittest.TestCase):
    def test_correct_rate_is_not_flagged(self) -> None:
        from apps.engine.validators.hsn_rates import rate_flags

        self.assertEqual(rate_flags("1006", 0), [])
        self.assertEqual(rate_flags("998314", 18), [])
        self.assertEqual(rate_flags("8481", 18.0), [])
        self.assertEqual(rate_flags("HSN 1006", "0%"), [])

    def test_rounded_rate_is_not_flagged(self) -> None:
        from apps.engine.validators.hsn_rates import rate_flags

        self.assertEqual(rate_flags("8481", 17.6), [])
        self.assertEqual(rate_flags("8481", 18.4), [])

    def test_wrong_rate_is_flagged(self) -> None:
        from apps.engine.validators.hsn_rates import FLAG, rate_flags

        self.assertEqual(rate_flags("1006", 18), [FLAG])
        self.assertEqual(rate_flags("8481", 5), [FLAG])
        self.assertEqual(rate_flags("998314", 12), [FLAG])
        self.assertEqual(rate_flags("1006", "18%"), [FLAG])

    def test_dual_band_codes_accept_either_rate(self) -> None:
        """Apparel, footwear, hotels and restaurants price by MRP / tariff band.

        Both bands are legitimate, so neither may be flagged — a pack that
        accuses a correct 18% shirt is worse than no check at all.
        """
        from apps.engine.validators.hsn_rates import accepted_rates, rate_flags

        for code in ("6109", "6403", "6205", "996331"):
            self.assertEqual(sorted(accepted_rates(code)), [5, 18], code)
            self.assertEqual(rate_flags(code, 5), [], code)
            self.assertEqual(rate_flags(code, 18), [], code)
            self.assertEqual(rate_flags(code, 12), ["hsn_rate_suspect"], code)

    def test_unknown_code_or_missing_rate_is_not_flagged(self) -> None:
        from apps.engine.validators.hsn_rates import rate_flags

        self.assertEqual(rate_flags("0000", 18), [])
        self.assertEqual(rate_flags(None, 18), [])
        self.assertEqual(rate_flags("1006", None), [])
        self.assertEqual(rate_flags("1006", "n/a"), [])

    def test_missing_or_zero_taxable_does_not_crash(self) -> None:
        from apps.engine.validators.hsn_rates import derive_charged_rate, hsn_rate_flags

        self.assertIsNone(derive_charged_rate(None, 100))
        self.assertIsNone(derive_charged_rate(0, 100))
        self.assertIsNone(derive_charged_rate(100, None))
        self.assertEqual(derive_charged_rate(1000, 180), 18.0)
        self.assertEqual(hsn_rate_flags("1006", taxable=None, tax=None), [])
        self.assertEqual(hsn_rate_flags("1006", taxable=0, tax=180), [])
        self.assertEqual(hsn_rate_flags("1006", taxable=1000, tax=180), ["hsn_rate_suspect"])
        self.assertEqual(hsn_rate_flags("1006", tax_percent=18), ["hsn_rate_suspect"])
        self.assertEqual(hsn_rate_flags("1006", tax_percent=0), [])


class HsnRateParserTests(unittest.TestCase):
    def test_invoice_row_carries_the_rate_flag(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "wrong.pdf"
            wrong.write_bytes(pdf_with_text(_invoice_lines("1006", "10000.00", "CGST 900.00  SGST 900.00")))
            right = Path(tmp) / "right.pdf"
            right.write_bytes(pdf_with_text(_invoice_lines("998314", "10000.00", "CGST 900.00  SGST 900.00")))
            wrong_row = parse_invoice_file(wrong)["rows"][0]
            right_row = parse_invoice_file(right)["rows"][0]

        self.assertEqual(wrong_row["hsn"], "1006")
        self.assertEqual(wrong_row["taxable_value"], 10000.0)
        self.assertIn("hsn_rate_suspect", wrong_row["flags"])
        self.assertNotIn("hsn_length", wrong_row["flags"])
        self.assertNotIn("hsn_rate_suspect", right_row["flags"])

    def test_zoho_row_carries_the_rate_flag(self) -> None:
        from apps.engine.parsers.zoho import parse_zoho_file

        header = (
            "Invoice Number,GST Identification Number (GSTIN),"
            "HSN/SAC,Taxable Value,Tax Amount\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zoho_gst.csv"
            path.write_text(
                header + f"INV-9,{VALID_GSTIN},1006,1000,180\n" + f"INV-10,{VALID_GSTIN},998314,1000,180\n",
                encoding="utf-8",
            )
            rows = parse_zoho_file(path)["rows"]

        self.assertEqual(len(rows), 2)
        self.assertIn("hsn_rate_suspect", rows[0]["flags"])
        self.assertNotIn("hsn_rate_suspect", rows[1]["flags"])


if __name__ == "__main__":
    unittest.main()
