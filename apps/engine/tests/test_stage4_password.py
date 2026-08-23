from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.test_stage3_bank import write_hdfc

SECRET = "stage4-secret-passphrase-never-on-disk"


def _localapp_contains(needle: str) -> bool:
    root = Path(os.environ.get("LOCALAPPDATA") or "")
    if not root.exists():
        return False
    blob = needle.encode("utf-8")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if blob in data:
            return True
    return False


class PasswordMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        reset_engine()
        clear_all_passwords()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        clear_all_passwords()
        reset_engine()
        self._tmp.cleanup()

    def test_set_get_clear_password_stays_off_disk(self) -> None:
        from apps.engine.library import init_library
        from apps.engine.pdf_passwords import (
            clear_file_password,
            get_file_password,
            set_file_password,
        )

        init_library()
        set_file_password(42, SECRET)
        self.assertEqual(get_file_password(42), SECRET)
        self.assertFalse(_localapp_contains(SECRET))
        clear_file_password(42)
        self.assertIsNone(get_file_password(42))
        self.assertFalse(_localapp_contains(SECRET))


class FileDictPasswordTests(unittest.TestCase):
    def test_needs_password_from_classify_reason(self) -> None:
        from apps.engine.dump import _file_dict

        row = SimpleNamespace(
            id=1,
            job_id=1,
            period_id=1,
            original_name="locked.pdf",
            size=12,
            storage_key="1/1/locked.pdf",
            detected_kind="unknown",
            override_kind=None,
            confidence=0.5,
            classify_reason="password-protected PDF",
        )
        payload = _file_dict(row)
        self.assertTrue(payload["needs_password"])
        self.assertEqual(payload["kind"], "unknown")

        row.classify_reason = "bank statement text"
        self.assertFalse(_file_dict(row)["needs_password"])


class PreviewAndCropTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        reset_engine()
        clear_all_passwords()
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Test firm")
        self.client = create_client("Acme")
        self.period = create_period(self.client["id"], "Jul 2026")

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        clear_all_passwords()
        reset_engine()
        self._tmp.cleanup()

    def _ingest_hdfc(self) -> Path:
        from apps.engine.dump import ingest_paths, start_job

        inbox = Path(self._tmp.name) / "inbox"
        inbox.mkdir(exist_ok=True)
        pdf = write_hdfc(inbox)
        job = start_job(self.period["id"])
        ingest_paths(job["id"], [str(pdf)])
        return pdf

    def test_preview_rows_include_row_id(self) -> None:
        from apps.engine.pipeline import get_period_preview

        self._ingest_hdfc()
        preview = get_period_preview(self.period["id"], 10)
        files = preview.get("files") or []
        self.assertTrue(files)
        rows = files[0].get("preview") or []
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("row_id", row)
            self.assertIsInstance(row["row_id"], int)
            self.assertIn("source_page", row)
            self.assertIn("source_bbox", row)

    def test_source_crop_from_dumped_hdfc(self) -> None:
        try:
            from apps.engine import pdf_render
        except Exception:
            self.skipTest("pdf_render missing")
        if not hasattr(pdf_render, "crop_png_bytes") and not hasattr(pdf_render, "crop_png"):
            self.skipTest("pdf_render missing")

        from apps.engine.dump import list_period_files
        from apps.engine.parsers.bank.parser import parse_bank_pdf
        from apps.engine.pipeline import get_source_crop

        pdf = self._ingest_hdfc()
        parsed = parse_bank_pdf(pdf)
        boxed = next((row for row in parsed["rows"] if row.get("source_bbox")), None)
        if boxed is None:
            self.skipTest("no bbox from parse_bank_pdf")
        stored = next(row for row in list_period_files(self.period["id"]) if row["kind"] == "bank")
        crop = get_source_crop(stored["id"], int(boxed["source_page"] or 1), boxed["source_bbox"])
        self.assertTrue(crop.get("ok"), crop)
        path = crop.get("path")
        data_url = crop.get("data_url")
        self.assertTrue(path or data_url, crop)
        if path:
            self.assertTrue(str(path).lower().endswith(".png"), path)
            self.assertTrue(Path(path).is_file(), path)
            self.assertGreater(Path(path).stat().st_size, 8)
        if data_url:
            self.assertTrue(str(data_url).startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
