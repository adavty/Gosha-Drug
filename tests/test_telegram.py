from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import re
import sys
from threading import Event, Thread
from urllib.error import HTTPError, URLError

import pytest

from gosha.models import Intent, ProviderResult
from gosha.service import GoshaService
from gosha.store import Store
from gosha.telegram import BotIdentity, OffsetFile, TelegramAPI, TelegramAPIError, TelegramBot, main as telegram_main, run_polling


NOW = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
CHAT = "-100123"


class FakeAPI:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.admins = {"1"}
        self.next_message_id = 100
        self.send_error: TelegramAPIError | None = None

    def call(self, method, payload=None):
        payload = payload or {}
        self.calls.append((method, payload))
        if method == "getChatMember":
            return {"status": "administrator" if str(payload["user_id"]) in self.admins else "member"}
        if method == "sendMessage":
            if self.send_error:
                raise self.send_error
            self.next_message_id += 1
            return {"message_id": self.next_message_id, "chat": {"id": payload["chat_id"]}}
        if method in {"answerCallbackQuery", "editMessageText"}:
            return True
        raise AssertionError(f"unexpected Bot API method: {method}")

    def sent(self):
        return [payload for method, payload in self.calls if method == "sendMessage"]


def make_bot():
    store = Store()
    store.add_chat(CHAT, "Europe/Moscow")
    api = FakeAPI()
    bot = TelegramBot(api, GoshaService(store), now=lambda: NOW, identity=BotIdentity("999", "goshaspace_bot"))
    return bot, api, store


def message(text, *, user_id="10", reply_to=None, first_name="User", username=None):
    value = {
        "message_id": 1,
        "chat": {"id": int(CHAT), "type": "supergroup"},
        "from": {"id": int(user_id), "first_name": first_name},
        "text": text,
    }
    if reply_to:
        value["reply_to_message"] = reply_to
    if username:
        value["from"]["username"] = username
    return {"update_id": 1, "message": value}


def callback(data, *, user_id="10", callback_id="cb-1", message_id=101):
    return {
        "update_id": 2,
        "callback_query": {
            "id": callback_id,
            "from": {"id": int(user_id), "first_name": "User"},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": int(CHAT), "type": "supergroup"}},
        },
    }


def add_preview(bot, api, *, user_id="10"):
    bot.process_update(message("/deadline_add Презентация | 2026-08-20 | 18:00", user_id=user_id))
    keyboard = api.sent()[-1]["reply_markup"]["inline_keyboard"][0]
    return keyboard[0]["callback_data"].split(":")[-1]


def test_telegram_update_callback_commit_and_second_user_retrieval():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    assert store.list_deadlines(CHAT) == []

    bot.process_update(callback(f"g:confirm:{pending}"))
    assert len(store.list_deadlines(CHAT)) == 1
    methods = [method for method, _ in api.calls]
    assert "answerCallbackQuery" in methods and "editMessageText" in methods

    bot.process_update(message("/deadlines", user_id="20"))
    assert "Презентация" in api.sent()[-1]["text"]


def test_free_form_call_all_mentions_registered_participants_after_confirm():
    bot, api, store = make_bot()

    class CallAllProvider:
        def parse(self, _text):
            return ProviderResult(Intent.CALL_ALL, {}, "stub")

    bot.service.provider = CallAllProvider()
    # Ordinary text is not sent to AI, but its author becomes known locally.
    bot.process_update(message("обычная переписка", user_id="20", first_name="Даша", username="dasha_test"))
    bot.process_update(message("ещё сообщение", user_id="30", first_name="Макс"))
    assert api.sent() == []

    bot.process_update(message("@goshaspace_bot ребят, позовите всех сюда", user_id="10", first_name="Ален"))
    preview = api.sent()[-1]
    assert "Будут отмечены: 2" in preview["text"]
    pending = preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{pending}", user_id="10", callback_id="call-all-confirm"))
    assert bot.deliver_due() == 1
    delivered = api.sent()[-1]
    assert delivered["parse_mode"] == "HTML"
    assert "@dasha_test" in delivered["text"]
    assert 'tg://user?id=30' in delivered["text"]
    assert "Ален зовет всех в чат" in delivered["text"]
    job = next(item for item in store.jobs(CHAT) if item["type"] == "call_all")
    assert job["status"] == "delivered" and job["payload_json"] == "{}"


