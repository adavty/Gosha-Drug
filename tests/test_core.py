from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from gosha.evaluation import evaluate
from gosha.config import build_provider
from gosha.models import Actor, ProviderResult, ProviderUsage, Intent, Role
from gosha.provider import OfflineProvider, OpenAICompatibleProvider, ProviderError
from gosha.service import GoshaService
from gosha.server import Handler
from gosha.store import Store
from gosha.time_rules import TimeRuleError, normalize_due, reminder_schedule, resolve_user_dates


NOW = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)


@pytest.fixture
def app():
    store = Store(); store.add_chat("chat-a", "Europe/Moscow"); store.add_chat("chat-b", "Europe/Moscow")
    return GoshaService(store)


def preview(app, chat="chat-a", actor=Actor("u1")):
    return app.handle(chat, actor, "@gosha добавь дедлайн презентация 2026-08-20 18:00", now=NOW)


def create(app, chat="chat-a", actor=Actor("u1")):
    p = preview(app, chat, actor)
    return app.confirm(chat, actor, p.data["pending_id"], f"key:{chat}:{actor.user_id}", NOW)


def test_create_requires_preview_and_confirm(app):
    p = preview(app); assert p.status == "preview"; assert app.store.list_deadlines("chat-a") == []
    c = app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "k1", NOW); assert c.status == "success"; assert len(app.store.list_deadlines("chat-a")) == 1


def test_confirmation_bound_to_actor(app):
    p = preview(app); r = app.confirm("chat-a", Actor("attacker"), p.data["pending_id"], "k", NOW); assert r.status == "rejected"; assert not app.store.list_deadlines("chat-a")


def test_confirmation_bound_to_chat(app):
    p = preview(app); r = app.confirm("chat-b", Actor("u1"), p.data["pending_id"], "k", NOW); assert r.status == "rejected"; assert not app.store.list_deadlines("chat-b")


def test_confirmation_idempotent(app):
    p = preview(app); one = app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "same", NOW); two = app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "same", NOW); assert one.to_dict() == two.to_dict(); assert len(app.store.list_deadlines("chat-a")) == 1


def test_idempotency_cache_cannot_leak_across_chat(app):
    p = preview(app); app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "same", NOW)
    other = app.confirm("chat-b", Actor("u1"), p.data["pending_id"], "same", NOW)
    assert other.status == "rejected" and "deadline" not in other.data


def test_cross_chat_list_isolated(app):
    create(app); r = app.handle("chat-b", Actor("u2"), "@gosha покажи дедлайны", now=NOW); assert r.data["deadlines"] == []


def test_question_by_id_is_grounded_and_chat_isolated(app):
    d = create(app).data["deadline"]
    r = app.handle("chat-a", Actor("u2"), f"@gosha когда дедлайн {d['id']}", now=NOW)
    assert r.status == "ok" and r.data["deadline"]["due_utc"] == d["due_utc"]
    assert app.handle("chat-b", Actor("u2"), f"@gosha когда дедлайн {d['id']}", now=NOW).status == "not_found"


def test_duplicate_is_not_written(app):
    create(app); r = preview(app)
    assert r.status == "possible_duplicate" and len(app.store.list_deadlines("chat-a")) == 1


def test_cross_chat_change_rejected(app):
    d = create(app).data["deadline"]; steward = Actor("s", Role.STEWARD)
    r = app.handle("chat-b", steward, f"@gosha деактивируй {d['id']}", now=NOW); assert r.status == "not_found"; assert app.store.get_deadline("chat-a", d["id"]).status == "active"


def test_member_cannot_deactivate(app):
    d = create(app).data["deadline"]; r = app.handle("chat-a", Actor("u2"), f"@gosha деактивируй {d['id']}", now=NOW); assert r.status == "forbidden"


def test_steward_deactivate_requires_confirm(app):
    d = create(app).data["deadline"]; steward = Actor("s", Role.STEWARD)
    p = app.handle("chat-a", steward, f"@gosha деактивируй {d['id']}", now=NOW); assert app.store.get_deadline("chat-a", d["id"]).status == "active"
    app.confirm("chat-a", steward, p.data["pending_id"], "deactivate", NOW); assert app.store.get_deadline("chat-a", d["id"]).status == "inactive"
    assert all(j["status"] == "cancelled" for j in app.store.jobs("chat-a") if j["type"] == "t24")


