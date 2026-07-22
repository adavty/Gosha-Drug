from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest

from gosha.models import Actor
from gosha.config import telemetry_hmac_key
from gosha.operator_cli import main as operator_main
from gosha.postgres_store import PostgresStore
from gosha.runtime_check import main as runtime_check_main
from gosha.service import GoshaService
from gosha.store import REMINDER_MIGRATIONS, Store


NOW = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)


def make_legacy_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE reminders(
          job_key TEXT PRIMARY KEY, chat_id TEXT NOT NULL, deadline_id TEXT NOT NULL,
          type TEXT NOT NULL, scheduled_for TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled'
        );
        INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status)
        VALUES('legacy-job','legacy-chat','legacy-deadline','t24','2026-08-19T18:00:00+00:00','scheduled');
        """
    )
    conn.commit(); conn.close()


def test_legacy_sqlite_upgrade_preserves_records_is_idempotent_and_healthy(tmp_path):
    path = tmp_path / "legacy.db"
    make_legacy_sqlite(path)

    for _ in range(2):
        store = Store(path)
        row = store.conn.execute("SELECT * FROM reminders WHERE job_key='legacy-job'").fetchone()
        assert row["scheduled_for"] == "2026-08-19T18:00:00+00:00"
        assert row["available_at"] == row["scheduled_for"]
        columns = {item[1] for item in store.conn.execute("PRAGMA table_info(reminders)")}
        assert set(REMINDER_MIGRATIONS) <= columns
        indexes = {item[1] for item in store.conn.execute("PRAGMA index_list(reminders)")}
        assert "idx_reminders_due" in indexes
        assert store.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        store.close()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]
    entrypoint = Path(sys.executable).with_name("gosha-server")
    command = [str(entrypoint), "--db", str(path), "--host", "127.0.0.1", "--port", str(port)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.25) as response:
                    assert response.status == 200
                    assert json.loads(response.read())["status"] == "ok"
                    break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    stdout, stderr = process.communicate(timeout=1)
                    pytest.fail(f"gosha-server failed to become healthy: {stdout}\n{stderr}")
                time.sleep(0.05)
    finally:
        process.terminate()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=2)


def test_claim_ledger_ids_are_unique():
    ledger = Path(__file__).parents[1] / "submission" / "claim-ledger.md"
    if not ledger.exists():
        # The allowlisted public export intentionally omits the private JMLC
        # evidence package; absence is expected only when the whole folder is absent.
        assert not ledger.parent.exists()
        return
    ids = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            claim_id = line.split("|", 2)[1].strip()
            if claim_id not in {"ID", "---"} and claim_id:
                ids.append(claim_id)
    duplicates = sorted({claim_id for claim_id in ids if ids.count(claim_id) > 1})
    assert duplicates == []


def test_live_telemetry_key_requires_secret_and_supports_mounted_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GOSHA_TELEMETRY_HMAC_KEY", raising=False)
    monkeypatch.delenv("GOSHA_TELEMETRY_HMAC_KEY_FILE", raising=False)
    with pytest.raises(ValueError, match="deployment-specific"):
        telemetry_hmac_key(required=True)
    secret = tmp_path / "telemetry.key"
    secret.write_text("x" * 32, encoding="utf-8")
    monkeypatch.setenv("GOSHA_TELEMETRY_HMAC_KEY_FILE", str(secret))
    assert telemetry_hmac_key(required=True) == "x" * 32


def add_due_job(store: Store, key: str = "job-1", chat: str = "chat-a") -> None:
    if not store.chat(chat):
        store.add_chat(chat, "Europe/Moscow")
    with store.lock:
        store.conn.execute(
            "INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,available_at,payload_json) "
            "VALUES(?,?,?,?,?,'scheduled',?,'{}')",
            (key, chat, "deadline-1", "t24", NOW.isoformat(), NOW.isoformat()),
        )
        store.conn.commit()


def test_per_chat_stop_before_claim_cancels_and_excludes_queue():
    store = Store(); add_due_job(store)
    store.set_chat_enabled("chat-a", False, actor_id="admin", reason="privacy request", now=NOW)
    assert store.jobs("chat-a")[0]["status"] == "cancelled"
    assert store.claim_due_deliveries(NOW + timedelta(minutes=1)) == []


def test_per_chat_stop_after_claim_before_send_fails_closed():
    store = Store(); add_due_job(store)
    job = store.claim_due_deliveries(NOW)[0]
    store.set_chat_enabled("chat-a", False, actor_id="admin", reason="stop before send", now=NOW)
    assert store.jobs("chat-a")[0]["status"] == "cancelled"
    assert store.mark_delivery_sending(job["job_key"], NOW) is False


def test_stop_during_sending_becomes_unknown_incident_not_retry():
    store = Store(); add_due_job(store)
    job = store.claim_due_deliveries(NOW)[0]
    assert store.mark_delivery_sending(job["job_key"], NOW)
    store.set_chat_enabled("chat-a", False, actor_id="admin", reason="incident", now=NOW)
    row = store.inspect_delivery(job["job_key"])
    assert row["status"] == "delivery_unknown"
    assert store.claim_due_deliveries(NOW + timedelta(days=1)) == []
    assert any(item["action"] == "scheduled_send_stop_unknown" for item in store.audit("chat-a"))


def test_global_stop_persists_restart_and_reenable_does_not_resurrect(tmp_path):
    path = tmp_path / "state.db"
    store = Store(path); add_due_job(store)
    store.set_global_sends_enabled(False, actor_id="operator", reason="INC-1", now=NOW)
    assert store.global_sends_enabled() is False
    store.close()
    restarted = Store(path)
    assert restarted.global_sends_enabled() is False
    assert restarted.claim_due_deliveries(NOW + timedelta(days=1)) == []
    restarted.set_global_sends_enabled(True, actor_id="operator", reason="reviewed", now=NOW + timedelta(days=1))
    assert restarted.global_sends_enabled() is True
    assert restarted.jobs("chat-a")[0]["status"] == "cancelled"
    assert restarted.claim_due_deliveries(NOW + timedelta(days=1)) == []


def test_write_and_llm_stops_persist_restart_and_are_independently_reenabled(tmp_path):
    path = tmp_path / "controls.db"
    store = Store(path); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store)
    preview = app.handle("chat-a", Actor("u1"), "@gosha добавь дедлайн отчёт 2026-08-20 18:00", now=NOW)
    store.set_runtime_setting("global_writes_enabled", False, actor_id="operator", reason="INC-W", now=NOW)
    store.set_runtime_setting("global_llm_enabled", False, actor_id="operator", reason="INC-L", now=NOW)
    store.close()

    restarted = Store(path)
    assert restarted.global_writes_enabled() is False
    assert restarted.global_llm_enabled() is False
    assert GoshaService(restarted).confirm("chat-a", Actor("u1"), preview.data["pending_id"], "after-restart", NOW).status == "stopped"
    assert GoshaService(restarted).handle("chat-a", Actor("u2"), "@gosha покажи дедлайны", now=NOW).status == "ok"
    audit = restarted.audit("__global__")
    assert {row["action"] for row in audit} >= {"global_writes_enabled_changed", "global_llm_enabled_changed"}
    restarted.set_runtime_setting("global_writes_enabled", True, actor_id="operator", reason="reviewed", now=NOW)
    assert restarted.global_llm_enabled() is False and restarted.global_writes_enabled() is True
    restarted.close()


def test_missing_write_and_llm_settings_fail_closed():
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    with store.lock:
        store.conn.execute("DELETE FROM runtime_settings WHERE key IN ('global_writes_enabled','global_llm_enabled')")
        store.conn.commit()
    app = GoshaService(store)
    preview = app.handle("chat-a", Actor("u1"), "/deadline_add Отчёт | 2026-08-20 | 18:00", entry_point="command", now=NOW)
    # Missing LLM gate uses deterministic commands; missing write gate blocks commit.
    assert preview.status == "preview"
    assert app.confirm("chat-a", Actor("u1"), preview.data["pending_id"], "missing", NOW).status == "stopped"


def test_llm_off_serializes_before_provider_call():
    class SpyProvider:
        def parse(self, _text):
            raise AssertionError("provider must not be called while durable LLM-off is active")

    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    store.set_runtime_setting("global_llm_enabled", False, actor_id="operator", reason="provider incident", now=NOW)
    app = GoshaService(store, SpyProvider())
    assert app.handle("chat-a", Actor("u1"), "/deadlines", entry_point="command", now=NOW).status == "ok"


def test_deadline_created_during_global_stop_never_queues_for_later():
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    store.set_global_sends_enabled(False, actor_id="operator", reason="maintenance", now=NOW)
    app = GoshaService(store)
    preview = app.handle("chat-a", Actor("u1"), "@gosha добавь дедлайн отчёт 2026-08-20 18:00", now=NOW)
    assert app.confirm("chat-a", Actor("u1"), preview.data["pending_id"], "during-stop", NOW).status == "success"
    assert {row["status"] for row in store.jobs("chat-a")} == {"cancelled"}
    store.set_global_sends_enabled(True, actor_id="operator", reason="maintenance done", now=NOW)
    assert store.claim_due_deliveries(datetime(2026, 8, 20, tzinfo=timezone.utc)) == []


def test_missing_global_setting_fails_closed_for_claim_and_send():
    store = Store(); add_due_job(store)
    with store.lock:
        store.conn.execute("DELETE FROM runtime_settings WHERE key='global_sends_enabled'"); store.conn.commit()
    assert store.global_sends_enabled() is False
    assert store.claim_due_deliveries(NOW) == []
    with store.lock:
        store.conn.execute("UPDATE reminders SET status='claimed',lease_until=? WHERE job_key='job-1'", ((NOW + timedelta(minutes=1)).isoformat(),)); store.conn.commit()
    assert store.mark_delivery_sending("job-1", NOW) is False


def make_unknown(path: Path) -> str:
    store = Store(path); add_due_job(store)
    job = store.claim_due_deliveries(NOW)[0]
    store.mark_delivery_sending(job["job_key"], NOW)
    store.mark_delivery_unknown(job["job_key"], "timeout_after_send", NOW)
    store.close()
    return job["job_key"]


def test_operator_cli_lists_inspects_and_audits_resolution(tmp_path, capsys):
    path = tmp_path / "operator.db"; key = make_unknown(path)
    assert operator_main(["--db", str(path), "delivery-unknown-list"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["job_key"] == key
    assert operator_main(["--db", str(path), "delivery-inspect", key]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["status"] == "delivery_unknown" and "payload_json" not in inspected
    assert operator_main([
        "--db", str(path), "delivery-unknown-resolve", key, "--decision", "failed_permanent",
        "--actor", "operator-7", "--reason", "acceptance cannot be disproved INC-7",
    ]) == 0
    capsys.readouterr()
    store = Store(path)
    assert store.inspect_delivery(key)["status"] == "failed_permanent"
    audit = [row for row in store.audit("chat-a") if row["action"] == "resolve_delivery_unknown"][-1]
    assert json.loads(audit["after_json"])["reason"] == "acceptance cannot be disproved INC-7"
    store.close()
    assert operator_main([
        "--db", str(path), "delivery-unknown-resolve", key, "--decision", "retry",
        "--actor", "operator-7", "--reason", "second try",
    ]) == 2


def test_operator_cli_controls_durable_writes_and_llm(tmp_path, capsys):
    path = tmp_path / "operator-controls.db"
    Store(path).close()
    for command, key in (("writes-global", "global_writes_enabled"), ("llm-global", "global_llm_enabled")):
        assert operator_main([
            "--db", str(path), command, "--enabled", "off", "--actor", "operator-9", "--reason", "INC-9",
        ]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["control"] == key and output["enabled"] is False
    restarted = Store(path)
    assert restarted.global_writes_enabled() is False and restarted.global_llm_enabled() is False
    assert {row["action"] for row in restarted.audit("__global__")} >= {
        "global_writes_enabled_changed", "global_llm_enabled_changed",
    }
    restarted.close()


def test_telemetry_uses_deployment_keyed_hmac_without_raw_ids():
    def event_keys(key: str):
        store = Store(); store.add_chat("chat-raw-123", "Europe/Moscow")
        app = GoshaService(store, telemetry_hmac_key=key)
        app.handle("chat-raw-123", Actor("user-raw-456"), "обычное сообщение", entry_point="ordinary", now=NOW)
        row = dict(store.conn.execute("SELECT * FROM events").fetchone())
        serialized = json.dumps(row, ensure_ascii=False)
        assert "chat-raw-123" not in serialized and "user-raw-456" not in serialized
        return row["chat_key"], row["user_key"]

    assert event_keys("deployment-A") != event_keys("deployment-B")


def test_postgres_failed_migration_rolls_back_statement_and_marker(tmp_path, monkeypatch):
    migration = tmp_path / "001_broken.sql"
    migration.write_text("CREATE TABLE partial_state(id INT); BROKEN;", encoding="utf-8")
    monkeypatch.setenv("GOSHA_MIGRATIONS_DIR", str(tmp_path))

    class FakeResult:
        def __init__(self, row=None): self.row = row
        def fetchone(self): return self.row

    class FakeRaw:
        def __init__(self): self.markers = set(); self.partial_state = False
        @contextmanager
        def transaction(self):
            snapshot = (set(self.markers), self.partial_state)
            try: yield
            except Exception:
                self.markers, self.partial_state = snapshot
                raise
        def execute(self, sql, params=()):
            if sql.startswith("SELECT version"):
                return FakeResult({"version": params[0]} if params[0] in self.markers else None)
            if sql.startswith("INSERT INTO schema_migrations"):
                self.markers.add(params[0]); return FakeResult()
            if "partial_state" in sql:
                self.partial_state = True
                if "BROKEN" in sql: raise RuntimeError("migration_failed")
            return FakeResult()

    raw = FakeRaw()
    store = object.__new__(PostgresStore)
    store.lock = RLock(); store.conn = SimpleNamespace(raw=raw)
    with pytest.raises(RuntimeError, match="migration_failed"):
        store.apply_migrations()
    assert raw.partial_state is False and raw.markers == set()


def test_runtime_config_validation_needs_no_telegram_token(capsys):
    assert runtime_check_main([]) == 0
    assert "storage=sqlite local_only=1" in capsys.readouterr().out


def test_runtime_postgres_check_requires_applied_migration_marker(monkeypatch, capsys):
    class FakeConnection:
        def __init__(self, versions):
            self.versions = versions

        def execute(self, sql, _params=()):
            if "SELECT 1" in sql:
                return SimpleNamespace(fetchone=lambda: {"ok": 1})
            if "schema_migrations" in sql:
                return SimpleNamespace(fetchall=lambda: [{"version": value} for value in self.versions])
            raise AssertionError(sql)

    class FakeStore:
        def __init__(self, versions):
            self.conn = FakeConnection(versions)

        def close(self):
            pass

    monkeypatch.setattr("gosha.runtime_check.build_store", lambda **_kwargs: FakeStore(["001_initial.sql"]))
    assert runtime_check_main(["--database-url", "postgresql://example", "--require-postgres"]) == 0
    assert "migrations=ok count=1" in capsys.readouterr().out

    monkeypatch.setattr("gosha.runtime_check.build_store", lambda **_kwargs: FakeStore([]))
    with pytest.raises(RuntimeError, match="postgres_migrations_not_applied"):
        runtime_check_main(["--database-url", "postgresql://example", "--require-postgres"])


def test_compose_declares_postgres_bot_migrations_and_persistent_state():
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777" in compose
    assert "condition: service_healthy" in compose
    assert "gosha-runtime-check" in compose and "gosha-telegram" in compose
    assert "postgres-data:" in compose and "telegram-state:" in compose
    assert "TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}" in compose
    assert 'ports: ["127.0.0.1:8080:8080"]' in compose
    assert "permissions:\n  contents: read" in workflow
    assert "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5" in workflow
    assert "python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de" in dockerfile
    assert "'.[postgres]'" in dockerfile and "COPY migrations ./migrations" in dockerfile
