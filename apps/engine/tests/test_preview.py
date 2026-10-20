from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path


class PreviewTests(unittest.TestCase):
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

        save_firm("Preview firm")
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

    # helpers -------------------------------------------------------------

    def _store(self, source: Path, kind: str = "unknown") -> int:
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
                detected_kind=kind,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
        finally:
            session.close()

    def _write(self, name: str, data: bytes) -> Path:
        path = self.inbox / name
        path.write_bytes(data)
        return path

    def _pdf(self, name: str = "statement.pdf", pages: int = 1) -> Path:
        from make_test_dump import pdf_with_text
        from pypdf import PdfReader, PdfWriter

        lines = ["HDFC Bank Account Statement", "Opening Balance 150000.00"]
        first = self._write(name, pdf_with_text(lines))
        if pages == 1:
            return first
        reader = PdfReader(str(first))
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_page(reader.pages[0])
        with first.open("wb") as handle:
            writer.write(handle)
        return first

    # PDF -----------------------------------------------------------------

    def test_pdf_preview_returns_page_image_and_count(self) -> None:
        from apps.engine.preview import preview_file

        file_id = self._store(self._pdf(pages=2), "bank")
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "pdf")
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["kind_label"], "Bank statement")
        self.assertTrue(result["image"]["data_url"].startswith("data:image/"))
        self.assertGreater(result["image"]["width"], 0)
        self.assertGreater(result["image"]["height"], 0)

    def test_pdf_second_page_and_out_of_range(self) -> None:
        from apps.engine.preview import preview_file

        file_id = self._store(self._pdf(name="two.pdf", pages=2))
        second = preview_file(file_id, page=2)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["page"], 2)

        missing = preview_file(file_id, page=7)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["reason"], "range")

    def test_password_pdf_is_prompted_not_stored(self) -> None:
        from apps.engine.pdf_passwords import get_file_password
        from apps.engine.preview import preview_file
        from apps.engine.tests.fixtures_stage4 import make_password_pdf

        plain = self._pdf(name="lockme.pdf")
        locked = make_password_pdf(plain, self.inbox / "locked.pdf", "hunter2")
        file_id = self._store(locked, "bank")

        blocked = preview_file(file_id)
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["reason"], "password_required")

        wrong = preview_file(file_id, password="nope")
        self.assertFalse(wrong["ok"])
        self.assertEqual(wrong["reason"], "password_required")
        self.assertNotIn("hunter2", wrong["error"])

        opened = preview_file(file_id, password="hunter2")
        self.assertTrue(opened["ok"], opened)
        self.assertIsNone(get_file_password(file_id))

    # images / text -------------------------------------------------------

    def test_image_preview(self) -> None:
        from PIL import Image

        from apps.engine.preview import preview_file

        source = self.inbox / "invoice.png"
        Image.new("RGB", (900, 1200), (250, 250, 245)).save(source)
        file_id = self._store(source, "invoice")
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "image")
        self.assertEqual(result["page_count"], 1)
        self.assertTrue(result["image"]["data_url"].startswith("data:image/jpeg;base64,"))

    def test_json_preview_formats_and_flags_invalid_json(self) -> None:
        from apps.engine.preview import preview_file

        good = self._store(self._write("GSTR2B.json", b'{"gstin":"27AAPFU0939F1ZV","b2b":[]}'))
        formatted = preview_file(good)
        self.assertTrue(formatted["ok"], formatted)
        self.assertEqual(formatted["preview_type"], "text")
        self.assertTrue(formatted["valid_json"])
        self.assertIn("\n  ", formatted["text"])

        raw = preview_file(good, formatted=False)
        self.assertEqual(raw["text"], '{"gstin":"27AAPFU0939F1ZV","b2b":[]}')

        broken = self._store(self._write("GSTR-2B_broken.json", b"{"))
        invalid = preview_file(broken)
        self.assertTrue(invalid["ok"], invalid)
        self.assertFalse(invalid["valid_json"])
        self.assertEqual(invalid["text"], "{")
        self.assertIn("not valid JSON", invalid["note"])

    def test_text_preview_truncates(self) -> None:
        from apps.engine.preview import TEXT_LIMIT, preview_file

        blob = ("A" * 1000 + "\n").encode("utf-8") * 260
        file_id = self._store(self._write("notes.txt", blob))
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "text")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), TEXT_LIMIT)

    def test_csv_preview_is_a_table_with_sniffed_delimiter(self) -> None:
        from apps.engine.preview import preview_file

        csv_text = "Invoice Number;Party;Total\nINV-1;Acme;11800\nINV-2;Beta;5900\n"
        file_id = self._store(self._write("Zoho_Books.csv", csv_text.encode("utf-8")))
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "table")
        table = result["table"]
        self.assertEqual(table["delimiter"], ";")
        self.assertEqual(table["rows"][0], ["Invoice Number", "Party", "Total"])
        self.assertEqual(table["rows"][2], ["INV-2", "Beta", "5900"])
        self.assertFalse(table["truncated"])

    def test_xlsx_preview_lists_sheets_and_switches(self) -> None:
        from openpyxl import Workbook

        from apps.engine.preview import preview_file

        path = self.inbox / "books.xlsx"
        workbook = Workbook()
        first = workbook.active
        first.title = "Purchase"
        first.append(["Supplier", "Amount"])
        first.append(["Acme Traders", 11800])
        second = workbook.create_sheet("Sales")
        second.append(["Party", "Amount"])
        second.append(["Beta", 5900])
        workbook.save(path)
        file_id = self._store(path, "zoho")

        result = preview_file(file_id)
        self.assertEqual(result["preview_type"], "table")
        self.assertEqual(result["table"]["sheets"], ["Purchase", "Sales"])
        self.assertEqual(result["table"]["sheet"], "Purchase")
        self.assertEqual(result["table"]["rows"][1], ["Acme Traders", "11800"])

        sales = preview_file(file_id, sheet="Sales")
        self.assertEqual(sales["table"]["sheet"], "Sales")
        self.assertEqual(sales["table"]["rows"][1], ["Beta", "5900"])

    def test_zip_preview_lists_entries_without_extracting(self) -> None:
        from apps.engine.preview import preview_file

        path = self.inbox / "Tally_Backup.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("DAYBOOK.xml", "<ENVELOPE/>")
            archive.writestr("Masters/ledgers.xml", "<ENVELOPE/>")
        file_id = self._store(path, "tally")
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "archive")
        names = [entry["name"] for entry in result["archive"]["entries"]]
        self.assertEqual(names, ["DAYBOOK.xml", "Masters/ledgers.xml"])

    def test_unsupported_type_explains_itself(self) -> None:
        from apps.engine.preview import preview_file

        file_id = self._store(self._write("meeting_notes.docx", b"PK notes"))
        result = preview_file(file_id)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preview_type"], "unsupported")
        self.assertTrue(result["can_open_external"])
        self.assertIn(".docx", result["note"])

    def test_missing_source_file_and_unknown_id(self) -> None:
        from apps.engine.db import StoredFile, get_session
        from apps.engine.preview import preview_file

        session = get_session()
        try:
            row = StoredFile(
                job_id=self.job["id"],
                period_id=self.period["id"],
                original_name="gone.pdf",
                size=1,
                storage_key="nowhere/gone.pdf",
                detected_kind="bank",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            file_id = row.id
        finally:
            session.close()

        missing = preview_file(file_id)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["reason"], "missing")

        unknown = preview_file(999999)
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["reason"], "missing")


class PreviewCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

        from apps.engine.db import reset_engine

        reset_engine()

        from apps.engine.clients import create_client
        from apps.engine.dump import start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Cache firm")
        self.period = create_period(create_client("Acme")["id"], "Jul 2026")
        self.job = start_job(self.period["id"])

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()
        if self._original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._original_localappdata

    def test_second_preview_reuses_the_rendered_page(self) -> None:
        from make_test_dump import pdf_with_text

        from apps.engine.db import StoredFile, get_session
        from apps.engine.library import files_root
        from apps.engine.preview import preview_file

        source = files_root() / "cachetest.pdf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(pdf_with_text(["HDFC Bank Account Statement"]))
        session = get_session()
        try:
            row = StoredFile(
                job_id=self.job["id"],
                period_id=self.period["id"],
                original_name="cachetest.pdf",
                size=source.stat().st_size,
                storage_key="cachetest.pdf",
                detected_kind="bank",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            file_id = row.id
        finally:
            session.close()

        first = preview_file(file_id)
        self.assertTrue(first["ok"], first)
        cache_files = list((files_root().parent / "cache" / "previews").iterdir())
        self.assertEqual(len(cache_files), 1)
        stamp = cache_files[0].stat().st_mtime_ns

        second = preview_file(file_id)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["image"]["data_url"], first["image"]["data_url"])
        self.assertEqual(cache_files[0].stat().st_mtime_ns, stamp)

    def test_preview_cache_keeps_the_newest_files(self) -> None:
        from apps.engine.preview import _prune_cache

        folder = Path(self._tmp.name) / "prune"
        folder.mkdir()
        for index in range(6):
            item = folder / f"f{index}.png"
            item.write_bytes(b"x")
            os.utime(item, (1000 + index, 1000 + index))

        _prune_cache(folder, keep=3)

        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["f3.png", "f4.png", "f5.png"])


if __name__ == "__main__":
    unittest.main()
