from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.pdf_render import crop_png, crop_png_bytes, page_size_pts, render_page_png

from apps.engine.tests.dump_paths import HDFC


class PageSizeTests(unittest.TestCase):
    def test_page_1_has_positive_size(self) -> None:
        width, height = page_size_pts(HDFC, 1)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)


class RenderPageTests(unittest.TestCase):
    def test_render_page_png_matches_scale(self) -> None:
        width_pt, height_pt = page_size_pts(HDFC, 1)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "nested" / "page1.png"
            out = render_page_png(HDFC, 1, dest, scale=2.0)
            self.assertEqual(out, dest)
            self.assertTrue(dest.is_file())
            with Image.open(dest) as image:
                image.load()
                self.assertEqual(image.format, "PNG")
                self.assertAlmostEqual(image.width, width_pt * 2.0, delta=2)
                self.assertAlmostEqual(image.height, height_pt * 2.0, delta=2)


class CropTests(unittest.TestCase):
    def test_crop_from_extracted_bank_row(self) -> None:
        from apps.engine.parsers.bank.parser import parse_bank_pdf

        parsed = parse_bank_pdf(HDFC)
        row = next(
            (
                item
                for item in parsed["rows"]
                if (item.get("debit") or item.get("credit")) and item.get("source_bbox")
            ),
            None,
        )
        self.assertIsNotNone(row, "expected a bank row with debit/credit and source_bbox")
        assert row is not None
        page = int(row["source_page"])
        with tempfile.TemporaryDirectory() as tmp:
            full = Path(tmp) / "full.png"
            crop = Path(tmp) / "crop.png"
            render_page_png(HDFC, page, full, scale=2.0)
            crop_png(HDFC, page, row["source_bbox"], crop, scale=2.0)
            with Image.open(full) as full_img, Image.open(crop) as crop_img:
                full_img.load()
                crop_img.load()
                self.assertLess(crop_img.width, full_img.width)
                self.assertLess(crop_img.height, full_img.height)
                self.assertLess(crop_img.width * crop_img.height, full_img.width * full_img.height)

    def test_invalid_bbox_writes_fallback_strip(self) -> None:
        width_pt, height_pt = page_size_pts(HDFC, 1)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "strip.png"
            crop_png(HDFC, 1, "", dest, scale=2.0)
            self.assertTrue(dest.is_file())
            with Image.open(dest) as image:
                image.load()
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, 0)
                self.assertGreater(image.height, 0)
                self.assertAlmostEqual(image.width, width_pt * 2.0, delta=2)
                self.assertAlmostEqual(image.height, (height_pt * 2.0) / 3.0, delta=3)
                self.assertLess(image.height, height_pt * 2.0 - 1)

    def test_crop_png_bytes_returns_png(self) -> None:
        payload = crop_png_bytes(HDFC, 1, "not-a-bbox")
        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))


class PasswordTests(unittest.TestCase):
    def test_encrypted_pdf_raises_password_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            locked = Path(tmp) / "locked.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            try:
                writer.encrypt("secret", algorithm="RC4-128")
            except TypeError:
                writer.encrypt("secret")
            with locked.open("wb") as handle:
                writer.write(handle)
            dest = Path(tmp) / "out.png"
            with self.assertRaises(ValueError) as missing:
                render_page_png(locked, 1, dest)
            self.assertIn("password", str(missing.exception).lower())
            with self.assertRaises(ValueError) as wrong:
                crop_png(locked, 1, "10.0,10.0,20.0,20.0", dest, password="nope")
            self.assertIn("password", str(wrong.exception).lower())


if __name__ == "__main__":
    unittest.main()
