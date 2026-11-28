"""Contract test for the generated stress corpus (smoke profile).

Builds the 12-file smoke corpus into a temp folder and checks that the three
artefacts agree with each other and with the bytes on disk:

* ``manifest.json`` — one row per file, expectations known by construction
* ``manifest.csv`` — the same rows in a shape a CA can open in Excel
* ``index.html`` — the gallery

This test never runs the engine. ``corpus_run.py --profile smoke`` does that and
compares the engine's answer with the manifest; see ``docs/STRESS-CORPUS.md``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "build_corpus.py"

EXPECTED_FAMILIES = {
    "banks": 3,
    "books": 2,
    "gst": 2,
    "invoices": 2,
    "junk": 2,
    "mixed": 1,
}

CSV_COLUMNS = {
    "path",
    "family",
    "kind",
    "outcome",
    "rows",
    "line_items",
    "debit",
    "credit",
    "value",
    "taxable",
    "balance_status",
    "flags",
    "requires",
    "notes",
    "size",
    "sha256",
}

LEGACY_DEPS = ("reportlab",)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILDER), "--profile", "smoke", "--out", str(out), *extra],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )


class CorpusSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="ca-corpus-smoke-")
        cls.tmp = Path(cls._tmp.name)
        cls.out = cls.tmp / "corpus"
        cls.sentinel = cls.tmp / "keep-me.txt"
        cls.sentinel.write_text("not part of the corpus\n", encoding="utf-8")
        cls.build = build(cls.out)
        cls.manifest = {}
        if (cls.out / "manifest.json").exists():
            cls.manifest = json.loads((cls.out / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # -- the five assertions a broken generator would fail first -----------

    def test_build_exits_cleanly_and_reports_its_count(self) -> None:
        self.assertEqual(self.build.returncode, 0, self.build.stderr)
        self.assertIn("Wrote 12 files", self.build.stdout)

    def test_manifest_counts_match_the_target(self) -> None:
        manifest = self.manifest
        self.assertTrue(manifest, "manifest.json was not written")
        self.assertEqual(manifest["corpus"], "ca-unpacker-stress-corpus")
        self.assertTrue(manifest["fictional"])
        self.assertEqual(manifest["profile"], "smoke")
        self.assertEqual(manifest["seed"], 2026)
        self.assertEqual(manifest["file_count"], 12)
        self.assertEqual(len(manifest["files"]), 12)
        self.assertEqual(manifest["families"], EXPECTED_FAMILIES)
        self.assertEqual(
            manifest["total_bytes"], sum(item["size"] for item in manifest["files"])
        )

    def test_every_file_on_disk_matches_its_hash_and_size(self) -> None:
        root = self.out.resolve()
        for item in self.manifest["files"]:
            path = (self.out / item["path"]).resolve()
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(path.relative_to(root).as_posix(), item["path"])
            self.assertEqual(path.stat().st_size, item["size"], item["path"])
            self.assertEqual(sha256_of(path), item["sha256"], item["path"])

    def test_csv_has_the_same_rows_as_the_manifest(self) -> None:
        with (self.out / "manifest.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(set(rows[0].keys()), CSV_COLUMNS)
        self.assertEqual(len(rows), self.manifest["file_count"])
        manifest_rows = {item["path"]: item for item in self.manifest["files"]}
        self.assertEqual({row["path"] for row in rows}, set(manifest_rows))
        for row in rows:
            self.assertEqual(int(row["size"]), manifest_rows[row["path"]]["size"])
            self.assertEqual(row["sha256"], manifest_rows[row["path"]]["sha256"])

    def test_gallery_lists_every_file_without_machine_paths(self) -> None:
        gallery = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn("CA Unpacker stress corpus", gallery)
        for family in EXPECTED_FAMILIES:
            self.assertIn(f">{family}</div>", gallery)
        for item in self.manifest["files"]:
            self.assertIn(item["path"], gallery)
        self.assertNotIn(str(ROOT), gallery)
        self.assertNotIn("C:\\", gallery)

    # -- expectations, not just filenames ----------------------------------

    def test_every_entry_carries_a_known_expectation(self) -> None:
        allowed_outcomes = {
            "processed",
            "needs_review",
            "failed",
            "unclassified",
            "skipped_duplicate",
            "skipped_by_name",
            "rejected_selection",
        }
        for item in self.manifest["files"]:
            self.assertIn(item["outcome"], allowed_outcomes, item["path"])
            self.assertTrue(item["kind"], item["path"])
            self.assertTrue(item["notes"], f"{item['path']} has no note")
            for key, value in item["totals"].items():
                self.assertIn(key, {"debit", "credit", "value", "taxable"}, item["path"])
                self.assertIsInstance(value, (int, float), item["path"])
            if item["balance_status"]:
                self.assertIn(item["balance_status"], {"match", "mismatch", "unverified"})

        banks = [item for item in self.manifest["files"] if item["family"] == "banks"]
        self.assertTrue(all(item["rows"] for item in banks))
        self.assertTrue(all(item["balance_status"] for item in banks))
        broken = [item for item in banks if "closing_mismatch" in item["flags"]]
        self.assertTrue(broken, "the deliberately broken closing balance lost its flag")
        self.assertTrue(all(item["balance_status"] == "mismatch" for item in broken))

    def test_files_live_in_their_family_folder(self) -> None:
        for item in self.manifest["files"]:
            first = Path(item["path"]).parts[0]
            if item["family"] == "mixed":
                self.assertEqual(first, "mixed", item["path"])
            else:
                self.assertEqual(first, item["family"], item["path"])

    def test_second_build_is_identical_and_spares_neighbouring_files(self) -> None:
        second = self.tmp / "corpus-again"
        completed = build(second)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        again = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [(item["path"], item["sha256"]) for item in self.manifest["files"]],
            [(item["path"], item["sha256"]) for item in again["files"]],
        )
        # Rebuilding wiped only its own folder; the sentinel next door survives.
        self.assertTrue(self.sentinel.exists())
        self.assertTrue((self.out / "manifest.json").exists())

    def test_generator_needs_no_extra_renderer(self) -> None:
        source = BUILDER.read_text(encoding="utf-8")
        for dependency in LEGACY_DEPS:
            self.assertNotIn(dependency, source.lower())
        requirement = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        for dependency in LEGACY_DEPS:
            self.assertNotIn(dependency, requirement)


if __name__ == "__main__":
    unittest.main()
