from __future__ import annotations

from pathlib import Path

from .postgres_store import PostgresStore
from .repository import Repository
from .store import Store


def build_store(*, database_url: str | None = None, sqlite_path: str | Path = ":memory:") -> Repository:
    """Select the explicit storage profile; PostgreSQL is never silently downgraded."""
    if database_url:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL DSN")
        return PostgresStore(database_url)
    return Store(sqlite_path)

