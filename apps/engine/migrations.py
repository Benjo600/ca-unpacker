from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.schema import MetaData

BASELINE_SCHEMA_VERSION = 1
LATEST_SCHEMA_VERSION = 3

_log = logging.getLogger(__name__)

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


def _migrate_v2_to_v3(connection: Connection) -> None:
    statements = (
        "ALTER TABLE files ADD COLUMN currency_code VARCHAR(3)",
        "ALTER TABLE files ADD COLUMN currency_source VARCHAR(40)",
        "ALTER TABLE files ADD COLUMN currency_confidence FLOAT",
        "ALTER TABLE files ADD COLUMN currency_candidates_json VARCHAR "
        "NOT NULL DEFAULT '[]'",
        "ALTER TABLE files ADD COLUMN currency_status VARCHAR(20)",
        "ALTER TABLE files ADD COLUMN currency_override VARCHAR(3)",
        "ALTER TABLE clients ADD COLUMN profession_key VARCHAR(60)",
        "ALTER TABLE clients ADD COLUMN profession_label VARCHAR(120)",
        "ALTER TABLE clients ADD COLUMN entity_type VARCHAR(40)",
        "ALTER TABLE clients ADD COLUMN gst_registered INTEGER",
        "ALTER TABLE clients ADD COLUMN profile_json VARCHAR NOT NULL DEFAULT '{}'",
    )
    for statement in statements:
        connection.exec_driver_sql(statement)


MIGRATION_STEPS: Mapping[int, Migration] = {
    2: _migrate_v1_to_v2,
    3: _migrate_v2_to_v3,
}


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


def _column_default_literal(column) -> str | None:
    """A literal SQLite accepts in ADD COLUMN ... NOT NULL DEFAULT <here>."""
    name = column.name.lower()
    if name.endswith("_json"):
        return "'{}'"
    try:
        python_type = column.type.python_type
    except (NotImplementedError, AttributeError):
        return None
    if python_type is bool:
        return "0"
    if python_type is int:
        return "0"
    if python_type is float:
        return "0.0"
    if python_type is str:
        return "''"
    return None


def _add_column_statement(connection: Connection, table_name: str, column) -> str:
    type_sql = column.type.compile(dialect=connection.dialect)
    literal = _column_default_literal(column)
    if not column.nullable and literal is not None:
        tail = f" NOT NULL DEFAULT {literal}"
    else:
        # Dates and other values have no safe literal: add them nullable so the
        # repair cannot write junk into existing rows.
        tail = ""
    return f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {type_sql}{tail}'


def repair_missing_columns(connection: Connection, metadata: MetaData) -> list[str]:
    """Add columns this build expects but the file on disk does not have.

    Libraries written by a newer build, or by a build whose model changed
    without a migration, end up missing columns the code reads on every query -
    which surfaced as an unopenable app. SQLite only supports additive column
    changes, so that is all this does; nothing is dropped or rewritten.
    """
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    for table_name, table in metadata.tables.items():
        if table_name not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in present:
                continue
            connection.exec_driver_sql(
                _add_column_statement(connection, table_name, column)
            )
            added.append(f"{table_name}.{column.name}")
    return added


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
    """Create the latest schema, upgrade an older one, or open a newer one.

    A library written by a newer build used to abort startup outright. It now
    opens as-is (numbered migrations cannot run backwards) and any column this
    build reads but the file lacks is added, so an app update cannot leave the
    user with a window that refuses to start.
    """
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            table_names = set(inspect(connection).get_table_names())
            if not (table_names & APP_TABLES):
                _create_fresh_schema(connection, metadata)
            else:
                current_version = _read_version(connection, table_names)
                steps = MIGRATION_STEPS if migration_steps is None else migration_steps
                if current_version > LATEST_SCHEMA_VERSION:
                    # Another build already moved this library forward. Numbered
                    # migrations cannot go backwards, so open it read/write as it
                    # is instead of refusing to start, then make sure every column
                    # this build reads actually exists.
                    _log.warning(
                        "Library schema v%s is newer than this build supports (v%s); "
                        "opening it without migrating",
                        current_version,
                        LATEST_SCHEMA_VERSION,
                    )
                else:
                    missing_steps = [
                        version
                        for version in range(current_version + 1, LATEST_SCHEMA_VERSION + 1)
                        if version not in steps
                    ]
                    if missing_steps:
                        raise RuntimeError(
                            f"Missing database migration steps: {missing_steps}"
                        )
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
                repaired = repair_missing_columns(connection, metadata)
                if repaired:
                    _log.warning(
                        "Library was missing columns this build needs and they were "
                        "added: %s",
                        ", ".join(repaired),
                    )
                # Additive schema repair for tables introduced by newer,
                # backwards-compatible features (reconciliation runs,
                # exceptions, audit events, rule snapshots).  create_all is
                # checkfirst/idempotent and never alters or drops a table that
                # already exists, so older libraries keep their data intact.
                metadata.create_all(connection)
        except BaseException:
            connection.rollback()
            raise
        connection.commit()
