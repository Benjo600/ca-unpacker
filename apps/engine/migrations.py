from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.schema import MetaData

BASELINE_SCHEMA_VERSION = 1
LATEST_SCHEMA_VERSION = 2

APP_TABLES = frozenset(
    {"firms", "clients", "periods", "jobs", "files", "extracted_rows", "data_packs"}
)
VERSION_TABLE = "schema_version"
Migration = Callable[[Connection], None]


def _migrate_v1_to_v2(connection: Connection) -> None:
    statements = (
        "ALTER TABLE files ADD COLUMN parse_outcome VARCHAR(20) "
        "NOT NULL DEFAULT 'unclassified'",
        "ALTER TABLE files ADD COLUMN parse_reason_code VARCHAR(80)",
        "ALTER TABLE files ADD COLUMN parse_reason_message VARCHAR(500)",
        "ALTER TABLE files ADD COLUMN parse_row_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE files ADD COLUMN parse_warnings_json VARCHAR NOT NULL DEFAULT '[]'",
        "ALTER TABLE files ADD COLUMN parser_id VARCHAR(80)",
        "ALTER TABLE files ADD COLUMN parser_version VARCHAR(40)",
        "ALTER TABLE files ADD COLUMN processed_at DATETIME",
        "ALTER TABLE jobs ADD COLUMN intake_discovered_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN intake_accepted_count INTEGER NOT NULL DEFAULT 0",
    )
    for statement in statements:
        connection.exec_driver_sql(statement)


MIGRATION_STEPS: Mapping[int, Migration] = {2: _migrate_v1_to_v2}


def _database_path(engine: Engine) -> Path:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        raise ValueError("Numbered migrations require a file-backed SQLite database")
    return Path(engine.url.database)


def _read_version(connection: Connection, table_names: set[str]) -> int:
    if VERSION_TABLE not in table_names:
        return BASELINE_SCHEMA_VERSION
    rows = connection.exec_driver_sql(
        f"SELECT version FROM {VERSION_TABLE}"
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("schema_version must contain exactly one row")
    return int(rows[0][0])


def _backup_candidate(db_path: Path, from_version: int, to_version: int, index: int) -> Path:
    collision = "" if index == 0 else f".{index}"
    return db_path.with_name(
        f"{db_path.name}.v{from_version}-to-v{to_version}{collision}.backup"
    )


def create_backup(db_path: Path, from_version: int, to_version: int) -> Path:
    """Create a consistent SQLite snapshot without replacing an earlier backup."""
    index = 0
    while True:
        candidate = _backup_candidate(db_path, from_version, to_version, index)
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            index += 1
            continue
        os.close(descriptor)
        break

    source_uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(source_uri, uri=True)) as source:
            with closing(sqlite3.connect(candidate)) as destination:
                source.backup(destination)
    except BaseException:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


def _create_version_table(connection: Connection) -> None:
    connection.exec_driver_sql(
        f"CREATE TABLE {VERSION_TABLE} (version INTEGER NOT NULL)"
    )


def _create_fresh_schema(connection: Connection, metadata: MetaData) -> None:
    metadata.create_all(connection)
    _create_version_table(connection)
    connection.exec_driver_sql(
        f"INSERT INTO {VERSION_TABLE} (version) VALUES (?)",
        (LATEST_SCHEMA_VERSION,),
    )


def ensure_schema(
    engine: Engine,
    metadata: MetaData,
    *,
    migration_steps: Mapping[int, Migration] | None = None,
) -> None:
    """Create the latest schema or transactionally upgrade an existing database."""
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            table_names = set(inspect(connection).get_table_names())
            if not (table_names & APP_TABLES):
                _create_fresh_schema(connection, metadata)
            else:
                current_version = _read_version(connection, table_names)
                if current_version > LATEST_SCHEMA_VERSION:
                    raise RuntimeError(
                        f"Database schema v{current_version} is newer than supported "
                        f"v{LATEST_SCHEMA_VERSION}"
                    )
                steps = MIGRATION_STEPS if migration_steps is None else migration_steps
                missing_steps = [
                    version
                    for version in range(current_version + 1, LATEST_SCHEMA_VERSION + 1)
                    if version not in steps
                ]
                if missing_steps:
                    raise RuntimeError(f"Missing database migration steps: {missing_steps}")
                if current_version < LATEST_SCHEMA_VERSION:
                    create_backup(
                        _database_path(engine), current_version, LATEST_SCHEMA_VERSION
                    )
                    if VERSION_TABLE not in table_names:
                        _create_version_table(connection)
                        connection.exec_driver_sql(
                            f"INSERT INTO {VERSION_TABLE} (version) VALUES (?)",
                            (current_version,),
                        )
                    for version in range(
                        current_version + 1, LATEST_SCHEMA_VERSION + 1
                    ):
                        steps[version](connection)
                        connection.exec_driver_sql(
                            f"UPDATE {VERSION_TABLE} SET version = ?",
                            (version,),
                        )
        except BaseException:
            connection.rollback()
            raise
        connection.commit()
