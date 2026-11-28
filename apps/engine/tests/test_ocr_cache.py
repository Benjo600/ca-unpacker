from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Printed text a scanned bank statement would carry.  It gives the classifier
# four bank hints (account number, opening balance, withdrawal, closing
# balance) and the parser a dated transaction.
BANK_TEXT_LINES = (
    "Account Number 123456789012",
    "Opening Balance 1,000.00",
    "01/07/2026 Withdrawal 100.00 900.00",
    "Closing Balance 900.00",
)


def _page_png(path: Path, size: tuple[int, int] = (160, 120)) -> Path:
    from PIL import Image

    Image.new("RGB", size, "white").save(path, "PNG")
    return path


def _words_for(
    lines: tuple[str, ...] | list[str],
) -> list[tuple[float, float, float, float, str, float | None]]:
    words: list[tuple[float, float, float, float, str, float | None]] = []
    for row_index, line in enumerate(lines):
        y = 700.0 - row_index * 20.0
        x = 40.0
        for token in line.split():
            words.append((x, y, 30.0, 10.0, token, 0.95))
            x += 35.0
    return words


@contextmanager
def stubbed_ocr(lines=BANK_TEXT_LINES, calls: list[str] | None = None):
    """Replace the OCR worker with a counting stub.

    ``_rapidocr_words`` is the function that actually drives the engine, so
    counting its calls counts real OCR work.
    """
    calls = calls if calls is not None else []
    words = _words_for(lines)

    def worker(image_path, page_width_pts, page_height_pts, scale):
        calls.append(str(image_path))
        return list(words), "rapidocr"

    with (
        patch("apps.engine.ocr.ocr_available", return_value=True),
        patch("apps.engine.ocr._rapidocr_words", side_effect=worker),
        patch("apps.engine.ocr._tesseract_words", return_value=([], "none")),
    ):
        yield calls


class ImageExtractionCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        from apps.engine.ocr import clear_extraction_cache, extraction_cache_info

        clear_extraction_cache()
        self.info = extraction_cache_info

    def tearDown(self) -> None:
        from apps.engine.ocr import clear_extraction_cache

        clear_extraction_cache()

    def test_second_extract_reuses_the_first_ocr_run(self) -> None:
        from apps.engine.ocr import extract_image

        with tempfile.TemporaryDirectory() as tmp:
            path = _page_png(Path(tmp) / "statement.png")
            with stubbed_ocr() as calls:
                first = extract_image(path)
                second = extract_image(path)

        self.assertEqual(len(calls), 1, "the same file was OCR'd twice")
        self.assertEqual(first, second)
        self.assertEqual(self.info()["entries"], 1)

    def test_changed_file_runs_ocr_again(self) -> None:
        from apps.engine.ocr import extract_image

        with tempfile.TemporaryDirectory() as tmp:
            path = _page_png(Path(tmp) / "statement.png")
            with stubbed_ocr() as calls:
                extract_image(path)
                self.assertEqual(len(calls), 1)
                # Same bytes, new timestamp: the file counts as replaced.
                stat = path.stat()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
                extract_image(path)

        self.assertEqual(len(calls), 2, "a re-touched file returned stale OCR text")

    def test_rewritten_file_does_not_return_old_text(self) -> None:
        from apps.engine.ocr import extract_image

        with tempfile.TemporaryDirectory() as tmp:
            path = _page_png(Path(tmp) / "statement.png")
            with stubbed_ocr() as calls:
                first = extract_image(path)
                _page_png(path, size=(200, 140))
                second = extract_image(path)

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first.engine, "none")
        self.assertTrue(second.lines)

    def test_two_files_do_not_collide(self) -> None:
        from apps.engine.ocr import extract_image

        with tempfile.TemporaryDirectory() as tmp:
            one = _page_png(Path(tmp) / "one.png")
            two = _page_png(Path(tmp) / "two.png")
            with stubbed_ocr() as calls:
                extract_image(one)
                extract_image(two)
                extract_image(one)
                extract_image(two)

        self.assertEqual(len(calls), 2, "each distinct file must be OCR'd once")
        self.assertEqual(self.info()["entries"], 2)

    def test_cache_never_holds_more_than_its_entry_cap(self) -> None:
        from apps.engine import ocr

        with tempfile.TemporaryDirectory() as tmp:
            paths = [
                _page_png(Path(tmp) / f"statement-{index}.png") for index in range(4)
            ]
            with patch.object(ocr, "_EXTRACTION_CACHE_MAX_ENTRIES", 2):
                with stubbed_ocr() as calls:
                    for path in paths:
                        ocr.extract_image(path)

        self.assertEqual(len(calls), 4, "eviction must not change OCR results")
        self.assertLessEqual(self.info()["entries"], 2)

    def test_cache_never_holds_more_than_its_byte_budget(self) -> None:
        from apps.engine import ocr

        with tempfile.TemporaryDirectory() as tmp:
            paths = [
                _page_png(Path(tmp) / f"statement-{index}.png") for index in range(5)
            ]
            with stubbed_ocr():
                ocr.extract_image(paths[0])
            entry_bytes = self.info()["bytes"]
            self.assertGreater(entry_bytes, 0)

            ocr.clear_extraction_cache()
            with patch.object(ocr, "_EXTRACTION_CACHE_MAX_BYTES", entry_bytes * 2):
                with stubbed_ocr():
                    for path in paths:
                        ocr.extract_image(path)
                info = self.info()

        self.assertLessEqual(info["bytes"], entry_bytes * 2)
        self.assertLessEqual(info["entries"], 2)
        self.assertGreaterEqual(info["entries"], 1, "nothing was cached at all")

    def test_empty_ocr_result_is_not_cached(self) -> None:
        from apps.engine.ocr import extract_image

        with tempfile.TemporaryDirectory() as tmp:
            path = _page_png(Path(tmp) / "blank.png")
            with (
                patch("apps.engine.ocr.ocr_available", return_value=False),
            ):
                extract_image(path)

        self.assertEqual(self.info()["entries"], 0)

    def test_classifier_and_parser_share_one_ocr_pass(self) -> None:
        from apps.engine.classifier import classify_path
        from apps.engine.parsers.bank.parser import parse_bank_pdf

        with tempfile.TemporaryDirectory() as tmp:
            path = _page_png(Path(tmp) / "Axis_statement_Jul2026.png")
            with stubbed_ocr() as calls:
                classification = classify_path(path)
                parsed = parse_bank_pdf(path)

        self.assertEqual(classification.kind, "bank", classification.reason)
        self.assertEqual(len(calls), 1, "classifier and parser both OCR'd the image")
        self.assertEqual(parsed["input_type"], "image")


if __name__ == "__main__":
    unittest.main()
