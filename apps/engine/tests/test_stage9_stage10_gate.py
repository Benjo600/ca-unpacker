from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LICENSE_PY = ROOT / "apps" / "engine" / "license.py"
DUMP_PY = ROOT / "apps" / "engine" / "dump.py"
_BANNED_NET = {"requests", "httpx", "urllib", "aiohttp"}


class Stage9LicenseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def _period(self):
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("License firm")
        client = create_client("Acme")
        return create_period(client["id"], "Jul 2026")

    def test_activation_payload_is_product_and_key_hash_only(self) -> None:
        from apps.engine.license import activation_payload

        payload = activation_payload("STARTER-TEST")
        self.assertEqual(set(payload), {"product", "key_sha256"})
        self.assertEqual(payload["product"], "ca-unpacker")
        self.assertEqual(len(payload["key_sha256"]), 64)
        blob = " ".join(payload.values()).lower()
        for banned in ("pdf", "invoice", "gstin", "row", ".json"):
            self.assertNotIn(banned, blob)

    def test_license_and_dump_modules_do_not_post_documents(self) -> None:
        for path in (LICENSE_PY, DUMP_PY):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module.split(".")[0])
            self.assertTrue(names.isdisjoint(_BANNED_NET), path.name)

    def test_starter_blocks_the_101st_file(self) -> None:
        from apps.engine.dump import ingest_paths, list_period_files, start_job
        from apps.engine.license import activate_key, record_ingested

        activate_key("STARTER-TEST")
        record_ingested(100, today=date(2026, 8, 30))
        period = self._period()
        extra = Path(self._tmp.name) / "one-more.txt"
        extra.write_text("x", encoding="utf-8")
        job = start_job(period["id"])
        with self.assertRaisesRegex(ValueError, "100 files"):
            ingest_paths(job["id"], [str(extra)])
        self.assertEqual(list_period_files(period["id"]), [])
        dest = Path(self._tmp.name) / "CAUnpacker" / "files"
        leftovers = [p for p in dest.rglob("*") if p.is_file()] if dest.exists() else []
        self.assertEqual(leftovers, [])

    def test_pro_does_not_block_after_100_files(self) -> None:
        from apps.engine.dump import ingest_paths, list_period_files, start_job
        from apps.engine.license import activate_key, record_ingested

        activate_key("PRO-TEST")
        record_ingested(100, today=date(2026, 8, 30))
        period = self._period()
        extra = Path(self._tmp.name) / "still-ok.txt"
        extra.write_text("x", encoding="utf-8")
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(extra)])
        names = [row["original_name"] for row in list_period_files(period["id"])]
        self.assertEqual(names, ["still-ok.txt"])

    def test_offline_activation_fails_honestly_existing_work_stays(self) -> None:
        from apps.engine.dump import ingest_paths, list_period_files, start_job
        from apps.engine.license import activate_key

        period = self._period()
        sample = Path(self._tmp.name) / "kept.txt"
        sample.write_text("keep", encoding="utf-8")
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(sample)])
        self.assertEqual(len(list_period_files(period["id"])), 1)

        with self.assertRaisesRegex(ValueError, "licence service"):
            activate_key("LIVE-KEY-NOT-TEST", network_available=False)
        self.assertEqual(len(list_period_files(period["id"])), 1)

    def test_suite_is_visible_and_gated(self) -> None:
        from apps.engine.license import activate_key, get_license_status

        status = get_license_status()
        self.assertEqual(status["suite"]["status"], "coming")
        self.assertEqual(status["suite"]["price_inr"], 6000)
        self.assertEqual(status["plans"]["starter"]["price_inr"], 999)
        self.assertEqual(status["plans"]["pro"]["price_inr"], 2500)
        with self.assertRaisesRegex(ValueError, "coming"):
            activate_key("SUITE-TEST")


class Stage10FirmReadyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()

    def test_delete_client_wipes_db_and_disk(self) -> None:
        from apps.engine.clients import create_client, delete_client, list_clients
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.firm import save_firm
        from apps.engine.library import get_library_path
        from apps.engine.periods import create_period

        save_firm("Firm")
        client = create_client("WipeMe")
        period = create_period(client["id"], "Jul 2026")
        sample = Path(self._tmp.name) / "bill.txt"
        sample.write_text("x", encoding="utf-8")
        ingest_paths(start_job(period["id"])["id"], [str(sample)])
        files_dir = get_library_path() / "files" / str(client["id"])
        self.assertTrue(any(files_dir.rglob("*")))

        delete_client(client["id"])
        self.assertEqual(list_clients(), [])
        self.assertFalse(files_dir.exists())

    def test_onedrive_and_desktop_paths_warn(self) -> None:
        from apps.engine.settings import path_sync_warnings

        notes = path_sync_warnings(r"C:\Users\Ada\OneDrive\CAUnpacker")
        self.assertTrue(any("OneDrive" in n for n in notes))
        desk = path_sync_warnings(r"C:\Users\Ada\Desktop\outputs")
        self.assertTrue(any("Desktop" in n for n in desk))
        local = path_sync_warnings(r"C:\Users\Ada\Documents\CAUnpacker")
        self.assertEqual(local, [])

    def test_duplicate_period_is_blocked(self) -> None:
        from apps.engine.clients import create_client
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period

        save_firm("Firm")
        client = create_client("Acme")
        create_period(client["id"], "Jul 2026")
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_period(client["id"], "Jul 2026")

    def test_library_lock_blocks_a_second_writer(self) -> None:
        from apps.engine.library import LOCK_FILENAME, acquire_library_lock, get_library_path, init_library

        init_library()
        acquire_library_lock()
        lock_path = get_library_path() / LOCK_FILENAME
        lock_path.write_text('{"pid": 1}', encoding="utf-8")
        from apps.engine import library as library_mod

        library_mod._lock_held = False
        with patch.object(library_mod, "_pid_alive", return_value=True):
            with self.assertRaisesRegex(ValueError, "one window"):
                acquire_library_lock()

    def test_smartscreen_workaround_is_written(self) -> None:
        path = ROOT / "installer" / "SMARTSCREEN.txt"
        text = path.read_text(encoding="utf-8").lower()
        self.assertTrue(path.is_file())
        self.assertIn("smartscreen", text)
        self.assertIn("more info", text)

    def test_installer_script_and_bank_notes_exist(self) -> None:
        iss = (ROOT / "installer" / "ca-unpacker.iss").read_text(encoding="utf-8")
        self.assertIn("Tesseract", iss)
        notes = (ROOT / "docs" / "ADDING-A-BANK.md").read_text(encoding="utf-8")
        self.assertIn("BankProfile", notes)
        self.assertIn("hints", notes)


if __name__ == "__main__":
    unittest.main()
