from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gosha.models import Actor, Role
from gosha.models import Intent, ProviderResult
from gosha.postgres_store import PostgresStore, _postgres_sql
from gosha.service import GoshaService
from gosha.store import Store
from gosha.store_factory import build_store
from gosha.time_rules import normalize_due, reminder_schedule
from gosha.url_rules import URLRuleError, normalize_material_url


NOW = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)


@pytest.fixture
def app():
    store = Store()
    store.add_chat("chat-a", "Europe/Moscow")
    store.add_chat("chat-b", "Europe/Moscow")
    return GoshaService(store)


def confirm_material(app, chat="chat-a", actor=Actor("u1"), url="https://Example.org:443/guide#intro", description="ML guide"):
    preview = app.preview_material(chat, actor, url, description, NOW)
    assert preview.status == "preview"
    return app.confirm(chat, actor, preview.data["pending_id"], f"mat:{chat}:{actor.user_id}:{url}", NOW)


@pytest.mark.parametrize("date", ["2026-08-17", "2026-08-18", "2026-08-21", "2026-08-23"])
def test_release_cadence_is_only_t24_and_sunday_digest(date):
    local, _, _ = normalize_due(date, "12:00", "Europe/Moscow", NOW)
    assert {kind for kind, _ in reminder_schedule(local, "Europe/Moscow", NOW.isoformat())} == {"t24", "sunday_digest"}


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)", "ftp://example.org/x", "https://user:pass@example.org/x",
        "https://example.org/a https://evil.test/b", "https://example.org\\@evil.test/x",
        "https://example.org:99999/x", "https://exa mple.org/x", "https://example.org/\nnext",
        "https:///missing-host",
    ],
)
def test_material_url_adversarial_inputs_fail_closed(url):
    with pytest.raises(URLRuleError):
        normalize_material_url(url)


def test_url_canonicalization_is_stable_and_does_not_fetch():
    result = normalize_material_url("HTTPS://Example.ORG:443/guide?q=1#section")
    assert result.display_url == "https://example.org/guide?q=1#section"
    assert result.canonical_url == "https://example.org/guide?q=1"
    assert result.domain == "example.org"


def test_material_preview_confirm_and_chat_isolation(app):
    preview = app.preview_material("chat-a", Actor("u1"), "https://example.org/guide", "Guide", NOW)
    assert preview.status == "preview" and preview.data["content_fetched"] is False
    assert app.store.list_materials("chat-a") == []
    wrong = app.confirm("chat-b", Actor("u1"), preview.data["pending_id"], "wrong-chat", NOW)
    assert wrong.status == "rejected" and app.store.list_materials("chat-b") == []
    result = app.confirm("chat-a", Actor("u1"), preview.data["pending_id"], "right-chat", NOW)
    assert result.status == "success"
    assert app.list_materials("chat-a", "Guide").data["materials"][0]["url"] == "https://example.org/guide"
    assert app.list_materials("chat-b", "Guide").status == "not_found"


def test_material_duplicate_is_by_canonical_url_in_same_chat(app):
    first = confirm_material(app)
    assert first.status == "success"
    duplicate = app.preview_material("chat-a", Actor("u2"), "https://example.org/guide#other", "Other", NOW)
    assert duplicate.status == "possible_duplicate"
    assert app.preview_material("chat-b", Actor("u2"), "https://example.org/guide#other", "Other", NOW).status == "preview"


def test_material_correction_requires_role_and_rejects_stale_preview(app):
    material = confirm_material(app).data["material"]
    assert app.preview_material_correct("chat-a", Actor("u2"), material["id"], description="new", now=NOW).status == "forbidden"
    steward = Actor("s", Role.STEWARD)
    one = app.preview_material_correct("chat-a", steward, material["id"], description="Version one", now=NOW)
    stale = app.preview_material_correct("chat-a", steward, material["id"], description="Version two", now=NOW)
    assert app.confirm("chat-a", steward, one.data["pending_id"], "one", NOW).status == "success"
    assert app.confirm("chat-a", steward, stale.data["pending_id"], "stale", NOW).status == "stale_preview"
    assert app.store.audit("chat-a")[-1]["action"] == "material_correct"


def test_material_deactivation_and_recent_author_cancel_are_isolated(app):
    first = confirm_material(app).data["material"]
    steward = Actor("s", Role.STEWARD)
    assert app.preview_material_deactivate("chat-b", steward, first["id"], NOW).status == "not_found"
    preview = app.preview_material_deactivate("chat-a", steward, first["id"], NOW)
    assert app.confirm("chat-a", steward, preview.data["pending_id"], "deactivate-material", NOW).status == "success"
    assert app.list_materials("chat-a").status == "not_found"
    second = confirm_material(app, url="https://example.org/second", description="Second").data["material"]
    cancelled = app.cancel_last_material("chat-a", Actor("u1"), NOW + timedelta(minutes=5))
    assert cancelled.status == "success" and cancelled.data["material_id"] == second["id"]
    assert app.list_materials("chat-a").status == "not_found"


