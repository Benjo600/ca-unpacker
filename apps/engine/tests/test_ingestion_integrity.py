from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from make_test_dump import pdf_with_text


class SniffFileKindTests(unittest.TestCase):
    def test_pdf_bytes_are_detected_even_when_renamed(self) -> None:
        from apps.engine.classifier import sniff_file_kind

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invoice.jpg"
            path.write_bytes(pdf_with_text(["Tax Invoice", "GSTIN 27AAPFU0939F1ZV"]))
            self.assertEqual(sniff_file_kind(path), "pdf")

    def test_image_bytes_are_detected(self) -> None:
        from apps.engine.classifier import sniff_file_kind

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
            self.assertEqual(sniff_file_kind(path), "image")

    def test_text_content_is_detected(self) -> None:
        from apps.engine.classifier import sniff_file_kind

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.bin"
            path.write_bytes(b"Voucher Number,Amount\nPUR-88,125000.50")
            self.assertEqual(sniff_file_kind(path), "text")


class ExtensionMismatchTests(unittest.TestCase):
    """A .pdf name must not make a JPEG image be parsed as a PDF (Phase 2)."""

    def test_jpeg_renamed_to_pdf_classifies_as_image(self) -> None:
        from apps.engine.classifier import classify_path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "statement.pdf"
            path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
            result = classify_path(path)
            self.assertEqual(result.kind, "unknown")
            self.assertIn("content is image", result.reason)
            self.assertIn(".pdf", result.reason)

    def test_zip_renamed_to_pdf_is_not_parsed_as_pdf(self) -> None:
        from apps.engine.classifier import classify_path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tally.xml"
            path.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
            result = classify_path(path)
            self.assertEqual(result.kind, "unknown")
            self.assertIn("zip archive content", result.reason)

    def test_pdf_renamed_to_jpg_still_classified_by_content(self) -> None:
        from apps.engine.classifier import classify_path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.jpg"
            path.write_bytes(
                pdf_with_text(
                    [
                        "HDFC Bank Statement",
                        "Account Number 50100123456789",
                        "IFSC HDFC0001234",
                        "Withdrawal 100.00",
                        "Deposit 200.00",
                        "Closing Balance 1,100.00",
                    ]
                )
            )
            result = classify_path(path)
            self.assertEqual(result.kind, "bank")
            self.assertIn("content is pdf", result.reason)


class CopyVerificationTests(unittest.TestCase):
    def test_copy_verified_computes_sha256_and_size(self) -> None:
        from apps.engine.dump import copy_verified

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.pdf"
            payload = pdf_with_text(["Opening Balance 1,000.00"])
            source.write_bytes(payload)
            dest = root / "dest.pdf"
            sha256, error = copy_verified(source, dest)
            self.assertIsNone(error)
            self.assertIsNotNone(sha256)
            assert sha256 is not None
            self.assertEqual(len(sha256), 64)
            self.assertEqual(dest.stat().st_size, len(payload))
            import hashlib

            self.assertEqual(hashlib.sha256(payload).hexdigest(), sha256)

    def test_copy_verified_detects_shrinking_source(self) -> None:
        """A source that changes size mid-copy must not produce a partial copy."""
        import threading
        import time as time_module
        from apps.engine.dump import copy_verified

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "growing.pdf"
            source.write_bytes(b"%PDF-1.4" + b"a" * 4096)
            dest = root / "dest.pdf"

            stop = threading.Event()

            def grow():
                time_module.sleep(0.01)
                with open(source, "ab") as handle:
                    handle.write(b"b" * 4096)
                    handle.flush()
                stop.set()

            worker = threading.Thread(target=grow)
            worker.start()
            sha256, error = copy_verified(source, dest)
            worker.join()
            if error is None:
                # No race hit this run — the verification still passed.
                self.assertIsNotNone(sha256)
            else:
                self.assertFalse(dest.exists())

    def test_copy_verified_removes_partial_output(self) -> None:
        from apps.engine.dump import copy_verified

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "dest.pdf"
            # A directory as source forces an OSError mid-copy.
            sha256, error = copy_verified(root, dest)
            self.assertIsNone(sha256)
            self.assertIsNotNone(error)
            self.assertFalse(dest.exists())


class DuplicateContentTests(unittest.TestCase):
    def _period(self):
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        client = create_client("Acme")
        return create_period(client["id"], "Jul 2026")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(
            os.environ, {"LOCALAPPDATA": self._tmp.name}
        )
        self._env.start()
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._env.stop()
        self._tmp.cleanup()

    def test_identical_file_ingested_twice_is_flagged_not_dropped(self) -> None:
        from apps.engine.dump import ingest_paths, list_period_files, start_job

        period = self._period()
        payload = pdf_with_text(
            [
                "HDFC Bank Statement",
                "Account Number 50100123456789",
                "IFSC HDFC0001234",
                "Opening Balance 1,000.00",
                "01/07/2026 UPI 100.00 1,100.00",
                "Closing Balance 1,100.00",
            ]
        )
        inbox = Path(self._tmp.name)
        first = inbox / "statement_a.pdf"
        second = inbox / "statement_b.pdf"
        first.write_bytes(payload)
        second.write_bytes(payload)

        job = start_job(period["id"])
        ingest_paths(job["id"], [str(first), str(second)])

        files = list_period_files(period["id"])
        by_name = {row["original_name"]: row for row in files}
        self.assertIn("statement_a.pdf", by_name)
        self.assertIn("statement_b.pdf", by_name)
        duplicate = by_name["statement_b.pdf"]
        original = by_name["statement_a.pdf"]
        # Both copies are ingested, hashed and processed — nothing is dropped.
        self.assertEqual(duplicate["content_sha256"], original["content_sha256"])
        self.assertIsNotNone(duplicate["content_sha256"])
        self.assertIn("duplicate content of statement_a.pdf", duplicate["classify_reason"])
        self.assertTrue(duplicate["duplicate_content"])
        # Both files still produce parsed rows for review.
        self.assertEqual(original["parse_row_count"], 1)

    def test_different_content_is_not_flagged(self) -> None:
        from apps.engine.dump import ingest_paths, list_period_files, start_job

        period = self._period()
        first = Path(self._tmp.name) / "one.pdf"
        second = Path(self._tmp.name) / "two.pdf"
        first.write_bytes(pdf_with_text(["HDFC Bank Statement", "Opening Balance 1,000.00"]))
        second.write_bytes(pdf_with_text(["Kotak Bank Statement", "Opening Balance 2,000.00"]))
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(first), str(second)])
        files = {row["original_name"]: row for row in list_period_files(period["id"])}
        self.assertFalse(files["one.pdf"]["duplicate_content"])
        self.assertFalse(files["two.pdf"]["duplicate_content"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
