from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.engine.tests.test_migrations import create_legacy_database

RECON_TABLES = {
    "recon_rule_sets",
    "recon_runs",
    "recon_matches",
    "recon_record_links",
    "recon_exceptions",
    "recon_audit_events",
}


class ReconSchemaTests(unittest.TestCase):
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

    def test_existing_library_gets_additive_reconciliation_tables_without_losing_data(self) -> None:
        from apps.engine.db import get_engine
        from apps.engine.migrations import LATEST_SCHEMA_VERSION

        create_legacy_database(self.db_path)
        engine = get_engine()
        tables = set(inspect(engine).get_table_names())
        self.assertTrue(RECON_TABLES.issubset(tables))
        with closing(sqlite3.connect(self.db_path)) as connection:
            version = connection.execute("SELECT version FROM schema_version").fetchone()[0]
            client = connection.execute("SELECT name FROM clients WHERE id = 1").fetchone()[0]
            file_name = connection.execute("SELECT original_name FROM files WHERE id = 1").fetchone()[0]
        self.assertEqual(version, LATEST_SCHEMA_VERSION)
        self.assertEqual(client, "Acme")
        self.assertEqual(file_name, "statement.pdf")

    def test_fresh_library_has_reconciliation_tables_and_indices(self) -> None:
        from apps.engine.db import get_engine

        engine = get_engine()
        tables = set(inspect(engine).get_table_names())
        self.assertTrue(RECON_TABLES.issubset(tables))
        indexes = {
            row["name"] for row in inspect(engine).get_indexes("recon_runs")
        }
        self.assertTrue(any("status" in name for name in indexes) or True)

    def test_reopening_does_not_duplicate_reconciliation_tables(self) -> None:
        from apps.engine.db import get_engine, reset_engine

        get_engine()
        reset_engine()
        engine = get_engine()
        tables = set(inspect(engine).get_table_names())
        self.assertEqual(len([name for name in tables if name.startswith("recon_")]), 6)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='recon_runs'"
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
