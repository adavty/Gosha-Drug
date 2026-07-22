from __future__ import annotations

import argparse
import os

from .store_factory import build_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Gosha storage configuration and migrations without Telegram token")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--db", default=os.environ.get("GOSHA_DB", ":memory:"))
    parser.add_argument("--require-postgres", action="store_true")
    args = parser.parse_args(argv)
    if args.require_postgres and not args.database_url:
        parser.error("DATABASE_URL is required for production profile")
    store = build_store(database_url=args.database_url, sqlite_path=args.db)
    try:
        row = store.conn.execute("SELECT 1 AS ok").fetchone()
        if not row or int(row["ok"]) != 1:
            raise RuntimeError("database_healthcheck_failed")
        if args.database_url:
            migrations = store.conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            if not migrations:
                raise RuntimeError("postgres_migrations_not_applied")
            print(f"storage=postgres migrations=ok count={len(migrations)}")
        else:
            print("storage=sqlite local_only=1")
        return 0
    finally:
        close = getattr(store, "close", None)
        if close:
            close()


if __name__ == "__main__":
    raise SystemExit(main())
