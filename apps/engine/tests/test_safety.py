from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine import safety


def write_pack(folder: Path, marker: str = "v1") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pack_summary.json").write_text(f'{{"marker": "{marker}"}}', encoding="utf-8")
    (folder / "Bank_Statement_Cleaned.xlsx").write_bytes(b"xlsx-" + marker.encode("utf-8"))
    nested = folder / "sources"
    nested.mkdir(exist_ok=True)
    (nested / "notes.txt").write_text(f"notes {marker}", encoding="utf-8")
    return folder


def bytes_of(folder: Path) -> dict[str, bytes]:
    return {
        item.relative_to(folder).as_posix(): item.read_bytes()
        for item in sorted(Path(folder).rglob("*"))
        if item.is_file()
    }


class SafetyCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LOCALAPPDATA"] = self._tmp.name
        from apps.engine.db import reset_engine

        reset_engine()
        self.root = Path(self._tmp.name)
        self.library = self.root / "CAUnpacker"
        self.packs = self.library / "packs"
        self.packs.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._tmp.cleanup()


class SnapshotTests(SafetyCase):
    def test_snapshot_copies_the_folder_and_records_what_when_why(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026")
        original = bytes_of(pack)
        when = datetime(2026, 7, 31, 18, 15, tzinfo=timezone.utc)

        manifest = safety.snapshot(pack, reason="before-rewrite", now=when)

        self.assertIsNotNone(manifest)
        folder = safety.snapshots_root() / manifest["id"]
        self.assertTrue(folder.is_dir())
        self.assertEqual(bytes_of(folder / "content"), original)
        self.assertEqual(manifest["kind"], "snapshot")
        self.assertEqual(manifest["reason"], "before-rewrite")
        self.assertEqual(manifest["source"], str(pack))
        self.assertEqual(manifest["created_at"], when.isoformat())
        self.assertEqual(manifest["file_count"], 3)
        self.assertIn("pack_summary.json", manifest["files"])
        self.assertGreater(manifest["byte_count"], 0)
        # The manifest is on disk, not just in memory.
        stored = safety.list_snapshots(target=pack)
        self.assertEqual([item["id"] for item in stored], [manifest["id"]])
        self.assertEqual(bytes_of(pack), original)

    def test_snapshots_live_under_the_library_and_never_in_the_period_folder(self) -> None:
        pack = write_pack(self.library / "packs" / "Acme" / "Jul 2026")
        manifest = safety.snapshot(pack)
        folder = safety.snapshots_root() / manifest["id"]
        self.assertTrue(str(folder).startswith(str(self.library)))
        self.assertNotIn(str(pack), str(folder))
        self.assertFalse(any(item.name == "manifest.json" for item in pack.rglob("*")))

    def test_nothing_to_snapshot_returns_none(self) -> None:
        missing = self.packs / "Acme" / "Jul 2026"
        self.assertIsNone(safety.snapshot(missing))
        empty = self.packs / "Acme" / "Aug 2026"
        empty.mkdir(parents=True)
        self.assertIsNone(safety.snapshot(empty))

    def test_refuses_to_copy_the_safety_area_into_itself(self) -> None:
        write_pack(self.packs / "Acme" / "Jul 2026")
        safety.snapshot(self.packs / "Acme" / "Jul 2026")
        with self.assertRaises(ValueError):
            safety.snapshot(safety.snapshots_root())

    def test_purge_removes_only_expired_snapshots_and_is_repeatable(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026")
        now = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
        old = safety.snapshot(pack, reason="old", now=now - timedelta(days=45), purge_first=False)
        recent = safety.snapshot(pack, reason="recent", now=now - timedelta(days=3), purge_first=False)
        today = safety.snapshot(pack, reason="today", now=now, purge_first=False)

        removed = safety.purge(30, now=now)

        self.assertEqual(removed, [old["id"]])
        remaining = [item["id"] for item in safety.list_snapshots()]
        self.assertIn(recent["id"], remaining)
        self.assertIn(today["id"], remaining)
        self.assertFalse((safety.snapshots_root() / old["id"]).exists())
        self.assertEqual(safety.purge(30, now=now), [])

    def test_purge_uses_the_saved_retention_setting(self) -> None:
        from apps.engine.settings import (
            get_snapshot_retention_days,
            set_snapshot_retention_days,
        )

        self.assertEqual(get_snapshot_retention_days(), 30)
        self.assertEqual(set_snapshot_retention_days(7), 7)
        self.assertEqual(get_snapshot_retention_days(), 7)
        with self.assertRaises(ValueError):
            set_snapshot_retention_days(0)

        pack = write_pack(self.packs / "Acme" / "Jul 2026")
        now = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)
        stale = safety.snapshot(pack, now=now - timedelta(days=10), purge_first=False)
        fresh = safety.snapshot(pack, now=now - timedelta(days=2), purge_first=False)

        self.assertEqual(safety.purge(now=now), [stale["id"]])
        self.assertTrue((safety.snapshots_root() / fresh["id"]).exists())


class TrashTests(SafetyCase):
    def test_trash_moves_the_folder_and_restore_brings_it_back(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026")
        original = bytes_of(pack)

        entry = safety.trash(pack, reason="test")

        self.assertFalse(pack.exists())
        self.assertTrue((safety.trash_root() / entry["id"] / "content").is_dir())
        self.assertEqual(entry["source"], str(pack))
        self.assertEqual(entry["file_count"], 3)
        self.assertEqual([item["id"] for item in safety.list_trash()], [entry["id"]])

        restored = safety.restore_from_trash(entry["id"])

        self.assertEqual(restored["path"], str(pack))
        self.assertEqual(bytes_of(pack), original)
        with self.assertRaises(ValueError):
            safety.restore_from_trash(entry["id"])

    def test_restore_from_trash_never_overwrites_a_folder_that_came_back(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026")
        entry = safety.trash(pack)
        write_pack(pack, "newer")

        with self.assertRaises(ValueError):
            safety.restore_from_trash(entry["id"])

        self.assertEqual(bytes_of(pack)["pack_summary.json"], b'{"marker": "newer"}')

    def test_trash_refuses_the_safety_area(self) -> None:
        write_pack(self.packs / "Acme" / "Jul 2026")
        safety.snapshot(self.packs / "Acme" / "Jul 2026")
        with self.assertRaises(ValueError):
            safety.trash(safety.snapshots_root())


class RestoreRollbackTests(SafetyCase):
    def test_failed_restore_puts_the_original_back_byte_for_byte(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026", "wanted")
        good = safety.snapshot(pack, reason="wanted-version")
        write_pack(pack, "live")
        original = bytes_of(pack)

        real_swap = safety._swap_in
        calls = {"n": 0}

        def flaky_swap(content: Path, target: Path) -> None:
            calls["n"] += 1
            real_swap(content, target)
            if calls["n"] == 1:
                raise OSError("disk full half way through")

        with patch("apps.engine.safety._swap_in", side_effect=flaky_swap):
            with self.assertRaises(ValueError) as ctx:
                safety.restore_snapshot(good["id"], pack)

        self.assertIn("put back the way it was", str(ctx.exception))
        self.assertEqual(calls["n"], 2)
        self.assertEqual(bytes_of(pack), original)
        self.assertNotEqual(bytes_of(pack)["pack_summary.json"], b'{"marker": "wanted"}')
        # The pre-restore copy is kept so nothing was lost.
        versions = safety.list_snapshots(target=pack)
        self.assertTrue(any(item["reason"].startswith("before-restore:") for item in versions))

    def test_failed_restore_into_a_fresh_folder_leaves_nothing_half_written(self) -> None:
        source = write_pack(self.packs / "Acme" / "Jul 2026", "wanted")
        good = safety.snapshot(source)
        fresh = self.packs / "Acme" / "Aug 2026"
        original = bytes_of(source)

        real_swap = safety._swap_in

        def flaky_swap(content: Path, target: Path) -> None:
            real_swap(content, target)
            raise OSError("disk full half way through")

        with patch("apps.engine.safety._swap_in", side_effect=flaky_swap):
            with self.assertRaises(ValueError):
                safety.restore_snapshot(good["id"], fresh)

        self.assertFalse(fresh.exists())
        self.assertEqual(bytes_of(source), original)

    def test_restore_keeps_the_current_pack_as_a_version(self) -> None:
        pack = write_pack(self.packs / "Acme" / "Jul 2026", "first")
        first = safety.snapshot(pack, reason="first-run")
        write_pack(pack, "second")
        second = bytes_of(pack)

        result = safety.restore_snapshot(first["id"], pack)

        self.assertEqual(result["path"], str(pack))
        self.assertIsNotNone(result["pre_restore_snapshot_id"])
        self.assertEqual(bytes_of(pack)["pack_summary.json"], b'{"marker": "first"}')
        kept = safety.snapshots_root() / result["pre_restore_snapshot_id"] / "content"
        self.assertEqual(bytes_of(kept), second)


class DailyGuardTests(SafetyCase):
    def test_full_packs_root_snapshot_happens_once_a_day(self) -> None:
        write_pack(self.packs / "Acme" / "Jul 2026")
        morning = datetime(2026, 7, 31, 9, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)
        tomorrow = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)

        first = safety.ensure_daily_snapshot(now=morning)
        self.assertIsNotNone(first)
        self.assertEqual(first["reason"], safety.DAILY_REASON)
        self.assertEqual(first["source"], str(self.packs))
        self.assertIsNone(safety.ensure_daily_snapshot(now=evening))
        self.assertTrue(safety.daily_snapshot_done(now=evening))

        next_day = safety.ensure_daily_snapshot(now=tomorrow)
        self.assertIsNotNone(next_day)
        self.assertNotEqual(next_day["id"], first["id"])
        dailies = [
            item
            for item in safety.list_snapshots()
            if item["reason"] == safety.DAILY_REASON
        ]
        self.assertEqual(len(dailies), 2)


class PipelineUndoTests(SafetyCase):
    def _ready_period(self) -> dict:
        from apps.engine.clients import create_client
        from apps.engine.dump import ingest_paths, start_job
        from apps.engine.firm import save_firm
        from apps.engine.periods import create_period
        from apps.engine.tests.test_stage3_bank import write_hdfc

        save_firm("Test firm")
        client = create_client("Acme")
        period = create_period(client["id"], "Jul 2026")
        inbox = self.root / "inbox"
        inbox.mkdir(exist_ok=True)
        job = start_job(period["id"])
        ingest_paths(job["id"], [str(write_hdfc(inbox))])
        return period

    def test_mid_run_failure_leaves_the_previous_pack_intact(self) -> None:
        from apps.engine.pipeline import list_pack_versions, parse_period

        period = self._ready_period()
        # Ingest already packs once; this run leaves the first pack recoverable.
        first = parse_period(period["id"])
        self.assertIsNotNone(first)
        dest = Path(first["path"])
        before = bytes_of(dest)
        self.assertIn("Bank_Statement_Cleaned.xlsx", before)
        versions_before = list_pack_versions(period["id"])
        self.assertEqual(len(versions_before), 1)
        self.assertEqual(versions_before[0]["reason"], "before-rewrite")

        def half_written(dest_path, *_args, **_kwargs):
            Path(dest_path).write_bytes(b"truncated")
            raise RuntimeError("disk full")

        with patch("apps.engine.pipeline.write_bank_workbook", side_effect=half_written):
            with self.assertRaises(RuntimeError) as ctx:
                parse_period(period["id"])

        self.assertIn("put back unchanged", str(ctx.exception))
        self.assertEqual(bytes_of(dest), before)
        versions = list_pack_versions(period["id"])
        self.assertEqual(len(versions), len(versions_before) + 1)
        self.assertEqual(versions[0]["reason"], "before-rewrite")

    def test_successful_rerun_keeps_the_earlier_version_recoverable(self) -> None:
        from apps.engine.pipeline import (
            list_pack_versions,
            parse_period,
            restore_pack_version,
        )

        period = self._ready_period()
        first = parse_period(period["id"])
        dest = Path(first["path"])
        first_bytes = bytes_of(dest)
        versions_before = list_pack_versions(period["id"])
        self.assertEqual(len(versions_before), 1)

        second = parse_period(period["id"])
        self.assertIsNotNone(second)
        versions = list_pack_versions(period["id"])
        self.assertEqual(len(versions), len(versions_before) + 1)
        # One live pack only: the earlier copy sits in the snapshot area, never
        # next to the current Excels.
        self.assertEqual(sorted(bytes_of(dest)), sorted(first_bytes))
        archived = safety.snapshots_root() / versions[0]["id"] / "content"
        self.assertEqual(bytes_of(archived), first_bytes)

        restore_pack_version(period["id"], versions[0]["id"])

        self.assertEqual(bytes_of(dest), first_bytes)


if __name__ == "__main__":
    unittest.main()