def test_correction_reschedules_jobs(app):
    d = create(app).data["deadline"]; steward = Actor("s", Role.STEWARD)
    p = app.handle("chat-a", steward, f"@gosha исправь {d['id']} на 2026-09-01 10:00", now=NOW)
    r = app.confirm("chat-a", steward, p.data["pending_id"], "edit", NOW); assert r.data["deadline"]["due_local"].startswith("2026-09-01T10:00"); assert len([j for j in app.store.jobs("chat-a") if j["status"] == "scheduled"]) == 2


def _create_named_deadline(app, title, date="2026-08-20", *, chat="chat-a"):
    actor = Actor("author")
    preview_result = app.handle(chat, actor, f"/deadline_add {title} | {date} | 18:00", entry_point="command", now=NOW)
    assert preview_result.status == "preview"
    return app.confirm(chat, actor, preview_result.data["pending_id"], f"create:{chat}:{title}:{date}", NOW).data["deadline"]


def test_admin_can_correct_unique_deadline_by_grounded_title(app):
    deadline = _create_named_deadline(app, "Загрузка презентации питча")

    class ByTitleProvider:
        def parse(self, _text):
            return ProviderResult(Intent.CORRECT, {
                "deadline_id": None,
                "target_title": "загрузка презентации питча",
                "target_evidence": "загрузке презентации питча",
                "date": "22 июля", "date_evidence": "22 июля",
                "time": "23:59", "time_evidence": "23:59",
            }, "stub")

    app.provider = ByTitleProvider()
    result = app.handle(
        "chat-a", Actor("admin", Role.ADMIN),
        "@gosha обнови дедлайн по загрузке презентации питча, там новый дедлайн 22 июля в 23:59",
        now=NOW,
    )
    assert result.status == "preview"
    assert result.data["deadline_id"] == deadline["id"]
    assert result.data["due_local"].startswith("2026-07-22T23:59")
    assert app.store.get_deadline("chat-a", deadline["id"]).due_local.startswith("2026-08-20T18:00")


def test_title_correction_asks_for_id_when_multiple_deadlines_match(app):
    _create_named_deadline(app, "Загрузка презентации питча")
    _create_named_deadline(app, "Загрузка презентации питча резерв", "2026-08-21")

    class ByTitleProvider:
        def parse(self, _text):
            return ProviderResult(Intent.CORRECT, {
                "deadline_id": None,
                "target_title": "загрузка презентации питча",
                "target_evidence": "загрузке презентации питча",
                "date": None, "time": None,
            }, "stub")

    app.provider = ByTitleProvider()
    result = app.handle(
        "chat-a", Actor("admin", Role.ADMIN),
        "@gosha обнови дедлайн по загрузке презентации питча",
        now=NOW,
    )
    assert result.status == "clarification"
    assert "несколько" in result.message and result.message.count("[") == 2


def test_title_correction_rejects_ungrounded_or_cross_chat_target(app):
    _create_named_deadline(app, "Загрузка презентации питча", chat="chat-b")

    class UngroundedProvider:
        def __init__(self, target): self.target = target
        def parse(self, _text):
            return ProviderResult(Intent.CORRECT, {
                "deadline_id": None,
                "target_title": self.target,
                "target_evidence": "загрузке презентации питча",
                "date": None, "time": None,
            }, "stub")

    app.provider = UngroundedProvider("экзамен")
    ungrounded = app.handle(
        "chat-a", Actor("admin", Role.ADMIN),
        "@gosha обнови дедлайн по загрузке презентации питча",
        now=NOW,
    )
    assert ungrounded.status == "clarification"

    app.provider = UngroundedProvider("загрузка презентации питча")
    cross_chat = app.handle(
        "chat-a", Actor("admin", Role.ADMIN),
        "@gosha обнови дедлайн по загрузке презентации питча",
        now=NOW,
    )
    assert cross_chat.status == "not_found"


