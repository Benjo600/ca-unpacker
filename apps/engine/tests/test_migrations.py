from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect


LEGACY_SCHEMA = """
CREATE TABLE firms (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    library_path VARCHAR(500) NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    firm_id INTEGER NOT NULL REFERENCES firms(id),
    name VARCHAR(200) NOT NULL,
    gstin VARCHAR(15),
    created_at DATETIME NOT NULL
);
CREATE TABLE periods (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    label VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    period_id INTEGER NOT NULL REFERENCES periods(id),
    status VARCHAR(20) NOT NULL,
    error_message VARCHAR(500),
    created_at DATETIME NOT NULL,
    finished_at DATETIME
);
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    period_id INTEGER NOT NULL REFERENCES periods(id),
    original_name VARCHAR(260) NOT NULL,
    mime VARCHAR(120),
    size INTEGER NOT NULL,
    storage_key VARCHAR(500) NOT NULL,
    detected_kind VARCHAR(20) NOT NULL,
    override_kind VARCHAR(20),
    confidence FLOAT NOT NULL,
    classify_reason VARCHAR(300) NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE extracted_rows (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    period_id INTEGER NOT NULL REFERENCES periods(id),
    kind VARCHAR(20) NOT NULL,
    payload_json VARCHAR NOT NULL,
    source_page INTEGER NOT NULL,
    source_bbox VARCHAR(80),
    validation_flags VARCHAR NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE data_packs (
    id INTEGER PRIMARY KEY,
    period_id INTEGER NOT NULL REFERENCES periods(id),
    job_id INTEGER REFERENCES jobs(id),
    bank_xlsx_key VARCHAR(500),
    balance_status VARCHAR(20),
    row_count INTEGER NOT NULL,
    created_at DATETIME NOT NULL
);
"""


