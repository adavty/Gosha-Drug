from __future__ import annotations

import json
import re
import sqlite3
import statistics
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Iterator
from zoneinfo import ZoneInfo

from .models import Deadline


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS chats(chat_id TEXT PRIMARY KEY, timezone_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS runtime_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL, actor_id TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deadlines(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, title TEXT NOT NULL, due_local TEXT NOT NULL,
 timezone_id TEXT NOT NULL, due_utc TEXT NOT NULL, author_id TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(chat_id) REFERENCES chats(chat_id));
CREATE INDEX IF NOT EXISTS idx_deadlines_chat ON deadlines(chat_id, status, due_utc);
CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, actor_id TEXT NOT NULL, action TEXT NOT NULL,
 object_id TEXT, before_json TEXT, after_json TEXT, correlation_id TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminders(job_key TEXT PRIMARY KEY, chat_id TEXT NOT NULL, deadline_id TEXT NOT NULL,
 type TEXT NOT NULL, scheduled_for TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled',
 payload_json TEXT NOT NULL DEFAULT '{}', attempt_count INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 5, available_at TEXT, claimed_by TEXT, claimed_at TEXT,
 lease_until TEXT, last_error TEXT, telegram_message_id TEXT, delivered_at TEXT);
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, request_fingerprint TEXT, response_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, name TEXT NOT NULL, chat_key TEXT NOT NULL, user_key TEXT NOT NULL,
 result TEXT NOT NULL, correlation_id TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, description TEXT NOT NULL,
 url TEXT NOT NULL, canonical_url TEXT NOT NULL, domain TEXT NOT NULL, author_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(chat_id, canonical_url), FOREIGN KEY(chat_id) REFERENCES chats(chat_id));
CREATE INDEX IF NOT EXISTS idx_materials_chat ON materials(chat_id, status, created_at);
CREATE TABLE IF NOT EXISTS delivery_attempts(id TEXT PRIMARY KEY, job_key TEXT NOT NULL, attempt_no INTEGER NOT NULL,
 attempted_at TEXT NOT NULL, result TEXT NOT NULL, error TEXT, telegram_message_id TEXT,
 UNIQUE(job_key,attempt_no), FOREIGN KEY(job_key) REFERENCES reminders(job_key));
CREATE TABLE IF NOT EXISTS participants(chat_id TEXT NOT NULL, user_id TEXT NOT NULL, display_name TEXT NOT NULL,
 username TEXT, status TEXT NOT NULL DEFAULT 'active', source TEXT NOT NULL, first_seen_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, PRIMARY KEY(chat_id,user_id), FOREIGN KEY(chat_id) REFERENCES chats(chat_id));
CREATE INDEX IF NOT EXISTS idx_participants_chat_status ON participants(chat_id,status,last_seen_at);
CREATE TABLE IF NOT EXISTS csat_surveys(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, period TEXT NOT NULL,
 job_key TEXT NOT NULL UNIQUE, scheduled_for TEXT NOT NULL, sent_at TEXT, telegram_message_id TEXT,
 created_at TEXT NOT NULL, UNIQUE(chat_id,period), FOREIGN KEY(chat_id) REFERENCES chats(chat_id));
CREATE INDEX IF NOT EXISTS idx_csat_surveys_period ON csat_surveys(period,chat_id);
CREATE TABLE IF NOT EXISTS csat_responses(survey_id TEXT NOT NULL, chat_id TEXT NOT NULL, user_id TEXT NOT NULL,
 score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 6), responded_at TEXT NOT NULL,
 PRIMARY KEY(survey_id,user_id), FOREIGN KEY(survey_id) REFERENCES csat_surveys(id),
 FOREIGN KEY(chat_id) REFERENCES chats(chat_id));