def test_stale_correction_preview_is_rejected(app):
    d = create(app).data["deadline"]; steward = Actor("s", Role.STEWARD)
    p1 = app.handle("chat-a", steward, f"@gosha исправь {d['id']} на 2026-09-01 10:00", now=NOW)
    p2 = app.handle("chat-a", steward, f"@gosha исправь {d['id']} на 2026-09-02 11:00", now=NOW)
    assert app.confirm("chat-a", steward, p1.data["pending_id"], "first", NOW).status == "success"
    assert app.confirm("chat-a", steward, p2.data["pending_id"], "second", NOW).status == "stale_preview"


def test_stale_deactivation_preview_is_rejected(app):
    d = create(app).data["deadline"]; steward = Actor("s", Role.STEWARD)
    stale = app.handle("chat-a", steward, f"@gosha деактивируй {d['id']}", now=NOW)
    edit = app.handle("chat-a", steward, f"@gosha исправь {d['id']} на 2026-09-01 10:00", now=NOW)
    assert app.confirm("chat-a", steward, edit.data["pending_id"], "edit-first", NOW).status == "success"
    assert app.confirm("chat-a", steward, stale.data["pending_id"], "stale-deactivate", NOW).status == "stale_preview"


def test_ordinary_message_ignored_before_provider(app):
    r = app.handle("chat-a", Actor("u"), "у нас дедлайн 2026-09-01", entry_point="ordinary", now=NOW); assert r.status == "ignored"


def test_write_kill_switch(app):
    p = preview(app); app.store.set_runtime_setting("global_writes_enabled", False, actor_id="operator", reason="incident", now=NOW)
    r = app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "k", NOW); assert r.status == "stopped"; assert not app.store.list_deadlines("chat-a")


def test_per_chat_kill_switch(app):
    p = preview(app); app.store.set_chat_enabled("chat-a", False, actor_id="operator", reason="incident", now=NOW)
    assert app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "k", NOW).status == "stopped"
    assert app.handle("chat-a", Actor("u1"), "@gosha покажи дедлайны", now=NOW).status == "stopped"


def test_persisted_chat_kill_switch_blocks_cancel(app):
    create(app); app.store.set_chat_enabled("chat-a", False)
    assert app.cancel_last("chat-a", Actor("u1"), NOW + timedelta(minutes=2)).status == "stopped"


def test_llm_kill_switch_uses_deterministic_fallback(app):
    app.store.set_runtime_setting("global_llm_enabled", False, actor_id="operator", reason="provider incident", now=NOW)
    r = app.handle("chat-a", Actor("u1"), "/deadline_add презентация | 2026-08-20 | 18:00", entry_point="command", now=NOW)
    assert r.status == "preview"


def test_provider_outage_keeps_formal_command_available():
    class Down:
        def parse(self, _text):
            raise ProviderError("down")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    result = GoshaService(store, Down()).handle(
        "chat-a", Actor("u1"), "/deadline_add Презентация | 2026-08-20 | 18:00", entry_point="command", now=NOW,
    )
    assert result.status == "preview"


def test_model_cannot_select_immediate_cancel_side_effect():
    class Faulty:
        def parse(self, _text):
            return ProviderResult(Intent.CANCEL_LAST, {}, "model")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store)
    deadline = create(app).data["deadline"]
    app.provider = Faulty()
    result = app.handle("chat-a", Actor("u1"), "@gosha что было добавлено последним?", now=NOW + timedelta(minutes=1))
    assert result.status == "clarification"
    assert store.get_deadline("chat-a", deadline["id"]).status == "active"