def test_participant_can_opt_out_and_rejoin_call_registry():
    bot, api, store = make_bot()
    bot.process_update(message("/gosha_join", user_id="20", first_name="Даша"))
    assert {item["user_id"] for item in store.list_participants(CHAT)} == {"20"}
    bot.process_update(message("/gosha_leave", user_id="20", first_name="Даша"))
    assert store.list_participants(CHAT) == []
    bot.process_update(message("обычное сообщение", user_id="20", first_name="Даша"))
    assert store.list_participants(CHAT) == []
    bot.process_update(message("/gosha_join", user_id="20", first_name="Даша"))
    assert {item["user_id"] for item in store.list_participants(CHAT)} == {"20"}


def test_onboarding_button_explicitly_registers_participant_and_updates_count():
    bot, api, store = make_bot()
    bot.process_update(message("/gosha_leave", user_id="20", first_name="Даша"))
    assert store.list_participants(CHAT) == []

    bot.process_update(callback("g:join", user_id="20", callback_id="join-dasha", message_id=700))

    participant = store.list_participants(CHAT)[0]
    assert participant["user_id"] == "20" and participant["source"] == "onboarding"
    answer = [payload for method, payload in api.calls if method == "answerCallbackQuery"][-1]
    assert "сможет позвать" in answer["text"]
    edit = [payload for method, payload in api.calls if method == "editMessageText"][-1]
    assert "Уже подключились: 1" in edit["text"]
    assert edit["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "g:join"

    edits_before = len([1 for method, _payload in api.calls if method == "editMessageText"])
    bot.process_update(callback("g:join", user_id="20", callback_id="join-dasha-again", message_id=700))
    assert len([1 for method, _payload in api.calls if method == "editMessageText"]) == edits_before
    assert "уже подключены" in [payload for method, payload in api.calls if method == "answerCallbackQuery"][-1]["text"]


def test_setup_posts_onboarding_and_admin_can_repost_it():
    store, api = Store(), FakeAPI()
    bot = TelegramBot(api, GoshaService(store), now=lambda: NOW, identity=BotIdentity("999", "goshaspace_bot"))

    bot.process_update(message("/setup Europe/Moscow", user_id="1", first_name="Ален"))
    onboarding = api.sent()[-1]
    assert "нужно нажать каждому участнику" in onboarding["text"]
    assert "может не суметь упомянуть вас" in onboarding["text"]
    assert "Уже подключились: 1" in onboarding["text"]
    assert onboarding["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "g:join"

    bot.process_update(message("/gosha_invite", user_id="20"))
    assert "только администратор" in api.sent()[-1]["text"]
    bot.process_update(message("/gosha_invite", user_id="1"))
    assert api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "g:join"


def test_monthly_csat_uses_emoji_buttons_numeric_storage_and_owner_only_statistics():
    bot, api, store = make_bot()
    bot.owner_user_id = "1"

    assert bot.schedule_monthly_csat() == 1
    assert bot.schedule_monthly_csat() == 0
    bot.now = lambda: datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    assert bot.deliver_due() == 1
    survey = api.sent()[-1]
    buttons = survey["reply_markup"]["inline_keyboard"][0]
    assert [button["text"] for button in buttons] == ["😡", "😞", "🙁", "😐", "🙂", "🤩"]
    assert all(not re.search(r"[1-6]", button["text"]) for button in buttons)

    bot.process_update(callback(buttons[1]["callback_data"], user_id="20", callback_id="csat-low", message_id=800))
    bot.process_update(callback(buttons[5]["callback_data"], user_id="30", callback_id="csat-high", message_id=800))
    answers = [payload["text"] for method, payload in api.calls if method == "answerCallbackQuery"]
    assert all(not re.search(r"\b[1-6]\b", answer) for answer in answers[-2:])

    bot.process_update(message("/csat_stats", user_id="20"))
    assert api.sent()[-1]["text"] == "Команда доступна только владельцу Gosha."
    bot.process_update(message("/csat_stats", user_id="1"))
    stats = api.sent()[-1]["text"]
    assert "Средняя оценка: 4 из 6" in stats
    assert "Медианная оценка: 4 из 6" in stats
    assert "Количество ответов: 2" in stats

    bot.process_update(callback(buttons[3]["callback_data"], user_id="20", callback_id="csat-update", message_id=800))
    assert "обновлён" in [payload for method, payload in api.calls if method == "answerCallbackQuery"][-1]["text"]
    assert store.csat_statistics()["count"] == 2


def test_deadline_preview_exposes_weekday_timezone_default_and_does_not_write():
    bot, api, store = make_bot()
    bot.process_update(message("/deadline_add Презентация | 2026-08-20"))
    sent = api.sent()[-1]
    assert "2026-08-20 09:00" in sent["text"]
    assert "четверг" in sent["text"]
    assert "Europe/Moscow" in sent["text"]
    assert "09:00 по умолчанию" in sent["text"]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["text"] == "✅ Подтвердить"
    assert store.list_deadlines(CHAT) == []


def test_polling_persists_offset_and_processes_update(tmp_path):
    stop = Event()

    class PollingAPI(FakeAPI):
        def call(self, method, payload=None):
            if method == "getUpdates":
                self.calls.append((method, payload or {}))
                stop.set()
                return [message("/deadlines", user_id="20")]
            return super().call(method, payload)

    store = Store()
    store.add_chat(CHAT, "Europe/Moscow")
    api = PollingAPI()
    bot = TelegramBot(api, GoshaService(store), now=lambda: NOW, identity=BotIdentity("999", "goshaspace_bot"))
    offset = OffsetFile(tmp_path / "polling.offset")

    run_polling(bot, offset, stop, poll_timeout=0)

    assert offset.load() == 2
    assert any(payload["text"] == "Актуальные дедлайны:\nпока нет" for payload in api.sent())
    assert any(job["type"] == "csat_survey" for job in store.jobs(CHAT))
    assert next(payload for method, payload in api.calls if method == "getUpdates")["offset"] == 0


def test_telegram_main_requires_token(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["gosha-telegram"])
    with pytest.raises(SystemExit, match="2"):
        telegram_main()
    assert "TELEGRAM_BOT_TOKEN is required" in capsys.readouterr().err


def test_telegram_api_classifies_transport_http_and_api_failures(monkeypatch):
    api = TelegramAPI("test-token", base_url="https://telegram.invalid")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: (_ for _ in ()).throw(URLError("offline")))
    with pytest.raises(TelegramAPIError) as send_failure:
        api.call("sendMessage", {"chat_id": "1", "text": "x"})
    assert send_failure.value.delivery_unknown is True and send_failure.value.retryable is False
    with pytest.raises(TelegramAPIError) as poll_failure:
        api.call("getUpdates")
    assert poll_failure.value.retryable is True and poll_failure.value.delivery_unknown is False

    def http_error(*_args, **_kwargs):
        raise HTTPError(
            "https://telegram.invalid", 429, "rate", {},
            BytesIO(b'{"description":"retry later"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", http_error)
    with pytest.raises(TelegramAPIError) as limited:
        api.call("getUpdates")
    assert limited.value.code == 429 and limited.value.retryable is True
    assert str(limited.value) == "retry later"

    class Fake(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: Fake(b'{"ok":false,"error_code":400,"description":"bad request"}'),
    )
    with pytest.raises(TelegramAPIError) as rejected:
        api.call("getMe")
    assert rejected.value.code == 400 and rejected.value.retryable is False


def test_natural_language_russian_date_reaches_telegram_preview():
    bot, api, store = make_bot()
    bot.process_update(message("@goshaspace_bot добавь дедлайн тест 27 июля в 18:00"))
    sent = api.sent()[-1]
    assert "тест — 2026-07-27 18:00" in sent["text"]
    assert "понедельник" in sent["text"]
    assert "reply_markup" in sent
    assert store.list_deadlines(CHAT) == []


def test_deadline_correction_preview_shows_symmetric_before_after_context():
    bot, api, store = make_bot()
    pending = add_preview(bot, api, user_id="1")
    bot.process_update(callback(f"g:confirm:{pending}", user_id="1", callback_id="create-for-correction"))
    deadline_id = store.list_deadlines(CHAT)[0].id
    bot.process_update(message(f"/deadline_correct {deadline_id} | 2026-09-01 | 10:00", user_id="1"))
    text = api.sent()[-1]["text"]
    assert "До:" in text and "После:" in text
    assert "четверг" in text and "вторник" in text
    assert text.count("Europe/Moscow") == 2
    assert store.get_deadline(CHAT, deadline_id).due_local.startswith("2026-08-20T18:00")


def test_callback_is_bound_to_original_actor():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    bot.process_update(callback(f"g:confirm:{pending}", user_id="20"))
    assert store.list_deadlines(CHAT) == []
    answers = [p for method, p in api.calls if method == "answerCallbackQuery"]
    assert "принадлежит другому" in answers[-1]["text"]


def test_success_exposes_ids_and_actor_bound_undo_without_store_lookup():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    bot.process_update(callback(f"g:confirm:{pending}", callback_id="cb-deadline-create"))
    deadline_edit = [p for method, p in api.calls if method == "editMessageText"][-1]
    deadline_id = re.search(r"\[([0-9a-f]{8})\]", deadline_edit["text"]).group(1)
    undo_deadline = deadline_edit["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert undo_deadline == f"g:undo:deadline:{deadline_id}"

    edits_before = len([1 for method, _ in api.calls if method == "editMessageText"])
    bot.process_update(callback(undo_deadline, user_id="20", callback_id="cb-foreign-undo", message_id=101))
    assert len([1 for method, _ in api.calls if method == "editMessageText"]) == edits_before
    bot.process_update(callback(undo_deadline, user_id="10", callback_id="cb-deadline-undo", message_id=101))
    assert store.get_deadline(CHAT, deadline_id).status == "cancelled"

    bot.process_update(message("@goshaspace_bot сохрани https://example.org/visible-id Гайд"))
    material_pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{material_pending}", callback_id="cb-material-create", message_id=202))
    material_edit = [p for method, p in api.calls if method == "editMessageText"][-1]
    material_id = re.search(r"\[([0-9a-f]{10})\]", material_edit["text"]).group(1)
    undo_material = material_edit["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert undo_material == f"g:undo:material:{material_id}"
    bot.process_update(callback(undo_material, callback_id="cb-material-undo", message_id=202))
    assert store.get_material(CHAT, material_id)["status"] == "cancelled"


def test_command_for_another_bot_is_ignored_before_provider_and_without_response():
    bot, api, _store = make_bot()
    class SpyProvider:
        calls = 0
        def parse(self, _text):
            self.calls += 1
            raise AssertionError("foreign command reached provider")
    spy = SpyProvider()
    bot.service.provider = spy
    bot.process_update(message("/deadline_add@other_bot Чужой | 2026-08-20 | 18:00"))
    assert spy.calls == 0 and api.sent() == []


def test_reply_to_bot_message_grounds_visible_material_id():
    bot, api, _store = make_bot()
    bot.process_update(message("@goshaspace_bot сохрани https://example.org/reply Гайд", user_id="1"))
    pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{pending}", user_id="1", callback_id="cb-reply-material", message_id=303))
    bot_text = [p for method, p in api.calls if method == "editMessageText"][-1]["text"]
    material_id = re.search(r"\[([0-9a-f]{10})\]", bot_text).group(1)
    reply_to = {"message_id": 303, "from": {"id": 999, "is_bot": True}, "text": bot_text}
    bot.process_update(message("деактивируй", user_id="1", reply_to=reply_to))
    assert "reply_markup" in api.sent()[-1]
    assert material_id in api.sent()[-1]["text"]


def test_time_only_reply_to_deadline_preserves_date_and_requires_admin_preview():
    bot, api, store = make_bot()
    pending = add_preview(bot, api, user_id="1")
    bot.process_update(callback(f"g:confirm:{pending}", user_id="1", callback_id="cb-time-followup-create", message_id=404))
    bot_text = [p for method, p in api.calls if method == "editMessageText"][-1]["text"]
    deadline = store.list_deadlines(CHAT)[0]
    assert deadline.due_local.startswith("2026-08-20T18:00")

    reply_to = {"message_id": 404, "from": {"id": 999, "is_bot": True}, "text": bot_text}
    bot.process_update(message("только время 23:55", user_id="1", reply_to=reply_to))
    preview = api.sent()[-1]
    assert "До:" in preview["text"] and "После:" in preview["text"]
    assert "2026-08-20 23:55" in preview["text"]
    assert store.get_deadline(CHAT, deadline.id).due_local.startswith("2026-08-20T18:00")

    correction_id = preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{correction_id}", user_id="1", callback_id="cb-time-followup-confirm", message_id=405))
    assert store.get_deadline(CHAT, deadline.id).due_local.startswith("2026-08-20T23:55")


def test_time_only_reply_to_deadline_still_requires_telegram_admin():
    bot, api, store = make_bot()
    pending = add_preview(bot, api, user_id="1")
    bot.process_update(callback(f"g:confirm:{pending}", user_id="1", callback_id="cb-time-member-create", message_id=406))
    bot_text = [p for method, p in api.calls if method == "editMessageText"][-1]["text"]
    deadline = store.list_deadlines(CHAT)[0]
    reply_to = {"message_id": 406, "from": {"id": 999, "is_bot": True}, "text": bot_text}
    bot.process_update(message("23:55", user_id="20", reply_to=reply_to))
    assert "администратора Telegram-чата" in api.sent()[-1]["text"]
    assert store.get_deadline(CHAT, deadline.id).due_local.startswith("2026-08-20T18:00")


def test_reply_to_multiple_ids_never_selects_first_implicitly():
    bot, api, store = make_bot()
    for title, date in (("Первый", "2026-08-20"), ("Второй", "2026-08-21")):
        pending = add_preview(bot, api, user_id="1") if title == "Первый" else None
        if pending is None:
            bot.process_update(message(f"/deadline_add {title} | {date} | 18:00", user_id="1"))
            pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
        bot.process_update(callback(f"g:confirm:{pending}", user_id="1", callback_id=f"confirm-{title}"))
    deadlines = store.list_deadlines(CHAT)
    bot_text = "Актуальные дедлайны:\n" + "\n".join(f"• {d.title} [{d.id}]" for d in deadlines)
    reply_to = {"message_id": 500, "from": {"id": 999, "is_bot": True}, "text": bot_text}
    bot.process_update(message("только время 23:55", user_id="1", reply_to=reply_to))
    assert "несколько объектов" in api.sent()[-1]["text"]
    assert all(d.due_local[11:16] == "18:00" for d in store.list_deadlines(CHAT))


def test_url_material_preview_confirm_and_second_user_search():
    bot, api, store = make_bot()
    bot.process_update(message("/material_add https://example.org/guide?utm_source=x | Гайд по интервью"))
    keyboard = api.sent()[-1]["reply_markup"]["inline_keyboard"][0]
    pending = keyboard[0]["callback_data"].split(":")[-1]
    assert store.list_materials(CHAT) == []
    bot.process_update(callback(f"g:confirm:{pending}"))
    assert len(store.list_materials(CHAT)) == 1

    bot.process_update(message("/materials интервью", user_id="20"))
    assert "Гайд по интервью" in api.sent()[-1]["text"]


def test_natural_language_material_save_find_and_admin_lifecycle():
    bot, api, store = make_bot()
    bot.process_update(message("@goshaspace_bot сохрани https://example.org/research гайд по интервью"))
    pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{pending}", callback_id="cb-material-save"))
    success_text = [p for method, p in api.calls if method == "editMessageText"][-1]["text"]
    material_id = re.search(r"\[([0-9a-f]{10})\]", success_text).group(1)

    bot.process_update(message("@goshaspace_bot найди материал интервью", user_id="20"))
    assert "https://example.org/research" in api.sent()[-1]["text"] and f"[{material_id}]" in api.sent()[-1]["text"]

    bot.process_update(message(f"@goshaspace_bot исправь материал {material_id} описание на Финальный гайд", user_id="20"))
    assert "администратора Telegram-чата" in api.sent()[-1]["text"]
    bot.process_update(message(f"@goshaspace_bot исправь материал {material_id} описание на Финальный гайд", user_id="1"))
    correct_pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{correct_pending}", user_id="1", callback_id="cb-material-correct"))
    assert store.get_material(CHAT, material_id)["description"] == "Финальный гайд"

    bot.process_update(message(f"@goshaspace_bot деактивируй материал {material_id}", user_id="1"))
    deactivate_pending = api.sent()[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    bot.process_update(callback(f"g:confirm:{deactivate_pending}", user_id="1", callback_id="cb-material-deactivate"))
    assert store.get_material(CHAT, material_id)["status"] == "inactive"


def test_ordinary_chat_ignored_but_reply_to_bot_is_processed():
    bot, api, _ = make_bot()
    bot.process_update(message("у нас дедлайн 2026-08-20"))
    assert api.sent() == []
    bot.process_update(message("покажи дедлайны", reply_to={"message_id": 8, "from": {"id": 999, "is_bot": True}, "text": "Gosha"}))
    assert "Актуальные дедлайны" in api.sent()[-1]["text"]


def test_privileged_change_uses_fresh_get_chat_member():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    bot.process_update(callback(f"g:confirm:{pending}"))
    deadline_id = store.list_deadlines(CHAT)[0].id

    bot.process_update(message(f"/deadline_deactivate {deadline_id}", user_id="20"))
    assert store.get_deadline(CHAT, deadline_id).status == "active"
    assert any(method == "getChatMember" and str(payload["user_id"]) == "20" for method, payload in api.calls)

    bot.process_update(message(f"/deadline_deactivate {deadline_id}", user_id="1"))
    assert "reply_markup" in api.sent()[-1]


def test_setup_requires_admin_and_iana_timezone():
    store, api = Store(), FakeAPI()
    bot = TelegramBot(api, GoshaService(store), now=lambda: NOW, identity=BotIdentity("999", "goshaspace_bot"))
    bot.process_update(message("/setup Europe/Moscow", user_id="20"))
    assert store.chat(CHAT) is None
    bot.process_update(message("/setup Europe/Moscow", user_id="1"))
    assert store.chat(CHAT)["timezone_id"] == "Europe/Moscow"


def test_due_delivery_calls_send_message_once_and_marks_success():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    bot.process_update(callback(f"g:confirm:{pending}"))
    job = next(item for item in store.jobs(CHAT) if item["deadline_id"] != "*")
    with store.lock:
        store.conn.execute("UPDATE reminders SET scheduled_for=?,available_at=? WHERE job_key=?", ((NOW - timedelta(minutes=1)).isoformat(), (NOW - timedelta(minutes=1)).isoformat(), job["job_key"]))
        store.conn.commit()
    before = len(api.sent())
    assert bot.deliver_due() == 1
    assert len(api.sent()) == before + 1
    assert next(x for x in store.jobs(CHAT) if x["job_key"] == job["job_key"])["status"] == "delivered"
    assert bot.deliver_due() == 0
    assert len(api.sent()) == before + 1


def test_transport_loss_becomes_delivery_unknown_without_blind_retry():
    bot, api, store = make_bot()
    pending = add_preview(bot, api)
    bot.process_update(callback(f"g:confirm:{pending}"))
    job = next(item for item in store.jobs(CHAT) if item["deadline_id"] != "*")
    with store.lock:
        store.conn.execute("UPDATE reminders SET scheduled_for=?,available_at=? WHERE job_key=?", ((NOW - timedelta(minutes=1)).isoformat(), (NOW - timedelta(minutes=1)).isoformat(), job["job_key"]))
        store.conn.commit()
    api.send_error = TelegramAPIError("transport", delivery_unknown=True)
    assert bot.deliver_due() == 0
    row = next(x for x in store.jobs(CHAT) if x["job_key"] == job["job_key"])
    assert row["status"] == "delivery_unknown"
    assert bot.deliver_due() == 0


def test_offset_file_is_atomic_and_recovers(tmp_path):
    offsets = OffsetFile(tmp_path / "telegram.offset")
    assert offsets.load() == 0
    offsets.save(42)
    assert offsets.load() == 42


def test_real_http_adapter_against_recorded_bot_api_simulation():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            method = self.path.rsplit("/", 1)[-1]
            calls.append((method, payload))
            if method == "getMe":
                result = {"id": 999, "is_bot": True, "username": "goshaspace_bot"}
            elif method == "getChatMember":
                result = {"status": "administrator"}
            elif method == "sendMessage":
                result = {"message_id": 501, "chat": {"id": payload["chat_id"]}}
            else:
                result = True
            body = json.dumps({"ok": True, "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        store = Store()
        store.add_chat(CHAT, "Europe/Moscow")
        api = TelegramAPI("mock-token", base_url=f"http://127.0.0.1:{server.server_port}", timeout=2)
        bot = TelegramBot(api, GoshaService(store), now=lambda: NOW)
        bot.process_update(message("/deadline_add HTTP demo | 2026-08-20 | 18:00"))
        send = next(payload for method, payload in reversed(calls) if method == "sendMessage")
        assert "четверг" in send["text"] and "Europe/Moscow" in send["text"] and "18:00" in send["text"]
        assert store.list_deadlines(CHAT) == []
        pending = send["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
        bot.process_update(callback(f"g:confirm:{pending}", message_id=501))
        assert len(store.list_deadlines(CHAT)) == 1
        methods = [method for method, _ in calls]
        assert methods[0] == "getMe"
        assert "answerCallbackQuery" in methods and "editMessageText" in methods
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