def create_legacy_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO firms VALUES (1, 'Patel & Co', 'D:/CA', '2026-08-01')"
        )
        connection.execute(
            "INSERT INTO clients VALUES (1, 1, 'Acme', NULL, '2026-08-01')"
        )
        connection.execute(
            "INSERT INTO periods VALUES (1, 1, 'Jul 2026', '2026-08-01')"
        )
        connection.execute(
            "INSERT INTO jobs VALUES (1, 1, 1, 'done', NULL, '2026-08-01', NULL)"
        )
        connection.execute(
            """INSERT INTO files VALUES (
                1, 1, 1, 'statement.pdf', 'application/pdf', 123,
                '1/statement.pdf', 'bank', NULL, 0.9, 'matched', '2026-08-01'
            )"""
        )
        connection.execute(
            "INSERT INTO data_packs VALUES "
            "(1, 1, 1, 'packs/bank.xlsx', 'balanced', 12, '2026-08-01')"
        )
        connection.commit()


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.local_app_data = Path(self._tmp.name)
        self.db_path = self.local_app_data / "CAUnpacker" / "app.db"
        self._env = patch.dict(os.environ, {"LOCALAPPDATA": self._tmp.name})
        self._env.start()
        from apps.engine.db import reset_engine

        reset_engine()

    def tearDown(self) -> None:
        from apps.engine.db import reset_engine

        reset_engine()
        self._env.stop()
        self._tmp.cleanup()

    def test_fresh_database_is_created_at_latest_version_without_backup(self) -> None:
        from apps.engine.db import get_engine
        from apps.engine.migrations import LATEST_SCHEMA_VERSION

        engine = get_engine()
        table_names = set(inspect(engine).get_table_names())
        self.assertIn("files", table_names)
        self.assertIn("jobs", table_names)
        self.assertIn("schema_version", table_names)
        with closing(sqlite3.connect(self.db_path)) as connection:
            version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
        self.assertEqual(version, LATEST_SCHEMA_VERSION)
        self.assertEqual(list(self.db_path.parent.glob("*.backup*")), [])

    def test_current_unversioned_schema_is_upgraded_without_losing_data(self) -> None:
        from apps.engine.db import get_engine
        from apps.engine.migrations import LATEST_SCHEMA_VERSION

        create_legacy_database(self.db_path)
        pack_path = self.db_path.parent / "packs" / "bank.xlsx"
        pack_path.parent.mkdir()
        pack_path.write_bytes(b"existing output pack")
        engine = get_engine()

        file_columns = {column["name"] for column in inspect(engine).get_columns("files")}
        job_columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
        self.assertTrue(
            {
                "parse_outcome",
                "parse_reason_code",
                "parse_reason_message",
                "parse_row_count",
                "parse_warnings_json",
                "parser_id",
                "parser_version",
                "processed_at",
            }.issubset(file_columns)
        )
        self.assertTrue(
            {"intake_discovered_count", "intake_accepted_count"}.issubset(job_columns)
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            file_row = connection.execute(
                "SELECT original_name, storage_key, parse_outcome, parse_row_count "
                "FROM files WHERE id = 1"
            ).fetchone()
            job_row = connection.execute(
                "SELECT status, intake_discovered_count, intake_accepted_count "
                "FROM jobs WHERE id = 1"
            ).fetchone()
            version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
            pack_row = connection.execute(
                "SELECT bank_xlsx_key, row_count FROM data_packs WHERE id = 1"
            ).fetchone()
        self.assertEqual(file_row, ("statement.pdf", "1/statement.pdf", "unclassified", 0))
        self.assertEqual(job_row, ("done", 0, 0))
        self.assertEqual(pack_row, ("packs/bank.xlsx", 12))
        self.assertEqual(pack_path.read_bytes(), b"existing output pack")
        self.assertEqual(version, LATEST_SCHEMA_VERSION)

    def test_upgrade_creates_a_non_overwriting_copy_of_the_pre_upgrade_database(self) -> None:
        from apps.engine.db import get_engine, reset_engine

        create_legacy_database(self.db_path)
        occupied = self.db_path.with_name("app.db.v1-to-v2.backup")
        occupied.write_bytes(b"older backup")

        get_engine()
        reset_engine()

        backups = sorted(self.db_path.parent.glob("app.db.v1-to-v2*.backup"))
        self.assertEqual(len(backups), 2)
        self.assertEqual(occupied.read_bytes(), b"older backup")
        new_backup = next(path for path in backups if path != occupied)
        with closing(sqlite3.connect(new_backup)) as connection:
            self.assertEqual(
                connection.execute("SELECT original_name FROM files").fetchone()[0],
                "statement.pdf",
            )
            self.assertNotIn(
                "parse_outcome",
                {row[1] for row in connection.execute("PRAGMA table_info(files)")},
            )
            self.assertNotIn(
                "schema_version",
                {row[0] for row in connection.execute("SELECT name FROM sqlite_master")},
            )

    def test_reopening_latest_database_is_idempotent_and_does_not_back_up_again(self) -> None:
        from apps.engine.db import get_engine, reset_engine

        create_legacy_database(self.db_path)
        get_engine()
        reset_engine()
        backups_after_upgrade = list(self.db_path.parent.glob("*.backup"))

        get_engine()
        reset_engine()

        self.assertEqual(list(self.db_path.parent.glob("*.backup")), backups_after_upgrade)
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM files").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT version FROM schema_version").fetchone()[0], 2)

    def test_failed_migration_rolls_back_schema_and_does_not_record_a_version(self) -> None:
        from sqlalchemy import create_engine

        from apps.engine.db import Base
        from apps.engine.migrations import ensure_schema

        create_legacy_database(self.db_path)
        engine = create_engine(f"sqlite:///{self.db_path}")

        def failing_migration(connection) -> None:
            connection.exec_driver_sql("ALTER TABLE files ADD COLUMN partial_change TEXT")
            raise RuntimeError("simulated failure")

        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            ensure_schema(engine, Base.metadata, migration_steps={2: failing_migration})

        engine.dispose()
        with closing(sqlite3.connect(self.db_path)) as connection:
            file_columns = {row[1] for row in connection.execute("PRAGMA table_info(files)")}
            table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
            self.assertNotIn("partial_change", file_columns)
            self.assertNotIn("schema_version", table_names)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM files").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