def test_free_form_call_all_requires_preview_and_queues_known_participants():
    class CallAllProvider:
        def parse(self, _text):
            return ProviderResult(Intent.CALL_ALL, {}, "stub")

    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    store.upsert_participant("chat-a", "u1", "Ален", "alen_test", NOW, explicit=True)
    store.upsert_participant("chat-a", "u2", "Даша", "dasha_test", NOW, explicit=True)
    store.upsert_participant("chat-a", "u3", "Макс", None, NOW, explicit=True)
    app = GoshaService(store, CallAllProvider())
    actor = Actor("u1", Role.MEMBER, "Ален")
    preview_result = app.handle("chat-a", actor, "@gosha ребят, собери всех сюда", now=NOW)
    assert preview_result.status == "preview" and preview_result.data["participant_count"] == 2
    assert not [job for job in store.jobs("chat-a") if job["type"] == "call_all"]

    confirmed = app.confirm("chat-a", actor, preview_result.data["pending_id"], "call-all", NOW)
    assert confirmed.status == "success"
    jobs = [job for job in store.jobs("chat-a") if job["type"] == "call_all"]
    assert len(jobs) == 1 and jobs[0]["status"] == "scheduled"
    payload = json.loads(jobs[0]["payload_json"])
    assert payload["caller_name"] == "Ален"
    assert {item["user_id"] for item in payload["participants"]} == {"u2", "u3"}


def test_call_all_respects_opt_out_and_ten_minute_cooldown():
    class CallAllProvider:
        def parse(self, _text):
            return ProviderResult(Intent.CALL_ALL, {}, "stub")

    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    store.upsert_participant("chat-a", "u1", "Ален", None, NOW, explicit=True)
    store.upsert_participant("chat-a", "u2", "Даша", None, NOW, explicit=True)
    store.upsert_participant("chat-a", "u3", "Макс", None, NOW, explicit=True)
    assert store.opt_out_participant("chat-a", "u3", NOW)
    # Ordinary observation must not silently undo an explicit opt-out.
    store.upsert_participant("chat-a", "u3", "Макс", None, NOW + timedelta(minutes=1))
    app = GoshaService(store, CallAllProvider())
    actor = Actor("u1", display_name="Ален")
    first = app.handle("chat-a", actor, "@gosha позови всех", now=NOW)
    assert first.data["participant_count"] == 1
    app.confirm("chat-a", actor, first.data["pending_id"], "first-call", NOW)
    second = app.handle("chat-a", actor, "@gosha тегни народ", now=NOW + timedelta(minutes=1))
    assert second.status == "rate_limited"


def test_two_previews_cannot_confirm_duplicate_deadline(app):
    first = preview(app)
    second = preview(app)
    assert app.confirm("chat-a", Actor("u1"), first.data["pending_id"], "first", NOW).status == "success"
    assert app.confirm("chat-a", Actor("u1"), second.data["pending_id"], "second", NOW).status == "possible_duplicate"
    assert len(app.store.list_deadlines("chat-a")) == 1


def test_cancel_last_creation_within_window(app):
    d = create(app).data["deadline"]
    r = app.handle("chat-a", Actor("u1"), "@gosha отмени последнее", now=NOW + timedelta(minutes=5))
    assert r.status == "success" and app.store.get_deadline("chat-a", d["id"]).status == "cancelled"
    assert app.handle("chat-a", Actor("u1"), "@gosha отмени последнее", now=NOW + timedelta(minutes=6)).data["idempotent_replay"] is True


def test_past_date_rejected(app):
    r = app.handle("chat-a", Actor("u"), "@gosha добавь дедлайн отчет 2026-01-01", now=NOW); assert r.status == "rejected"


def test_default_time_is_explicit_in_preview(app):
    r = app.handle("chat-a", Actor("u"), "@gosha добавь дедлайн отчет 2026-08-20", now=NOW); assert r.data["time_defaulted"] is True; assert "T09:00" in r.data["due_local"]; assert r.data["weekday"] == "четверг"


def test_natural_russian_date_is_normalized_in_preview(app):
    result = app.handle("chat-a", Actor("u"), "@gosha добавь дедлайн тест 27 июля в 18:00", now=NOW)
    assert result.status == "preview"
    assert result.data["title"] == "тест"
    assert result.data["due_local"].startswith("2026-07-27T18:00")
    assert result.data["weekday"] == "понедельник"


