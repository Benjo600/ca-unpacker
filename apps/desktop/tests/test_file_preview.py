from __future__ import annotations

import json
from pathlib import Path
import unittest

from apps.desktop.app import DesktopApi
from apps.engine.preview import get_preview_for_path, list_folder_preview_files


class TestFilePreview(unittest.TestCase):
    def setUp(self) -> None:
        self.api = DesktopApi()
        self.repo_root = Path(__file__).resolve().parents[3]
        self.test_dump_dir = self.repo_root / "test-dump"

    def test_preview_pdf_file(self) -> None:
        pdf_path = self.test_dump_dir / "01-banks-digital" / "HDFC_Statement_Jul2026.pdf"
        if not pdf_path.exists():
            self.skipTest("HDFC sample PDF not found")

        result = self.api.get_file_preview(file_path=str(pdf_path), page=1)
        self.assertTrue(result.get("ok"), f"Preview failed: {result.get('error')}")
        self.assertEqual(result.get("type"), "pdf")
        self.assertEqual(result.get("page"), 1)
        self.assertGreaterEqual(result.get("total_pages", 0), 1)
        self.assertTrue(result.get("image_data", "").startswith("data:image/png;base64,"))
        self.assertEqual(result.get("filename"), "HDFC_Statement_Jul2026.pdf")

    def test_preview_text_and_markdown(self) -> None:
        readme_path = self.test_dump_dir / "README.md"
        if not readme_path.exists():
            self.skipTest("README.md not found in test-dump")

        result = self.api.get_file_preview(file_path=str(readme_path))
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("type"), "text")
        self.assertIn("content", result)
        self.assertGreater(result.get("line_count", 0), 0)

    def test_preview_csv(self, tmp_path_factory=None) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_statement.csv"
            csv_path.write_text(
                "Date,Description,Debit,Credit,Balance\n2026-07-01,Opening Balance,,,10000.00\n2026-07-02,Office Supplies,450.00,,9550.00",
                encoding="utf-8",
            )
            result = self.api.get_file_preview(file_path=str(csv_path))
            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("type"), "spreadsheet")
            self.assertEqual(result.get("columns"), ["Date", "Description", "Debit", "Credit", "Balance"])
            self.assertEqual(len(result.get("rows", [])), 2)

    def test_preview_json(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sample_gstr.json"
            sample_data = {
                "gstin": "27AAAAA0000A1Z5",
                "fp": "072026",
                "b2b": [{"inv": [{"inum": "INV-101", "val": 15000}]}],
            }
            json_path.write_text(json.dumps(sample_data), encoding="utf-8")

            result = self.api.get_file_preview(file_path=str(json_path))
            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("type"), "json")
            self.assertIn("27AAAAA0000A1Z5", result.get("content", ""))
            self.assertEqual(result.get("meta", {}).get("key_count"), 3)

    def test_preview_image(self) -> None:
        import tempfile
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = Path(tmpdir) / "receipt.png"
            img = Image.new("RGB", (120, 80), color=(50, 100, 150))
            img.save(img_path)

            result = self.api.get_file_preview(file_path=str(img_path))
            self.assertTrue(result.get("ok"))
            self.assertEqual(result.get("type"), "image")
            self.assertEqual(result.get("width"), 120)
            self.assertEqual(result.get("height"), 80)
            self.assertTrue(result.get("image_data", "").startswith("data:image/png;base64,"))

    def test_preview_missing_file(self) -> None:
        result = self.api.get_file_preview(file_path="C:/nonexistent/file.pdf")
        self.assertFalse(result.get("ok"))
        self.assertIn("File not found", result.get("error", ""))

    def test_list_folder_files(self) -> None:
        folder = self.test_dump_dir / "01-banks-digital"
        if not folder.exists():
            self.skipTest("01-banks-digital not found")

        result = self.api.list_folder_files(str(folder))
        self.assertTrue(result.get("ok"))
        self.assertGreaterEqual(result.get("total_files", 0), 1)
        files = result.get("files", [])
        names = [f["name"] for f in files]
        self.assertIn("HDFC_Statement_Jul2026.pdf", names)

    def test_preview_by_stored_file_id(self) -> None:
        import os
        import tempfile
        from apps.engine.db import reset_engine
        from apps.engine.clients import create_client
        from apps.engine.periods import create_period
        from apps.engine.dump import ingest_paths, list_period_files, start_job

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_local = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = tmpdir
            try:
                reset_engine()
                client = create_client("Preview Corp")
                period = create_period(client["id"], "Aug 2026")
                sample_pdf = self.test_dump_dir / "01-banks-digital" / "HDFC_Statement_Jul2026.pdf"
                if not sample_pdf.exists():
                    return
                job = start_job(period["id"])
                ingest_paths(job["id"], [str(sample_pdf)])
                files = list_period_files(period["id"])
                self.assertGreater(len(files), 0)
                stored_id = files[0]["id"]
                preview = self.api.get_file_preview(file_id=stored_id)
                self.assertTrue(preview.get("ok"))
                self.assertEqual(preview.get("type"), "pdf")
                self.assertEqual(preview.get("file_id"), stored_id)
            finally:
                reset_engine()
                if orig_local:
                    os.environ["LOCALAPPDATA"] = orig_local
                else:
                    os.environ.pop("LOCALAPPDATA", None)


if __name__ == "__main__":
    unittest.main()

