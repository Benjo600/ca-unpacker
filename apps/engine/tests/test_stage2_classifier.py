from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.classifier import classify_from_text, classify_path
from apps.engine.db import reset_engine
from apps.engine.dump import collect_paths, ingest_paths, list_period_files, override_kind, start_job
from apps.engine.firm import save_firm
from apps.engine.clients import create_client
from apps.engine.periods import create_period, suggested_period_label


class ClassifierTests(unittest.TestCase):
    def test_legacy_xls_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.xls"
            path.write_bytes(b"PK\x03\x04fake")
            result = classify_path(path)
            self.assertEqual(result.kind, "unknown")
            self.assertEqual(
                result.reason,
                "legacy .xls is not supported — export .xlsx or .csv",
            )

    def test_gstr2b_filename_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GSTR-2B_July.json"
            path.write_text(json.dumps({"gstin": "27AAPFU0939F1ZV", "data": {"docdata": {"b2b": []}}}), encoding="utf-8")
            result = classify_path(path)
            self.assertEqual(result.kind, "gstr_2b")

    def test_gstr1_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "return.json"
            path.write_text(json.dumps({"gstin": "27AAPFU0939F1ZV", "fp": "072026", "b2b": []}), encoding="utf-8")
            self.assertEqual(classify_path(path).kind, "gstr_1")

    def test_gstr3b_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monthly.json"
            path.write_text(json.dumps({"gstin": "27AAPFU0939F1ZV", "sup_details": {}}), encoding="utf-8")
            self.assertEqual(classify_path(path).kind, "gstr_3b")

    def test_tally_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daybook.xml"
            path.write_text("<ENVELOPE><TALLYMESSAGE><VOUCHER></VOUCHER></TALLYMESSAGE></ENVELOPE>", encoding="utf-8")
            self.assertEqual(classify_path(path).kind, "tally")

    def test_tally_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "export.xml"
            xml.write_text("<ENVELOPE><TALLYMESSAGE></TALLYMESSAGE></ENVELOPE>", encoding="utf-8")
            zipped = Path(tmp) / "backup.zip"
            with zipfile.ZipFile(zipped, "w") as archive:
                archive.write(xml, arcname="export.xml")
            self.assertEqual(classify_path(zipped).kind, "tally")

    def test_zoho_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.csv"
            path.write_text("Invoice Number,Invoice Date,GST Treatment\nINV-1,2026-07-01,taxable\n", encoding="utf-8")
            self.assertEqual(classify_path(path).kind, "zoho")

    def test_image_without_hint_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.jpg"
            path.write_bytes(b"not-a-real-image")
            self.assertEqual(classify_path(path).kind, "unknown")

    def test_one_by_one_png_is_unknown(self) -> None:
        from make_test_dump import PNG

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invoice_photo.png"
            path.write_bytes(PNG)
            result = classify_path(path)
            self.assertEqual(result.kind, "unknown")
            self.assertIn("no printed invoice text", result.reason)

    def test_digital_tax_invoice_pdf_is_invoice(self) -> None:
        from make_test_dump import pdf_with_text

        fixture = ROOT / "test-dump" / "Tax_Invoice_Acme.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            path = fixture if fixture.is_file() else Path(tmp) / "Tax_Invoice_Acme.pdf"
            if not fixture.is_file():
                path.write_bytes(
                    pdf_with_text(
                        [
                            "TAX INVOICE",
                            "Invoice No ACME/26-27/0142",
                            "Supplier GSTIN 27AAPFU0939F1ZV",
                            "Place of Supply 29-Karnataka",
                            "HSN 998314",
                            "Taxable value 10000.00",
                        ]
                    )
                )
            result = classify_path(path)
            self.assertEqual(result.kind, "invoice")

    def test_rendered_invoice_png_is_invoice_when_tesseract(self) -> None:
        from apps.engine.ocr import find_tesseract

        if find_tesseract() is None:
            self.skipTest("tesseract.exe not found; local OCR skipped")
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            self.skipTest("pytesseract not installed; local OCR skipped")

        with tempfile.TemporaryDirectory() as tmp:
            png_path = Path(tmp) / "printed_bill.png"
            _render_invoice_png(png_path)
            result = classify_path(png_path)
            self.assertEqual(result.kind, "invoice", result.reason)

    def test_bank_text_signals(self) -> None:
        text = "Opening Balance 100\nWithdrawal 20\nDeposit 5\nClosing Balance 85\nNarration ATM"
        result = classify_from_text("stmt.pdf", 12, text)
        self.assertEqual(result.kind, "bank")

    def test_invoice_text_signals(self) -> None:
        text = "TAX INVOICE\nInvoice No 88\nGSTIN 27AAPFU0939F1ZV\nHSN 9983"
        result = classify_from_text("doc.pdf", 1, text)
        self.assertEqual(result.kind, "invoice")


class DumpCopyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        reset_engine()
        save_firm("Test firm")
        self.client = create_client("Acme")
        self.period = create_period(self.client["id"], "Jul 2026")

    def tearDown(self) -> None:
        reset_engine()
        self._tmp.cleanup()

    def test_suggested_label_format(self) -> None:
        from datetime import date

        self.assertEqual(suggested_period_label(date(2026, 8, 13)), "Aug 2026")

    def test_copy_in_and_override(self) -> None:
        source_dir = Path(self._tmp.name) / "inbox"
        source_dir.mkdir()
        json_path = source_dir / "GSTR2B.json"
        json_path.write_text(json.dumps({"data": {"docdata": {}}}), encoding="utf-8")
        odd = source_dir / "notes.docx"
        odd.write_bytes(b"xx")

        job = start_job(self.period["id"])
        ingest_paths(job["id"], [str(source_dir)])
        files = list_period_files(self.period["id"])
        kinds = {row["original_name"]: row["kind"] for row in files}
        self.assertEqual(kinds["GSTR2B.json"], "gstr_2b")
        self.assertEqual(kinds["notes.docx"], "unknown")

        unknown = next(row for row in files if row["original_name"] == "notes.docx")
        self.assertTrue(unknown["needs_review"])
        updated = override_kind(unknown["id"], "invoice")
        self.assertEqual(updated["kind"], "invoice")
        self.assertFalse(updated["needs_review"])

        dest = Path(self._tmp.name) / "CAUnpacker" / "files" / unknown["storage_key"]
        self.assertTrue(dest.exists())
        self.assertTrue(json_path.exists())

    def test_collect_folder(self) -> None:
        folder = Path(self._tmp.name) / "mix"
        folder.mkdir()
        (folder / "a.pdf").write_bytes(b"%PDF")
        (folder / ".hidden").write_bytes(b"x")
        paths = collect_paths([str(folder)])
        self.assertEqual([p.name for p in paths], ["a.pdf"])


def _render_invoice_png(dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    lines = (
        "TAX INVOICE",
        "Invoice No ACME/26-27/0142",
        "Supplier GSTIN 27AAPFU0939F1ZV",
        "Place of Supply 29-Karnataka",
        "HSN 998314",
        "Taxable value 10000.00",
    )
    top = 48
    for line in lines:
        draw.text((48, top), line, fill="black", font=font)
        top += 70
    image.save(dest, "PNG")


if __name__ == "__main__":
    unittest.main()
