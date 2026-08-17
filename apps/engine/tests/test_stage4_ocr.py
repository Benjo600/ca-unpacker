from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.test_stage3_bank import write_hdfc


class TesseractLookupTests(unittest.TestCase):
    def test_find_and_status_do_not_raise(self) -> None:
        from apps.engine.ocr import find_tesseract, tesseract_status

        found = find_tesseract()
        self.assertTrue(found is None or Path(found).is_file())
        status = tesseract_status()
        self.assertIn("found", status)
        self.assertIn("path", status)
        self.assertIn("note", status)
        self.assertIsInstance(status["found"], bool)
        self.assertIn("cloud", status["note"].lower())


class PasswordContextTests(unittest.TestCase):
    def test_using_password_sets_and_resets(self) -> None:
        from apps.engine.pdf_extract import _active_password, using_password

        self.assertIsNone(_active_password.get())
        with using_password("secret"):
            self.assertEqual(_active_password.get(), "secret")
        self.assertIsNone(_active_password.get())
        try:
            with using_password("temp"):
                self.assertEqual(_active_password.get(), "temp")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        self.assertIsNone(_active_password.get())


class DigitalExtractRegressionTests(unittest.TestCase):
    def test_digital_hdfc_not_replaced_by_ocr(self) -> None:
        from apps.engine.parsers.bank.parser import parse_bank_pdf
        from apps.engine.pdf_extract import extract_pdf

        fixture = ROOT / "test-dump" / "HDFC_Statement_Jul2026.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            generated = write_hdfc(Path(tmp))
            sources = [generated]
            if fixture.is_file():
                sources.append(fixture)
            for path in sources:
                extracted = extract_pdf(path)
                self.assertGreater(len(extracted.lines), 3, path.name)
                self.assertNotEqual(extracted.engine, "tesseract", path.name)
                self.assertNotEqual(extracted.pdf_type, "encrypted", path.name)
                for line in extracted.lines:
                    self.assertGreaterEqual(line.page, 1)
                parsed = parse_bank_pdf(path)
                self.assertGreaterEqual(len(parsed["rows"]), 3, path.name)


class ScanOcrTests(unittest.TestCase):
    def test_image_only_pdf_uses_local_ocr_when_present(self) -> None:
        from apps.engine.ocr import find_tesseract
        from apps.engine.pdf_extract import extract_pdf

        if find_tesseract() is None:
            self.skipTest("tesseract.exe not found; local OCR skipped")
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            self.skipTest("pytesseract not installed; local OCR skipped")

        fixture = ROOT / "test-dump" / "HDFC_Statement_Jul2026.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            source = fixture if fixture.is_file() else write_hdfc(Path(tmp))
            scanned = Path(tmp) / "HDFC_Statement_scan.pdf"
            _write_image_only_pdf(source, scanned)
            extracted = extract_pdf(scanned)
            self.assertTrue(
                extracted.engine == "tesseract" or bool(extracted.lines),
                (extracted.engine, extracted.pdf_type, len(extracted.lines)),
            )
            if extracted.engine == "tesseract":
                self.assertEqual(extracted.pdf_type, "scanned")
            for line in extracted.lines:
                self.assertGreaterEqual(line.page, 1)


class EncryptedPdfTests(unittest.TestCase):
    def test_encrypted_without_password_is_not_a_crash(self) -> None:
        from pypdf import PdfWriter

        from apps.engine.pdf_extract import extract_pdf, using_password

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = write_hdfc(folder)
            locked = folder / "HDFC_locked.pdf"
            writer = PdfWriter()
            writer.append(str(source))
            writer.encrypt("secret")
            with locked.open("wb") as handle:
                writer.write(handle)

            blocked = extract_pdf(locked)
            self.assertEqual(blocked.pdf_type, "encrypted")

            unlocked = extract_pdf(locked, password="secret")
            self.assertNotEqual(unlocked.pdf_type, "encrypted")
            self.assertGreater(len(unlocked.lines), 0)

            with using_password("secret"):
                via_ctx = extract_pdf(locked)
            self.assertNotEqual(via_ctx.pdf_type, "encrypted")
            self.assertGreater(len(via_ctx.lines), 0)


def _write_image_only_pdf(source: Path, dest: Path) -> None:
    import pypdfium2

    document = pypdfium2.PdfDocument(str(source))
    try:
        page = document[0]
        try:
            bitmap = page.render(scale=2)
            try:
                image = bitmap.to_pil().convert("RGB")
                image.save(dest, "PDF", resolution=144.0)
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


if __name__ == "__main__":
    unittest.main()
