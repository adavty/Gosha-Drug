from __future__ import annotations

import re
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from .store import Store


def _postgres_sql(sql: str) -> str:
    """Translate the deliberately small SQLite-compatible query subset."""
    ignored = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", sql, flags=re.I))
    translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    translated = translated.replace("?", "%s")
    if ignored and "ON CONFLICT" not in translated.upper():
        translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return translated


class _CompatConnection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params=()):
        return self.raw.execute(_postgres_sql(sql), params)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


class PostgresStore(Store):
    """PostgreSQL production profile implementing the same repository contract.

    `psycopg` is imported lazily so local/offline use has no PostgreSQL runtime
    dependency. Migrations are explicit and recorded in `schema_migrations`.
    """

    def __init__(self, dsn: str, *, apply_migrations: bool = True):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - environment specific
            raise RuntimeError("Install gosha-jmlc[postgres] for the PostgreSQL profile") from exc
        self.path = dsn
        self.lock = RLock()
        raw = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        self.conn = _CompatConnection(raw)
        if apply_migrations:
            self.apply_migrations()

    def apply_migrations(self) -> None:
        candidates = [
            Path(os.environ["GOSHA_MIGRATIONS_DIR"]) if os.environ.get("GOSHA_MIGRATIONS_DIR") else None,
            Path.cwd() / "migrations" / "postgres",
            Path(sys.prefix) / "share" / "gosha" / "migrations" / "postgres",
            Path(__file__).resolve().parents[2] / "migrations" / "postgres",
        ]
        root = next((path for path in candidates if path and path.is_dir()), None)
        if root is None:
            raise RuntimeError("PostgreSQL migrations directory not found")
        raw = self.conn.raw
        with self.lock:
            with raw.transaction():
                raw.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            paths = sorted(root.glob("*.sql"))
            if not paths:
                raise RuntimeError("No PostgreSQL migrations found")
            for path in paths:
                # One migration and its marker are one PostgreSQL transaction.
                # The advisory lock prevents concurrent deployers from applying
                # the same version before either can see its marker.
                with raw.transaction():
                    raw.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"gosha-migration:{path.name}",))
                    row = raw.execute("SELECT version FROM schema_migrations WHERE version=%s", (path.name,)).fetchone()
                    if row:
                        continue
                    raw.execute(path.read_text(encoding="utf-8"))
                    raw.execute("INSERT INTO schema_migrations(version) VALUES(%s)", (path.name,))

    def runtime_setting_enabled(self, key: str, *, conn=None, lock: bool = False) -> bool:
        target = conn.raw if conn is not None else self.conn.raw
        suffix = " FOR SHARE" if lock and conn is not None else ""
        params = (key,)
        if conn is not None:
            row = target.execute(f"SELECT value FROM runtime_settings WHERE key=%s{suffix}", params).fetchone()
        else:
            with self.lock:
                row = target.execute("SELECT value FROM runtime_settings WHERE key=%s", params).fetchone()
        return bool(row and row["value"] == "1")

    def acquire_idempotency_lock(self, conn: _CompatConnection, key: str) -> None:
        # Stable transaction-scoped mutex for parallel retries of the same key.
        conn.raw.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))

    def pending_for_update(self, conn: _CompatConnection, pending_id: str, chat_id: str, actor_id: str, now):
        return conn.raw.execute(
            "SELECT * FROM pending WHERE id=%s AND chat_id=%s AND actor_id=%s AND consumed=0 AND expires_at>%s FOR UPDATE",
            (pending_id, chat_id, actor_id, now.isoformat()),
        ).fetchone()

    @contextmanager
    def tx(self) -> Iterator[_CompatConnection]:
        with self.lock:
            try:
                self.conn.execute("BEGIN")
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def close(self) -> None:
        self.conn.close()