def test_openai_candidate_can_repair_a_misspelled_date_for_preview():
    class OpenAIStub:
        def parse(self, _text):
            return ProviderResult(
                Intent.ADD,
                {"title": "просто день лета", "date": "3 августа", "date_evidence": "З авгсута", "time": None, "time_evidence": None},
                "openai-structured-v1:test-model",
            )
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    result = GoshaService(store, OpenAIStub()).handle(
        "chat-a", Actor("u"), "@gosha гош З авгсута просто день лета", now=NOW,
    )
    assert result.status == "preview"
    assert result.data["title"] == "просто день лета"
    assert result.data["due_local"].startswith("2026-08-03T09:00")
    assert not store.list_deadlines("chat-a")


def test_non_openai_provider_cannot_invent_unwritten_date():
    class UntrustedStub:
        def parse(self, _text):
            return ProviderResult(Intent.ADD, {"title": "защита", "date": "3 августа", "time": None}, "untrusted")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    result = GoshaService(store, UntrustedStub()).handle("chat-a", Actor("u"), "@gosha добавь защиту", now=NOW)
    assert result.status == "clarification"
    assert not store.list_deadlines("chat-a")


def test_model_date_requires_verbatim_evidence_from_request():
    class Stub:
        def parse(self, _text):
            return ProviderResult(Intent.ADD, {"title": "защита", "date": "3 августа", "date_evidence": "3 августа", "time": None}, "stub")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    result = GoshaService(store, Stub()).handle("chat-a", Actor("u"), "@gosha добавь защиту", now=NOW)
    assert result.status == "clarification" and not store.list_deadlines("chat-a")


def test_model_can_ground_colloquial_time_with_verbatim_evidence():
    class Stub:
        def parse(self, _text):
            return ProviderResult(Intent.ADD, {
                "title": "защита", "date": "31 июля", "date_evidence": "31 июля",
                "time": "18:00", "time_evidence": "в шесть вечера",
            }, "stub")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    result = GoshaService(store, Stub()).handle("chat-a", Actor("u"), "@gosha добавь защиту 31 июля в шесть вечера", now=NOW)
    assert result.status == "preview" and result.data["due_local"].startswith("2026-07-31T18:00")


def test_natural_date_without_year_rolls_to_next_future_year():
    now = datetime(2026, 12, 20, 12, tzinfo=timezone.utc)
    assert resolve_user_dates("дедлайн 15 января", "Europe/Moscow", now) == ["2027-01-15"]


def test_relative_and_numeric_dates_use_chat_calendar():
    assert resolve_user_dates("защита завтра", "Europe/Moscow", NOW) == ["2026-07-18"]
    assert resolve_user_dates("защита 27.07 в 18:00", "Europe/Moscow", NOW) == ["2026-07-27"]


def test_reminder_cadence_has_t24_and_digest():
    local, _, _ = normalize_due("2026-08-20", "18:00", "Europe/Moscow", NOW); jobs = reminder_schedule(local, "Europe/Moscow", NOW.isoformat()); assert {j[0] for j in jobs} == {"t24", "sunday_digest"}


def test_short_lead_has_no_t24():
    local, _, _ = normalize_due("2026-07-18", "13:00", "Europe/Moscow", NOW); jobs = reminder_schedule(local, "Europe/Moscow", NOW.isoformat()); assert "t24" not in {j[0] for j in jobs}


def test_digest_uses_iana_zone_across_fall_dst():
    created = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    local, _, _ = normalize_due("2026-11-01", "10:00", "America/New_York", created)
    jobs = dict(reminder_schedule(local, "America/New_York", created.isoformat()))
    assert jobs["sunday_digest"] == "2026-10-25T23:00:00+00:00"
    assert jobs["t24"] == "2026-10-31T15:00:00+00:00"


def test_t24_is_exact_elapsed_day_across_spring_dst():
    created = datetime(2026, 3, 1, 12, tzinfo=timezone.utc)
    local, due_utc, _ = normalize_due("2026-03-08", "10:00", "America/New_York", created)
    jobs = dict(reminder_schedule(local, "America/New_York", created.isoformat()))
    assert datetime.fromisoformat(due_utc) - datetime.fromisoformat(jobs["t24"]) == timedelta(hours=24)


