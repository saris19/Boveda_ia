"""Minimal schema migrations for databases created by earlier versions (e.g. the Render PostgreSQL).

`create_all` creates missing tables but never adds columns to existing ones, so new columns are added
here with a safe default. Idempotent: safe to run on every startup.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> {column: (postgresql type, sqlite type)}
NEW_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "documents": {
        "search_index": ("JSON", "JSON"),                                       # v0.5
        "key_version": ("INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),  # v1.0
        "version_number": ("INTEGER NOT NULL DEFAULT 1", "INTEGER NOT NULL DEFAULT 1"),
        "deleted_at": ("TIMESTAMP WITH TIME ZONE", "DATETIME"),
        "deleted_by": ("INTEGER", "INTEGER"),
        "manual_classification": ("BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT 0"),
    },
    "users": {
        "downloads_blocked_until": ("TIMESTAMP WITH TIME ZONE", "DATETIME"),
    },
}


def run_migrations(engine: Engine) -> list[str]:
    applied = []
    inspector = inspect(engine)
    is_postgres = engine.dialect.name == "postgresql"
    with engine.begin() as connection:
        for table, columns in NEW_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, (pg_type, sqlite_type) in columns.items():
                if column not in existing:
                    sql_type = pg_type if is_postgres else sqlite_type
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
                    applied.append(f"{table}.{column}")
    if applied:
        print(f"[Bóveda] Migraciones aplicadas: {', '.join(applied)}")
    return applied
