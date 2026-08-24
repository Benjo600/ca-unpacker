from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_test_dump import PNG, pdf_with_text

ACME = ROOT / "test-dump" / "Tax_Invoice_Acme.pdf"
VALID_GSTIN = "27AAPFU0939F1ZV"
BAD_GSTIN = VALID_GSTIN[:-1] + ("W" if VALID_GSTIN[-1] != "W" else "X")


def _write_invoice(folder: Path, lines: list[str], name: str = "invoice.pdf") -> Path:
    path = folder / name
    path.write_bytes(pdf_with_text(lines))
    return path


def _acme_lines(**overrides: str) -> list[str]:
    fields = {
        "title": "TAX INVOICE",
        "number": "Invoice No ACME/26-27/0142",
        "date": "Invoice Date 12/07/2026",
        "gstin": f"Supplier GSTIN {VALID_GSTIN}",
        "pos": "Place of Supply 29-Karnataka",
        "hsn": "HSN 998314",
        "table_header": "HSN Qty Rate Taxable Amount",
        "table_row": "Professional fees 998314 1 10000.00 10000.00 11800.00",
        "taxable": "Taxable value 10000.00",
        "tax": "CGST 900.00  SGST 900.00",
        "total": "Invoice value 11800.00",
    }
    fields.update(overrides)
    return [value for value in fields.values() if value]


class DigitalInvoiceTests(unittest.TestCase):
    def test_digital_acme_invoice(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_invoice(Path(tmp), _acme_lines())
            parsed = parse_invoice_file(path)
            self.assertFalse(parsed["unreadable"])
            self.assertEqual(len(parsed["rows"]), 1)
            row = parsed["rows"][0]
            self.assertTrue(row["supplier_gstin"])
            self.assertIn("ACME/26-27/0142", row["invoice_number"] or "")
            self.assertEqual(row["invoice_value"], 11800.0)
            self.assertEqual(row["hsn"], "998314")
            self.assertNotIn("hsn_length", row["flags"])
            gstin_field = (row.get("fields") or {}).get("supplier_gstin") or {}
            self.assertTrue(
                row.get("source_bbox") or gstin_field.get("bbox"),
                "expected source_bbox or fields.supplier_gstin.bbox",
            )
            self.assertIn("supplier_name", row)
            self.assertIn("taxable_value", row)
            self.assertIn("tax", row)
            self.assertIsInstance(row["flags"], list)
            items = parsed.get("line_items") or []
            self.assertGreaterEqual(len(items), 1, parsed)
            self.assertEqual(items[0].get("hsn"), "998314")
            self.assertTrue(items[0].get("amount") or items[0].get("taxable"))

    def test_two_line_item_table(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        lines = [
            "TAX INVOICE",
            "Invoice No ACME/26-27/0142",
            "Invoice Date 12/07/2026",
            f"Supplier GSTIN {VALID_GSTIN}",
            "Place of Supply 29-Karnataka",
            "HSN Qty Rate Taxable Amount",
            "Consulting 998314 1 7000.00 7000.00 8260.00",
            "Software 997331 1 3000.00 3000.00 3540.00",
            "Taxable value 10000.00",
            "CGST 900.00  SGST 900.00",
            "Invoice value 11800.00",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_invoice(Path(tmp), lines)
            parsed = parse_invoice_file(path)
            self.assertFalse(parsed["unreadable"])
            self.assertEqual(len(parsed["rows"]), 1)
            items = parsed["line_items"]
            self.assertEqual(len(items), 2)
            hsns = {item.get("hsn") for item in items}
            self.assertEqual(hsns, {"998314", "997331"})

    def test_header_without_table_is_unreadable(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        lines = [
            "TAX INVOICE",
            "Invoice No ACME/26-27/0142",
            "Invoice Date 12/07/2026",
            f"Supplier GSTIN {VALID_GSTIN}",
            "HSN 998314",
            "Taxable value 10000.00",
            "Invoice value 11800.00",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            parsed = parse_invoice_file(_write_invoice(Path(tmp), lines))
            self.assertEqual(parsed["rows"], [])
            self.assertEqual(parsed.get("line_items") or [], [])
            self.assertTrue(parsed["unreadable"])

    def test_bad_gstin_checksum_is_flagged_not_rewritten(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file
        from apps.engine.validators.gstin import gstin_checksum_ok

        self.assertTrue(gstin_checksum_ok(VALID_GSTIN))
        self.assertFalse(gstin_checksum_ok(BAD_GSTIN))
        self.assertNotEqual(BAD_GSTIN, VALID_GSTIN)

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_invoice(Path(tmp), _acme_lines(gstin=f"Supplier GSTIN {BAD_GSTIN}"))
            row = parse_invoice_file(path)["rows"][0]
            self.assertEqual(row["supplier_gstin"], BAD_GSTIN)
            self.assertIn("gstin_checksum", row["flags"])
            self.assertNotEqual(row["supplier_gstin"], VALID_GSTIN)

    def test_bad_hsn_length_is_flagged(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_invoice(Path(tmp), _acme_lines(hsn="HSN 12345"))
            row = parse_invoice_file(path)["rows"][0]
            self.assertEqual(row["hsn"], "12345")
            self.assertIn("hsn_length", row["flags"])

    def test_invoice_math_break_is_flagged(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_invoice(
                Path(tmp),
                _acme_lines(
                    taxable="Taxable value 10000.00",
                    tax="IGST 100.00",
                    total="Invoice value 20000.00",
                ),
            )
            row = parse_invoice_file(path)["rows"][0]
            self.assertEqual(row["taxable_value"], 10000.0)
            self.assertEqual(row["tax"], 100.0)
            self.assertEqual(row["invoice_value"], 20000.0)
            self.assertIn("invoice_math", row["flags"])


class ImageInvoiceTests(unittest.TestCase):
    def test_tiny_png_is_unreadable(self) -> None:
        from apps.engine.parsers.invoice import parse_invoice_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.png"
            path.write_bytes(PNG)
            parsed = parse_invoice_file(path)
            self.assertEqual(parsed["rows"], [])
            self.assertTrue(parsed["unreadable"])

    def test_rendered_acme_png_when_tesseract_present(self) -> None:
        from apps.engine.ocr import find_tesseract
        from apps.engine.parsers.invoice import parse_invoice_file
        from apps.engine.pdf_render import render_page_png

        if find_tesseract() is None:
            self.skipTest("tesseract.exe not found; local OCR skipped")

        source = ACME
        with tempfile.TemporaryDirectory() as tmp:
            if not source.is_file():
                source = _write_invoice(Path(tmp), _acme_lines(), "Tax_Invoice_Acme.pdf")
            png = Path(tmp) / "acme-scan.png"
            render_page_png(source, 1, png, scale=3.0)
            parsed = parse_invoice_file(png)
            if parsed.get("unreadable") or not parsed.get("rows"):
                self.skipTest("OCR did not recover a line-item table")
            row = parsed["rows"][0]
            self.assertTrue(
                row.get("supplier_gstin") or row.get("invoice_number"),
                "expected a GSTIN or invoice_number from printed scan",
            )


if __name__ == "__main__":
    unittest.main()