def test_backend_resolves_literal_weekday_instead_of_provider_guess():
    class FaultyProvider:
        def parse(self, text):
            return ProviderResult(Intent.ADD, {"title": "Защита", "date": "2026-08-20", "time": "18:00"}, "faulty")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store, FaultyProvider())
    result = app.handle("chat-a", Actor("u1"), "@gosha защита в следующий четверг в 18:00", now=NOW)
    assert result.status == "preview"
    assert result.data["due_local"].startswith("2026-07-23T18:00")
    assert not store.list_deadlines("chat-a")


def test_backend_drops_provider_hallucinated_time():
    class FaultyProvider:
        def parse(self, text):
            return ProviderResult(Intent.ADD, {"title": "Защита", "date": "2026-08-20", "time": "18:00"}, "faulty")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store, FaultyProvider())
    result = app.handle("chat-a", Actor("u1"), "@gosha добавь защиту 2026-08-20", now=NOW)
    assert result.status == "preview" and result.data["time_defaulted"] is True
    assert "T09:00" in result.data["due_local"]


@pytest.mark.parametrize("provider_time", [None, "19:00"])
def test_backend_uses_unique_literal_time_over_provider(provider_time):
    class FaultyProvider:
        def parse(self, text):
            return ProviderResult(Intent.ADD, {"title": "Защита", "date": "2026-08-20", "time": provider_time}, "faulty")
    store = Store(); store.add_chat("chat-a", "Europe/Moscow")
    app = GoshaService(store, FaultyProvider())
    result = app.handle("chat-a", Actor("u1"), "@gosha добавь защиту 2026-08-20 18:00", now=NOW)
    assert result.status == "preview" and result.data["time_defaulted"] is False
    assert "T18:00" in result.data["due_local"]


def test_backend_rejects_provider_hallucinated_write_id():
    app = GoshaService(Store())
    app.store.add_chat("chat-a", "Europe/Moscow")
    deadline_id = create(app).data["deadline"]["id"]

    class FaultyProvider:
        def parse(self, text):
            return ProviderResult(Intent.DEACTIVATE, {"deadline_id": deadline_id}, "faulty")

    app.provider = FaultyProvider()
    result = app.handle("chat-a", Actor("s", Role.STEWARD), "@gosha деактивируй последний", now=NOW)
    assert result.status == "clarification"
    assert app.store.get_deadline("chat-a", deadline_id).status == "active"


def test_backend_rejects_multiple_write_date_or_time_literals(app):
    result = app.handle("chat-a", Actor("u1"), "@gosha добавь отчёт 2026-08-20 18:00 или 2026-08-21 19:00", now=NOW)
    assert result.status == "clarification" and not app.store.list_deadlines("chat-a")


def test_cancel_audit_contains_cancelled_after_state(app):
    create(app)
    app.handle("chat-a", Actor("u1"), "@gosha отмени последнее", now=NOW + timedelta(minutes=5))
    row = app.store.audit("chat-a")[-1]
    assert json.loads(row["after_json"])["status"] == "cancelled"


def test_invalid_timezone_rejected():
    with pytest.raises(TimeRuleError): normalize_due("2026-08-20", "18:00", "MSK", NOW)


def test_ambiguous_and_nonexistent_dst_times_rejected():
    with pytest.raises(TimeRuleError, match="ambiguous_local_time"):
        normalize_due("2026-11-01", "01:30", "America/New_York", NOW)
    with pytest.raises(TimeRuleError, match="nonexistent_local_time"):
        normalize_due("2027-03-14", "02:30", "America/New_York", NOW)


def test_audit_written_after_commit_only(app):
    p = preview(app); assert app.store.audit("chat-a") == []; app.confirm("chat-a", Actor("u1"), p.data["pending_id"], "k", NOW); assert app.store.audit("chat-a")[0]["action"] == "create"


def test_provider_refusal_fail_safe(monkeypatch):
    class Fake:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self): return iter([])
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Fake())
    with pytest.raises(ProviderError): OpenAICompatibleProvider("x", model="mock-contract-model").parse("@gosha hi")