def test_material_search_never_invents_or_crosses_chat(app):
    saved = confirm_material(app, description="guide to model evaluation").data["material"]
    assert app.list_materials("chat-a", "model evaluation").data["materials"][0]["url"] == saved["url"]
    missing = app.list_materials("chat-a", "invent a different link")
    assert missing.status == "not_found" and missing.data["materials"] == []
    assert app.list_materials("chat-b", saved["id"]).status == "not_found"


def test_material_write_requires_literal_url_from_user_text():
    class HallucinatingProvider:
        def parse(self, _text):
            return ProviderResult(Intent.MATERIAL_SAVE, {"url": "https://invented.example/x", "description": "X"}, "faulty")

    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store, HallucinatingProvider())
    result = app.handle("chat-a", Actor("u1"), "@gosha сохрани тот гайд", now=NOW)
    assert result.status == "clarification" and store.list_materials("chat-a") == []


def test_cancel_pending_is_owner_and_chat_bound(app):
    preview = app.preview_material("chat-a", Actor("u1"), "https://example.org/x", "X", NOW)
    assert app.cancel_pending("chat-a", Actor("attacker"), preview.data["pending_id"], NOW).status == "rejected"
    assert app.cancel_pending("chat-b", Actor("u1"), preview.data["pending_id"], NOW).status == "rejected"
    assert app.cancel_pending("chat-a", Actor("u1"), preview.data["pending_id"], NOW).status == "cancelled"
    assert app.confirm("chat-a", Actor("u1"), preview.data["pending_id"], "after-cancel", NOW).status == "rejected"


def test_material_parallel_confirm_writes_once(app):
    p1 = app.preview_material("chat-a", Actor("u1"), "https://example.org/race", "Race", NOW)
    p2 = app.preview_material("chat-a", Actor("u2"), "https://example.org/race#fragment", "Race 2", NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: app.confirm("chat-a", *args, now=NOW), [
            (Actor("u1"), p1.data["pending_id"], "race-1"),
            (Actor("u2"), p2.data["pending_id"], "race-2"),
        ]))
    assert sorted(result.status for result in results) == ["possible_duplicate", "success"]
    assert len(app.store.list_materials("chat-a")) == 1


def due_job(store: Store, key="job-1"):
    store.add_chat("chat-a", "Europe/Moscow")
    with store.lock:
        store.conn.execute(
            "INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,available_at) VALUES(?,?,?,?,?,'scheduled',?)",
            (key, "chat-a", "deadline-1", "t24", NOW.isoformat(), NOW.isoformat()),
        )
        store.conn.commit()


def test_outbox_retry_reuses_job_and_delivers_once():
    store = Store(); due_job(store)
    claim = store.claim_due_deliveries(NOW)[0]
    assert claim["status"] == "claimed" and store.mark_delivery_sending(claim["job_key"], NOW)
    assert store.mark_delivery_failed(claim["job_key"], "telegram_500", NOW, retryable=True)
    assert store.jobs("chat-a")[0]["status"] == "retry_wait"
    retry_at = NOW + timedelta(seconds=16)
    again = store.claim_due_deliveries(retry_at)[0]
    assert again["job_key"] == claim["job_key"] and again["attempt_count"] == 2
    assert store.mark_delivery_sending(again["job_key"], retry_at)
    assert store.mark_delivery_succeeded(again["job_key"], "tg-42", retry_at)
    assert store.mark_delivery_succeeded(again["job_key"], "tg-42", retry_at)
    assert store.claim_due_deliveries(retry_at + timedelta(hours=1)) == []


def test_ambiguous_delivery_is_quarantined_without_blind_retry():
    store = Store(); due_job(store)
    job = store.claim_due_deliveries(NOW, lease_seconds=5)[0]
    assert store.mark_delivery_sending(job["job_key"], NOW)
    store.recover_expired_deliveries(NOW + timedelta(seconds=6))
    assert store.jobs("chat-a")[0]["status"] == "delivery_unknown"
    assert store.claim_due_deliveries(NOW + timedelta(days=1)) == []
    assert store.resolve_delivery_unknown(job["job_key"], "retry", "operator-1", NOW + timedelta(days=1), reason="verified not delivered")
    assert store.claim_due_deliveries(NOW + timedelta(days=1))[0]["job_key"] == job["job_key"]