CREATE INDEX IF NOT EXISTS idx_csat_responses_chat ON csat_responses(chat_id,responded_at);
"""

REMINDER_MIGRATIONS = {
    "payload_json": "TEXT NOT NULL DEFAULT '{}'",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "max_attempts": "INTEGER NOT NULL DEFAULT 5",
    "available_at": "TEXT",
    "claimed_by": "TEXT",
    "claimed_at": "TEXT",
    "lease_until": "TEXT",
    "last_error": "TEXT",
    "telegram_message_id": "TEXT",
    "delivered_at": "TEXT",
}

MATERIAL_MIGRATIONS = {
    "canonical_url": "TEXT",
    "domain": "TEXT",
    "version": "INTEGER NOT NULL DEFAULT 1",
}


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = RLock()
        had_runtime_settings = bool(
            self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runtime_settings'"
            ).fetchone()
        )
        # Bootstrap tables first. Indexes that depend on compatibility columns are
        # intentionally created only after the upgrade transaction below.
        self.conn.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA}\nCOMMIT;")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in self.conn.execute("PRAGMA table_info(idempotency)")}
            if "request_fingerprint" not in columns:
                self.conn.execute("ALTER TABLE idempotency ADD COLUMN request_fingerprint TEXT")
            reminder_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(reminders)")}
            for name, declaration in REMINDER_MIGRATIONS.items():
                if name not in reminder_columns:
                    self.conn.execute(f"ALTER TABLE reminders ADD COLUMN {name} {declaration}")
            material_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(materials)")}
            for name, declaration in MATERIAL_MIGRATIONS.items():
                if name not in material_columns:
                    self.conn.execute(f"ALTER TABLE materials ADD COLUMN {name} {declaration}")
            self.conn.execute("UPDATE materials SET canonical_url=url WHERE canonical_url IS NULL")
            self.conn.execute("UPDATE materials SET domain='' WHERE domain IS NULL")
            self.conn.execute("UPDATE reminders SET available_at=scheduled_for WHERE available_at IS NULL")
            self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_materials_chat_canonical ON materials(chat_id,canonical_url)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status,scheduled_for,available_at)")
            if not had_runtime_settings:
                now = datetime.now(timezone.utc).isoformat()
                self.conn.executemany(
                    "INSERT INTO runtime_settings(key,value,updated_at,actor_id,reason) VALUES(?,?,?,?,?)",
                    [
                        ("global_sends_enabled", "1", now, "bootstrap", "fresh_database_default"),
                        ("global_writes_enabled", "1", now, "bootstrap", "fresh_database_default"),
                        ("global_llm_enabled", "1", now, "bootstrap", "fresh_database_default"),
                    ],
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.conn.close()
            raise

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def add_chat(self, chat_id: str, timezone_id: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO chats(chat_id, timezone_id, enabled) VALUES(?,?,1) ON CONFLICT(chat_id) DO UPDATE SET timezone_id=excluded.timezone_id", (chat_id, timezone_id))
            self.conn.commit()

    def upsert_participant(
        self, chat_id: str, user_id: str, display_name: str, username: str | None,
        now: datetime, *, source: str = "observed", explicit: bool = False,
    ) -> None:
        clean_name = " ".join(display_name.split())[:80] or f"Участник {user_id[-4:]}"
        clean_username = username if username and re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) else None
        with self.lock:
            self.conn.execute(
                "INSERT INTO participants(chat_id,user_id,display_name,username,status,source,first_seen_at,last_seen_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET "
                "display_name=excluded.display_name,username=excluded.username,last_seen_at=excluded.last_seen_at,"
                "source=CASE WHEN ?=1 THEN excluded.source ELSE participants.source END,"
                "status=CASE WHEN participants.status='opted_out' AND ?=0 THEN 'opted_out' ELSE 'active' END",
                (chat_id, user_id, clean_name, clean_username, "active", source, now.isoformat(), now.isoformat(), int(explicit), int(explicit)),
            )
            self.conn.commit()

    def opt_out_participant(self, chat_id: str, user_id: str, now: datetime) -> bool:
        with self.lock:
            result = self.conn.execute(
                "UPDATE participants SET status='opted_out',last_seen_at=? WHERE chat_id=? AND user_id=?",
                (now.isoformat(), chat_id, user_id),
            )
            self.conn.commit()
        return result.rowcount == 1

    def list_participants(self, chat_id: str) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT user_id,display_name,username,source,last_seen_at FROM participants "
                "WHERE chat_id=? AND status='active' ORDER BY first_seen_at,user_id", (chat_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_call_all(self, chat_id: str, since: datetime) -> bool:
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM reminders WHERE chat_id=? AND type='call_all' AND scheduled_for>=? LIMIT 1",
                (chat_id, since.isoformat()),
            ).fetchone()
        return bool(row)

    def ensure_monthly_csat(self, now: datetime) -> int:
        """Create one idempotent monthly CSAT outbox job per enabled chat."""
        created = 0
        with self.tx() as conn:
            chats = conn.execute("SELECT chat_id,timezone_id FROM chats WHERE enabled=1 ORDER BY chat_id").fetchall()
            for chat in chats:
                local_now = now.astimezone(ZoneInfo(chat["timezone_id"]))
                local_due = local_now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
                # A newly added chat should not receive a stale survey late in
                # the month. Allow a one-day catch-up after the normal slot;
                # otherwise schedule the next calendar month.
                if local_now > local_due + timedelta(days=1):
                    if local_due.month == 12:
                        local_due = local_due.replace(year=local_due.year + 1, month=1)
                    else:
                        local_due = local_due.replace(month=local_due.month + 1)
                period = local_due.strftime("%Y-%m")
                scheduled_for = local_due.astimezone(timezone.utc).isoformat()
                survey_id = uuid.uuid4().hex[:12]
                job_key = f"csat:{chat['chat_id']}:{period}"
                result = conn.execute(
                    "INSERT INTO csat_surveys(id,chat_id,period,job_key,scheduled_for,created_at) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(chat_id,period) DO NOTHING",
                    (survey_id, chat["chat_id"], period, job_key, scheduled_for, now.isoformat()),
                )
                if result.rowcount != 1:
                    continue
                conn.execute(
                    "INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,payload_json,max_attempts,available_at) "
                    "VALUES(?,?,?,'csat_survey',?,'scheduled',?,3,?) ON CONFLICT(job_key) DO NOTHING",
                    (job_key, chat["chat_id"], "*", scheduled_for,
                     json.dumps({"survey_id": survey_id, "period": period}, ensure_ascii=False), scheduled_for),
                )
                created += 1
        return created

    def record_csat_response(
        self, survey_id: str, chat_id: str, user_id: str, score: int, now: datetime,
    ) -> str | None:
        if score not in range(1, 7):
            return None
        with self.tx() as conn:
            survey = conn.execute(
                "SELECT s.id FROM csat_surveys s JOIN reminders r ON r.job_key=s.job_key "
                "WHERE s.id=? AND s.chat_id=? AND r.status IN ('sending','delivered','delivery_unknown')",
                (survey_id, chat_id),
            ).fetchone()
            if not survey:
                return None
            previous = conn.execute(
                "SELECT 1 FROM csat_responses WHERE survey_id=? AND user_id=?", (survey_id, user_id)
            ).fetchone()
            conn.execute(
                "INSERT INTO csat_responses(survey_id,chat_id,user_id,score,responded_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(survey_id,user_id) DO UPDATE SET score=excluded.score,responded_at=excluded.responded_at",
                (survey_id, chat_id, user_id, score, now.isoformat()),
            )
        return "updated" if previous else "created"

    def csat_statistics(self, period: str | None = None) -> dict:
        with self.lock:
            selected = period
            if selected is None:
                row = self.conn.execute(
                    "SELECT max(s.period) AS period FROM csat_surveys s "
                    "WHERE EXISTS(SELECT 1 FROM csat_responses r WHERE r.survey_id=s.id)"
                ).fetchone()
                selected = row["period"] if row else None
            if period == "all":
                rows = self.conn.execute("SELECT score FROM csat_responses ORDER BY score").fetchall()
            elif selected:
                rows = self.conn.execute(
                    "SELECT r.score FROM csat_responses r JOIN csat_surveys s ON s.id=r.survey_id "
                    "WHERE s.period=? ORDER BY r.score", (selected,),
                ).fetchall()
            else:
                rows = []
        scores = [int(row["score"]) for row in rows]
        return {
            "period": selected or period,
            "count": len(scores),
            "average": (sum(scores) / len(scores)) if scores else None,
            "median": statistics.median(scores) if scores else None,
        }

    @staticmethod
    def _quarantine_sending(conn, where_sql: str, params: tuple, actor_id: str, reason: str, now: datetime) -> int:
        rows = conn.execute(
            f"SELECT job_key,chat_id,attempt_count FROM reminders WHERE status='sending' AND {where_sql}", params
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE reminders SET status='delivery_unknown',available_at=NULL,claimed_by=NULL,claimed_at=NULL,"
                "lease_until=NULL,last_error=? WHERE job_key=? AND status='sending'",
                (f"scheduled_send_stop:{reason}"[:500], row["job_key"]),
            )
            conn.execute(
                "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, row["job_key"], row["attempt_count"], now.isoformat(), "delivery_unknown", f"scheduled_send_stop:{reason}"[:500], None),
            )
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, row["chat_id"], actor_id, "scheduled_send_stop_unknown", row["job_key"], None,
                 json.dumps({"reason": reason, "status": "delivery_unknown"}, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()),
            )
        return len(rows)

    def set_chat_enabled(
        self, chat_id: str, enabled: bool, *, actor_id: str = "system", reason: str = "",
        now: datetime | None = None,
    ) -> None:
        """Persist per-chat stop; re-enable never resurrects cancelled sends."""
        now = now or datetime.now(timezone.utc)
        with self.tx() as conn:
            conn.execute("UPDATE chats SET enabled=? WHERE chat_id=?", (int(enabled), chat_id))
            if not enabled:
                conn.execute(
                    "UPDATE reminders SET status='cancelled',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,"
                    "last_error=? WHERE chat_id=? AND status IN ('scheduled','retry_wait','claimed')",
                    (f"per_chat_stop:{reason}"[:500], chat_id),
                )
                self._quarantine_sending(conn, "chat_id=?", (chat_id,), actor_id, reason or "per_chat_stop", now)
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, chat_id, actor_id, "chat_send_stop_changed", chat_id, None,
                 json.dumps({"enabled": enabled, "reason": reason}, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()),
            )

    def global_sends_enabled(self) -> bool:
        return self.runtime_setting_enabled("global_sends_enabled")

    def runtime_setting_enabled(self, key: str, *, conn=None, lock: bool = False) -> bool:
        """Read a durable gate; a missing/invalid setting always fails closed."""
        del lock  # SQLite BEGIN IMMEDIATE already serializes the transactional path.
        if conn is not None:
            row = conn.execute("SELECT value FROM runtime_settings WHERE key=?", (key,)).fetchone()
            return bool(row and row["value"] == "1")
        with self.lock:
            row = self.conn.execute("SELECT value FROM runtime_settings WHERE key=?", (key,)).fetchone()
        return bool(row and row["value"] == "1")

    def set_runtime_setting(
        self, key: str, enabled: bool, *, actor_id: str, reason: str,
        now: datetime | None = None,
    ) -> None:
        if key not in {"global_writes_enabled", "global_llm_enabled"}:
            raise ValueError("unsupported_runtime_setting")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_and_reason_required")
        now = now or datetime.now(timezone.utc)
        with self.tx() as conn:
            before = conn.execute("SELECT value FROM runtime_settings WHERE key=?", (key,)).fetchone()
            conn.execute(
                "INSERT INTO runtime_settings(key,value,updated_at,actor_id,reason) VALUES(?,?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at,"
                "actor_id=excluded.actor_id,reason=excluded.reason",
                (key, "1" if enabled else "0", now.isoformat(), actor_id, reason),
            )
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, "__global__", actor_id, f"{key}_changed", key,
                 json.dumps({"enabled": bool(before and before["value"] == "1")}, ensure_ascii=False),
                 json.dumps({"enabled": enabled, "reason": reason}, ensure_ascii=False),
                 uuid.uuid4().hex, now.isoformat()),
            )

    def global_writes_enabled(self) -> bool:
        return self.runtime_setting_enabled("global_writes_enabled")

    def global_llm_enabled(self) -> bool:
        return self.runtime_setting_enabled("global_llm_enabled")

    def set_global_sends_enabled(
        self, enabled: bool, *, actor_id: str, reason: str, now: datetime | None = None,
    ) -> None:
        """Atomic persistent global delivery stop with conservative in-flight policy."""
        now = now or datetime.now(timezone.utc)
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO runtime_settings(key,value,updated_at,actor_id,reason) VALUES('global_sends_enabled',?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at,"
                "actor_id=excluded.actor_id,reason=excluded.reason",
                ("1" if enabled else "0", now.isoformat(), actor_id, reason),
            )
            if not enabled:
                conn.execute(
                    "UPDATE reminders SET status='cancelled',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,"
                    "last_error=? WHERE status IN ('scheduled','retry_wait','claimed')",
                    (f"global_send_stop:{reason}"[:500],),
                )
                self._quarantine_sending(conn, "1=1", (), actor_id, reason or "global_send_stop", now)

    def chat(self, chat_id: str):
        with self.lock:
            return self.conn.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,)).fetchone()

    def list_deadlines(self, chat_id: str) -> list[Deadline]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM deadlines WHERE chat_id=? AND status='active' ORDER BY due_utc", (chat_id,)).fetchall()
        return [Deadline(**dict(r)) for r in rows]

    def get_deadline(self, chat_id: str, deadline_id: str) -> Deadline | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM deadlines WHERE chat_id=? AND id=?", (chat_id, deadline_id)).fetchone()
        return Deadline(**dict(row)) if row else None

    def find_deadlines(self, chat_id: str, query: str) -> list[Deadline]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM deadlines WHERE chat_id=? AND status='active' AND lower(title) LIKE lower(?) ORDER BY due_utc", (chat_id, f"%{query}%")).fetchall()
        return [Deadline(**dict(r)) for r in rows]

    def create_pending(self, chat_id: str, actor_id: str, action: str, payload: dict, now: datetime) -> str:
        pid = uuid.uuid4().hex[:12]
        with self.lock:
            self.conn.execute("INSERT INTO pending VALUES(?,?,?,?,?,?,?,0)", (pid, chat_id, actor_id, action, json.dumps(payload, ensure_ascii=False), now.isoformat(), (now + timedelta(minutes=10)).isoformat()))
            self.conn.commit()
        return pid

    def pending(self, pending_id: str, chat_id: str, actor_id: str, now: datetime):
        with self.lock:
            return self.conn.execute("SELECT * FROM pending WHERE id=? AND chat_id=? AND actor_id=? AND consumed=0 AND expires_at>?", (pending_id, chat_id, actor_id, now.isoformat())).fetchone()

    def acquire_idempotency_lock(self, conn, key: str) -> None:
        # BEGIN IMMEDIATE + process lock already serialize SQLite writers.
        return None

    def pending_for_update(self, conn, pending_id: str, chat_id: str, actor_id: str, now: datetime):
        return conn.execute(
            "SELECT * FROM pending WHERE id=? AND chat_id=? AND actor_id=? AND consumed=0 AND expires_at>?",
            (pending_id, chat_id, actor_id, now.isoformat()),
        ).fetchone()

    def idempotent_record(self, key: str):
        with self.lock:
            row = self.conn.execute("SELECT request_fingerprint,response_json FROM idempotency WHERE key=?", (key,)).fetchone()
        return {"request_fingerprint": row[0], "response": json.loads(row[1])} if row else None

    def audit(self, chat_id: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM audit WHERE chat_id=? ORDER BY occurred_at", (chat_id,)).fetchall()]

    def jobs(self, chat_id: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM reminders WHERE chat_id=? ORDER BY scheduled_for", (chat_id,)).fetchall()]

    # ---- Feature stores used by the Telegram-first product surface. ----

    def get_material(self, chat_id: str, material_id: str) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, material_id)).fetchone()
        return dict(row) if row else None

    def save_material(
        self, chat_id: str, actor_id: str, description: str, url: str,
        canonical_url: str, domain: str, now: datetime,
    ) -> dict:
        material_id = uuid.uuid4().hex[:10]
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO materials(id,chat_id,description,url,canonical_url,domain,author_id,status,created_at,version) "
                "VALUES(?,?,?,?,?,?,?,'active',?,1)",
                (material_id, chat_id, description, url, canonical_url, domain, actor_id, now.isoformat()),
            )
            row = conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, material_id)).fetchone()
        return dict(row)

    def find_material_by_canonical_url(self, chat_id: str, canonical_url: str) -> dict | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM materials WHERE chat_id=? AND canonical_url=? AND status='active'",
                (chat_id, canonical_url),
            ).fetchone()
        return dict(row) if row else None

    def list_materials(self, chat_id: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM materials WHERE chat_id=? AND status='active' ORDER BY created_at DESC", (chat_id,)
            ).fetchall()]

    def search_materials(self, chat_id: str, query: str) -> list[dict]:
        exact = self.get_material(chat_id, query.strip())
        if exact and exact["status"] == "active":
            return [exact]
        pattern = f"%{query.strip()}%"
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM materials WHERE chat_id=? AND status='active' "
                "AND (lower(description) LIKE lower(?) OR lower(domain) LIKE lower(?) OR lower(url) LIKE lower(?)) "
                "ORDER BY created_at DESC",
                (chat_id, pattern, pattern, pattern),
            ).fetchall()]

    # ---- Durable delivery outbox. Claims are leased and safe after restart. ----

    def _delivery_payload(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        payload = json.loads(row["payload_json"] or "{}")
        if row["deadline_id"] != "*":
            deadline = conn.execute(
                "SELECT * FROM deadlines WHERE chat_id=? AND id=?", (row["chat_id"], row["deadline_id"])
            ).fetchone()
            if deadline:
                payload["deadline"] = dict(deadline)
        elif row["deadline_id"] == "*" and row["type"] == "sunday_digest":
            chat = conn.execute("SELECT timezone_id FROM chats WHERE chat_id=?", (row["chat_id"],)).fetchone()
            zone = ZoneInfo(chat["timezone_id"])
            digest_local = datetime.fromisoformat(row["scheduled_for"]).astimezone(zone)
            start_local = (digest_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=7)
            rows = conn.execute(
                "SELECT * FROM deadlines WHERE chat_id=? AND status='active' AND due_utc>=? AND due_utc<? ORDER BY due_utc",
                (row["chat_id"], start_local.astimezone(timezone.utc).isoformat(), end_local.astimezone(timezone.utc).isoformat()),
            ).fetchall()
            payload["deadlines"] = [dict(deadline) for deadline in rows]
        return payload

    def recover_expired_deliveries(self, now: datetime) -> int:
        with self.tx() as conn:
            unstarted = conn.execute(
                "UPDATE reminders SET status='retry_wait',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,"
                "available_at=?,last_error='claim_lease_expired_before_send' "
                "WHERE status='claimed' AND lease_until IS NOT NULL AND lease_until<=?",
                (now.isoformat(), now.isoformat()),
            )
            ambiguous = conn.execute(
                "UPDATE reminders SET status='delivery_unknown',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,"
                "available_at=NULL,last_error='send_lease_expired_after_start' "
                "WHERE status='sending' AND lease_until IS NOT NULL AND lease_until<=?",
                (now.isoformat(),),
            )
        return unstarted.rowcount + ambiguous.rowcount

    def claim_due_deliveries(self, now: datetime, limit: int = 20, lease_seconds: int = 60) -> list[dict]:
        if limit < 1:
            return []
        worker = uuid.uuid4().hex
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self.tx() as conn:
            setting = conn.execute("SELECT value FROM runtime_settings WHERE key='global_sends_enabled'").fetchone()
            if not setting or setting["value"] != "1":
                return []
            conn.execute(
                "UPDATE reminders SET status='retry_wait',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,available_at=?,"
                "last_error='claim_lease_expired_before_send' WHERE status='claimed' AND lease_until IS NOT NULL AND lease_until<=?",
                (now.isoformat(), now.isoformat()),
            )
            conn.execute(
                "UPDATE reminders SET status='delivery_unknown',claimed_by=NULL,claimed_at=NULL,lease_until=NULL,available_at=NULL,"
                "last_error='send_lease_expired_after_start' WHERE status='sending' AND lease_until IS NOT NULL AND lease_until<=?",
                (now.isoformat(),),
            )
            rows = conn.execute(
                "SELECT r.job_key FROM reminders r JOIN chats c ON c.chat_id=r.chat_id "
                "WHERE c.enabled=1 AND r.status IN ('scheduled','retry_wait') "
                "AND r.scheduled_for<=? AND coalesce(r.available_at,r.scheduled_for)<=? "
                "ORDER BY r.scheduled_for,r.job_key LIMIT ?",
                (now.isoformat(), now.isoformat(), int(limit)),
            ).fetchall()
            keys = [row["job_key"] for row in rows]
            for key in keys:
                conn.execute(
                    "UPDATE reminders SET status='claimed',claimed_by=?,claimed_at=?,lease_until=?,attempt_count=attempt_count+1 "
                    "WHERE job_key=? AND status IN ('scheduled','retry_wait')",
                    (worker, now.isoformat(), lease_until, key),
                )
            claimed = [conn.execute("SELECT * FROM reminders WHERE job_key=? AND claimed_by=?", (key, worker)).fetchone() for key in keys]
            output = []
            for row in claimed:
                if not row:
                    continue
                item = dict(row)
                item.update({"id": row["job_key"], "kind": row["type"], "payload": self._delivery_payload(conn, row)})
                output.append(item)
        return output

    def mark_delivery_sending(self, job_key: str, now: datetime) -> bool:
        """Persist that a network request is about to start.

        An expired lease after this transition is ambiguous and must never be
        blindly retried because Telegram may already have accepted the request.
        """
        with self.tx() as conn:
            result = conn.execute(
                "UPDATE reminders SET status='sending',claimed_at=? WHERE job_key=? AND status='claimed' AND lease_until>? "
                "AND EXISTS(SELECT 1 FROM chats c WHERE c.chat_id=reminders.chat_id AND c.enabled=1) "
                "AND EXISTS(SELECT 1 FROM runtime_settings s WHERE s.key='global_sends_enabled' AND s.value='1')",
                (now.isoformat(), job_key, now.isoformat()),
            )
        return result.rowcount == 1

    def mark_delivery_succeeded(self, job_key: str, telegram_message_id: str, now: datetime) -> bool:
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE job_key=?", (job_key,)).fetchone()
            if not row:
                return False
            if row["status"] == "delivered":
                return row["telegram_message_id"] == str(telegram_message_id)
            if row["status"] != "sending":
                return False
            conn.execute(
                "UPDATE reminders SET status='delivered',telegram_message_id=?,delivered_at=?,claimed_by=NULL,"
                "claimed_at=NULL,lease_until=NULL,last_error=NULL,payload_json=CASE WHEN type='call_all' THEN '{}' ELSE payload_json END WHERE job_key=?",
                (str(telegram_message_id), now.isoformat(), job_key),
            )
            if row["type"] == "csat_survey":
                conn.execute(
                    "UPDATE csat_surveys SET sent_at=?,telegram_message_id=? WHERE job_key=?",
                    (now.isoformat(), str(telegram_message_id), job_key),
                )
            conn.execute(
                "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, job_key, row["attempt_count"], now.isoformat(), "success", None, str(telegram_message_id)),
            )
        return True

    def mark_delivery_failed(self, job_key: str, error: str, now: datetime, retryable: bool = True) -> bool:
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE job_key=?", (job_key,)).fetchone()
            if not row or row["status"] != "sending":
                return False
            terminal = not retryable or row["attempt_count"] >= row["max_attempts"]
            delay = min(900, 15 * (2 ** max(0, row["attempt_count"] - 1)))
            status = "failed_permanent" if terminal else "retry_wait"
            available = None if terminal else (now + timedelta(seconds=delay)).isoformat()
            conn.execute(
                "UPDATE reminders SET status=?,available_at=?,claimed_by=NULL,claimed_at=NULL,lease_until=NULL,last_error=? WHERE job_key=?",
                (status, available, error[:500], job_key),
            )
            conn.execute(
                "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, job_key, row["attempt_count"], now.isoformat(), "terminal_failure" if terminal else "retry", error[:500], None),
            )
        return True

    def mark_delivery_unknown(self, job_key: str, error: str, now: datetime) -> bool:
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE job_key=?", (job_key,)).fetchone()
            if not row or row["status"] != "sending":
                return False
            conn.execute(
                "UPDATE reminders SET status='delivery_unknown',available_at=NULL,claimed_by=NULL,claimed_at=NULL,"
                "lease_until=NULL,last_error=? WHERE job_key=?",
                (error[:500], job_key),
            )
            conn.execute(
                "INSERT OR IGNORE INTO delivery_attempts VALUES(?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, job_key, row["attempt_count"], now.isoformat(), "delivery_unknown", error[:500], None),
            )
        return True

    def list_unknown_deliveries(self, limit: int = 100) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT job_key,chat_id,type,scheduled_for,status,attempt_count,last_error,claimed_at,delivered_at "
                "FROM reminders WHERE status='delivery_unknown' ORDER BY scheduled_for,job_key LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def inspect_delivery(self, job_key: str) -> dict | None:
        """Return operator-safe delivery metadata; payload/content is excluded."""
        with self.lock:
            row = self.conn.execute(
                "SELECT job_key,chat_id,deadline_id,type,scheduled_for,status,attempt_count,max_attempts,available_at,"
                "claimed_at,lease_until,last_error,telegram_message_id,delivered_at FROM reminders WHERE job_key=?", (job_key,)
            ).fetchone()
            attempts = self.conn.execute(
                "SELECT attempt_no,attempted_at,result,error,telegram_message_id FROM delivery_attempts "
                "WHERE job_key=? ORDER BY attempt_no", (job_key,)
            ).fetchall() if row else []
        return {**dict(row), "attempts": [dict(item) for item in attempts]} if row else None

    def resolve_delivery_unknown(
        self, job_key: str, decision: str, actor_id: str, now: datetime, *, reason: str = "",
    ) -> bool:
        """Audited operator decision: retry deliberately or close as permanent.

        This is never called automatically. A retry reuses the same job_key.
        """
        if decision not in {"retry", "failed_permanent"}:
            raise ValueError("invalid_operator_decision")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_and_reason_required")
        target = "retry_wait" if decision == "retry" else "failed_permanent"
        available = now.isoformat() if decision == "retry" else None
        with self.tx() as conn:
            row = conn.execute("SELECT chat_id FROM reminders WHERE job_key=? AND status='delivery_unknown'", (job_key,)).fetchone()
            if not row:
                return False
            if decision == "retry":
                chat = conn.execute("SELECT enabled FROM chats WHERE chat_id=?", (row["chat_id"],)).fetchone()
                setting = conn.execute("SELECT value FROM runtime_settings WHERE key='global_sends_enabled'").fetchone()
                if not chat or not chat["enabled"] or not setting or setting["value"] != "1":
                    raise ValueError("scheduled_sends_stopped")
            result = conn.execute(
                "UPDATE reminders SET status=?,available_at=?,last_error=? WHERE job_key=? AND status='delivery_unknown'",
                (target, available, f"operator:{actor_id}:{decision}:{reason}"[:500], job_key),
            )
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, row["chat_id"], actor_id, "resolve_delivery_unknown", job_key, None,
                 json.dumps({"decision": decision, "reason": reason}, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()),
            )
        return result.rowcount == 1
