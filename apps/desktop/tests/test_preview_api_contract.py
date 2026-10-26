from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path


class DesktopPreviewApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        reset_engine()
        clear_all_passwords()

        from apps.engine.clients import create_client
        from apps.engine.dump import start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Preview contract firm")
        self.period = create_period(create_client("Acme")["id"], "Jul 2026")
        self.job = start_job(self.period["id"])
        self.inbox = Path(self._tmp.name) / "inbox"
        self.inbox.mkdir()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine
        from apps.engine.pdf_passwords import clear_all_passwords

        clear_all_passwords()
        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def _store(self, source: Path) -> int:
        from apps.engine.db import StoredFile, get_session
        from apps.engine.library import files_root

        key = f"{self.period['id']}/{self.job['id']}/{uuid.uuid4().hex[:8]}_{source.name}"
        dest = files_root() / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        session = get_session()
        try:
            row = StoredFile(
                job_id=self.job["id"],
                period_id=self.period["id"],
                original_name=source.name,
                size=source.stat().st_size,
                storage_key=key,
                detected_kind="bank",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
        finally:
            session.close()

    def test_preview_api_returns_a_page_url(self) -> None:
        from apps.desktop.app import DesktopApi
        from make_test_dump import pdf_with_text

        source = self.inbox / "HDFC_Statement.pdf"
        source.write_bytes(pdf_with_text(["HDFC Bank Account Statement", "Closing Balance 147500.00"]))
        file_id = self._store(source)

        result = DesktopApi().get_file_preview(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "pdf")
        self.assertEqual(result["page_count"], 1)
        self.assertTrue(result["image"]["data_url"].startswith("data:image/"))

    def test_preview_api_accepts_empty_optional_arguments(self) -> None:
        from apps.desktop.app import DesktopApi
        from make_test_dump import pdf_with_text

        source = self.inbox / "GSTR.json"
        source.write_text('{"gstin":"27AAPFU0939F1ZV"}', encoding="utf-8")
        file_id = self._store(source)

        result = DesktopApi().get_file_preview(file_id, 1, "", "", True)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "text")

    def test_preview_api_reports_unknown_file(self) -> None:
        from apps.desktop.app import DesktopApi

        result = DesktopApi().get_file_preview(424242)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "missing")

    def test_open_source_file_does_not_launch_a_missing_file(self) -> None:
        from apps.desktop.app import DesktopApi

        result = DesktopApi().open_source_file(424242)
        self.assertFalse(result["ok"])
        self.assertIn("missing", result["error"].lower())