def test_expired_claim_before_send_is_safe_to_retry():
    store = Store(); due_job(store)
    job = store.claim_due_deliveries(NOW, lease_seconds=5)[0]
    assert job["status"] == "claimed"
    store.recover_expired_deliveries(NOW + timedelta(seconds=6))
    assert store.jobs("chat-a")[0]["status"] == "retry_wait"
    assert store.claim_due_deliveries(NOW + timedelta(seconds=6))[0]["job_key"] == job["job_key"]


def test_concurrent_outbox_claim_has_single_winner():
    store = Store(); due_job(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim_due_deliveries(NOW), range(2)))
    assert sum(len(items) for items in claims) == 1


def test_postgres_query_compat_and_migration_contract():
    translated = _postgres_sql("INSERT OR IGNORE INTO reminders(job_key) VALUES(?)")
    assert translated == "INSERT INTO reminders(job_key) VALUES(%s) ON CONFLICT DO NOTHING"
    migration = Path("migrations/postgres/001_initial.sql").read_text(encoding="utf-8")
    for table in ("deadlines", "materials", "pending", "audit", "reminders", "delivery_attempts", "idempotency"):
        assert f"TABLE IF NOT EXISTS {table}" in migration
    assert "UNIQUE(chat_id,canonical_url)" in migration


def test_store_factory_does_not_silently_downgrade_bad_database_url():
    with pytest.raises(ValueError):
        build_store(database_url="sqlite:///prod.db")


def test_monthly_csat_jobs_are_per_chat_period_and_timezone_idempotent():
    store = Store()
    store.add_chat("chat-moscow", "Europe/Moscow")
    store.add_chat("chat-la", "America/Los_Angeles")

    assert store.ensure_monthly_csat(NOW) == 2
    assert store.ensure_monthly_csat(NOW + timedelta(days=10)) == 0
    moscow_job = store.jobs("chat-moscow")[0]
    la_job = store.jobs("chat-la")[0]
    assert moscow_job["type"] == la_job["type"] == "csat_survey"
    assert datetime.fromisoformat(moscow_job["scheduled_for"]).hour == 9  # 12:00 Moscow in July
    assert datetime.fromisoformat(la_job["scheduled_for"]).hour == 19  # 12:00 Los Angeles in July

    october_schedule = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)
    assert store.ensure_monthly_csat(october_schedule) == 2
    assert len(store.jobs("chat-moscow")) == len(store.jobs("chat-la")) == 2


@pytest.mark.skipif(not os.environ.get("GOSHA_TEST_POSTGRES_DSN"), reason="set GOSHA_TEST_POSTGRES_DSN for live parity")
def test_postgres_material_and_outbox_smoke():
    store = PostgresStore(os.environ["GOSHA_TEST_POSTGRES_DSN"])
    chat = f"test-{NOW.timestamp()}"
    store.add_chat(chat, "Europe/Moscow")
    app = GoshaService(store)
    preview = app.preview_material(chat, Actor("u1"), "https://example.org/pg", "PG", NOW)
    assert app.confirm(chat, Actor("u1"), preview.data["pending_id"], "pg-material", NOW).status == "success"
    assert len(store.list_materials(chat)) == 1
    # Two independent connections prove same-key confirmation convergence,
    # rather than relying on SQLite's process lock.
    store2 = PostgresStore(os.environ["GOSHA_TEST_POSTGRES_DSN"])
    app2 = GoshaService(store2)
    deadline_preview = app.handle(chat, Actor("u2"), "@gosha добавь дедлайн PG race 2026-09-10 10:00", now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda service: service.confirm(chat, Actor("u2"), deadline_preview.data["pending_id"], "pg-same-confirm", NOW),
            (app, app2),
        ))
    assert all(result.status == "success" for result in results)
    assert results[0].data["deadline"]["id"] == results[1].data["deadline"]["id"]
    assert len([d for d in store.list_deadlines(chat) if d.title == "PG race"]) == 1
    stopped_preview = app.handle(chat, Actor("u3"), "@gosha добавь дедлайн PG stop 2026-09-11 11:00", now=NOW)
    store2.set_runtime_setting("global_writes_enabled", False, actor_id="pg-operator", reason="PG race retest", now=NOW)
    assert app.confirm(chat, Actor("u3"), stopped_preview.data["pending_id"], "pg-stop-confirm", NOW).status == "stopped"
    store3 = PostgresStore(os.environ["GOSHA_TEST_POSTGRES_DSN"])
    assert store3.global_writes_enabled() is False
    store3.set_runtime_setting("global_writes_enabled", True, actor_id="pg-operator", reason="PG retest cleanup", now=NOW)
    store3.close()
    store2.close()
    store.close()