def test_openai_structured_response_contract(monkeypatch):
    payload = {
        "output": [{"content": [{"type": "output_text", "text": json.dumps({"intent": "add_deadline", "slots": {"title": "Отчёт", "date": "2026-09-01", "date_evidence": "2026-09-01", "time": None, "time_evidence": None, "deadline_id": None, "target_title": None, "target_evidence": None, "url": None, "description": None, "material_id": None, "query": None}})}]}],
        "usage": {
            "input_tokens": 120,
            "output_tokens": 30,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
    }
    class Fake(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    captured = {}
    def fake_open(request, **_kwargs):
        captured["body"] = json.loads(request.data)
        return Fake(json.dumps(payload).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    result = OpenAICompatibleProvider("secret", model="gpt-5.6-luna").parse("@gosha добавь дедлайн")
    assert result.intent == Intent.ADD and result.slots["date"] == "2026-09-01" and "secret" not in result.provider
    assert result.usage is not None
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.cached_input_tokens, result.usage.reasoning_tokens) == (120, 30, 20, 5)
    assert result.usage.latency_ms is not None and result.usage.latency_ms >= 0
    assert captured["body"]["model"] == "gpt-5.6-luna"
    assert captured["body"]["reasoning"] == {"effort": "none"}
    assert captured["body"]["store"] is False
    structured = captured["body"]["text"]["format"]
    assert structured["type"] == "json_schema" and structured["strict"] is True
    assert "save_material" in structured["schema"]["properties"]["intent"]["enum"]
    assert "call_all_participants" in structured["schema"]["properties"]["intent"]["enum"]
    assert {"url", "description", "material_id"} <= set(structured["schema"]["properties"]["slots"]["required"])
    assert {"date_evidence", "time_evidence"} <= set(structured["schema"]["properties"]["slots"]["required"])
    assert {"target_title", "target_evidence"} <= set(structured["schema"]["properties"]["slots"]["required"])
    assert "cancel_last_creation" not in structured["schema"]["properties"]["intent"]["enum"]
    assert "safety_identifier" not in captured["body"]


def test_openai_refusal_and_malformed_material_schema_fail_safe(monkeypatch):
    bodies = [
        {"output": [{"content": [{"type": "refusal", "refusal": "no"}]}]},
        {"output": [{"content": [{"type": "output_text", "text": json.dumps({"intent": "save_material", "slots": {"url": "https://example.org"}})}]}]},
    ]
    class Fake(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    for body in bodies:
        monkeypatch.setattr("urllib.request.urlopen", lambda *_a, _body=body, **_k: Fake(json.dumps(_body).encode()))
        with pytest.raises(ProviderError):
            OpenAICompatibleProvider("secret", model="mock-contract-model").parse("@gosha сохрани https://example.org гайд")


def test_openai_provider_requires_explicit_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_provider("openai")


def test_openai_provider_requires_explicit_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.delenv("GOSHA_OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError, match="GOSHA_OPENAI_MODEL"):
        build_provider("openai")


def test_synthetic_eval_is_labeled_smoke():
    report = evaluate("data/synthetic-eval.jsonl"); assert report["dataset_kind"] == "synthetic_smoke_test"; assert report["n"] == 26; assert "not an LLM" in report["claim_limit"]; assert report["reproducibility"]["dataset_sha256"]; assert report["reproducibility"]["evaluator_version"] == "1.4.0"; assert report["per_class"] and report["confusion_matrix"]; assert report["slice_metrics"]["material"]["n"] == 8


def test_eval_aggregates_llm_usage_and_explicit_pricing():
    class MeteredProvider(OfflineProvider):
        name = "metered-test"

        def parse(self, text):
            result = super().parse(text)
            result.usage = ProviderUsage(input_tokens=100, output_tokens=20, latency_ms=50)
            return result

    report = evaluate(
        "data/synthetic-eval.jsonl", MeteredProvider(),
        input_usd_per_million=1.0, output_usd_per_million=2.0,
    )
    assert report["llm_usage"] == {
        "measured_requests": 26,
        "input_tokens": 2600,
        "output_tokens": 520,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "latency_ms": 1300,
        "mean_latency_ms": 50.0,
        "estimated_cost_usd": 0.00364,
        "pricing_assumption_usd_per_million": {"input": 1.0, "output": 2.0},
    }


def test_runtime_usage_event_contains_no_message_or_raw_identifiers():
    class MeteredProvider:
        name = "metered-test"

        def parse(self, _text):
            return ProviderResult(
                Intent.LIST, {}, "metered-test:model-a",
                usage=ProviderUsage(input_tokens=101, output_tokens=11, latency_ms=42),
            )

    store = Store()
    store.add_chat("chat-secret", "Europe/Moscow")
    service = GoshaService(store, MeteredProvider(), telemetry_hmac_key="deployment-key")
    service.handle("chat-secret", Actor("user-secret"), "@gosha покажи дедлайны с личным текстом", now=NOW)
    event = dict(store.conn.execute("SELECT * FROM events WHERE name='llm_usage'").fetchone())
    serialized = json.dumps(event, ensure_ascii=False)
    assert '"input_tokens":101' in event["result"] and '"latency_ms":42' in event["result"]
    assert "личным текстом" not in serialized and "chat-secret" not in serialized and "user-secret" not in serialized


def test_http_root_and_asset_are_served(app):
    Handler.service = app
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/health", timeout=2) as r:
            assert json.load(r) == {"status": "ok", "version": "1.2.0"}
        with urlopen(base + "/", timeout=2) as r:
            assert r.status == 200 and b"Gosha AI" in r.read()
        with urlopen(base + "/app.js", timeout=2) as r:
            assert r.status == 200 and b"/api/confirm" in r.read()
        with urlopen(base + "/api/state?chat_id=chat-a", timeout=2) as r:
            assert json.load(r)["chat_id"] == "chat-a"
        with pytest.raises(HTTPError) as missing:
            urlopen(base + "/api/state?chat_id=missing", timeout=2)
        assert missing.value.code == 404

        invalid = Request(
            base + "/api/ask", json.dumps({"role": "owner"}).encode(),
            {"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(HTTPError) as rejected:
            urlopen(invalid, timeout=2)
        assert rejected.value.code == 400

        unknown = Request(
            base + "/api/unknown", b"{}", {"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(HTTPError) as not_found:
            urlopen(unknown, timeout=2)
        assert not_found.value.code == 404
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def _post(base, path, body):
    request = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def test_parallel_http_double_confirm_is_atomic(app):
    Handler.service = app
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler); thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        preview_body = _post(base, "/api/ask", {"chat_id": "chat-a", "user_id": "u1", "role": "member", "text": "@gosha добавь дедлайн параллельный тест 2026-09-10 10:00"})
        pending = preview_body["data"]["pending_id"]
        bodies = [{"chat_id": "chat-a", "user_id": "u1", "role": "member", "pending_id": pending, "idempotency_key": key} for key in ("parallel-a", "parallel-b")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda body: _post(base, "/api/confirm", body), bodies))
        assert sorted(r["status"] for r in results) == ["rejected", "success"]
        assert len(app.store.list_deadlines("chat-a")) == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_idempotency_key_mismatch_is_rejected(app):
    p1 = preview(app)
    p2 = app.handle("chat-a", Actor("u1"), "@gosha добавь дедлайн другой 2026-08-21 18:00", now=NOW)
    assert app.confirm("chat-a", Actor("u1"), p1.data["pending_id"], "reused", NOW).status == "success"
    assert app.confirm("chat-a", Actor("u1"), p2.data["pending_id"], "reused", NOW).status == "idempotency_conflict"


def test_sunday_digest_is_aggregated_per_chat_week(app):
    create(app)
    p2 = app.handle("chat-a", Actor("u2"), "@gosha добавь дедлайн второй 2026-08-21 18:00", now=NOW)
    app.confirm("chat-a", Actor("u2"), p2.data["pending_id"], "second", NOW)
    jobs = app.store.jobs("chat-a")
    assert len([j for j in jobs if j["type"] == "sunday_digest"]) == 1
    assert len([j for j in jobs if j["type"] == "t24"]) == 2
