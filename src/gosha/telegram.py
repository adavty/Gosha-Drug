from __future__ import annotations

import argparse
import html
import json
import os
import re
import signal
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import build_provider, telemetry_hmac_key
from .models import Actor, Response, Role
from .service import GoshaService
from .store_factory import build_store


class TelegramAPIError(RuntimeError):
    """A redacted Bot API failure safe to persist in the delivery outbox."""

    def __init__(self, description: str, *, code: int | None = None, retryable: bool = False, delivery_unknown: bool = False):
        super().__init__(description[:500])
        self.code = code
        self.retryable = retryable
        self.delivery_unknown = delivery_unknown


class TelegramAPI:
    def __init__(self, token: str, *, base_url: str = "https://api.telegram.org", timeout: float = 35):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self._url = f"{base_url.rstrip('/')}/bot{token}"
        self.timeout = timeout

    def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            f"{self._url}/{method}",
            json.dumps(payload or {}, ensure_ascii=False).encode(),
            {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body = json.load(exc)
                description = str(body.get("description") or f"telegram_http_{exc.code}")
            except Exception:
                description = f"telegram_http_{exc.code}"
            raise TelegramAPIError(description, code=exc.code, retryable=exc.code == 429 or exc.code >= 500) from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # A send may have reached Telegram even when its HTTP response was
            # lost. Blind retry would risk duplicate group notifications.
            raise TelegramAPIError(
                "telegram_transport_failure",
                retryable=method != "sendMessage",
                delivery_unknown=method == "sendMessage",
            ) from exc
        if not body.get("ok"):
            code = body.get("error_code")
            description = str(body.get("description") or "telegram_api_error")
            raise TelegramAPIError(description, code=code, retryable=code == 429 or bool(code and code >= 500))
        return body.get("result")


class OffsetFile:
    """Crash-safe long-polling cursor without coupling it to domain storage."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> int:
        try:
            return max(0, int(self.path.read_text(encoding="utf-8").strip()))
        except (FileNotFoundError, ValueError, OSError):
            return 0

    def save(self, offset: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(str(offset))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass


@dataclass(frozen=True)
class BotIdentity:
    id: str
    username: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramBot:
    def __init__(
        self,
        api: TelegramAPI,
        service: GoshaService,
        *,
        now: Callable[[], datetime] = _utcnow,
        identity: BotIdentity | None = None,
        owner_user_id: str | None = None,
    ):
        self.api = api
        self.service = service
        self.store = service.store
        self.now = now
        self.identity = identity or self._load_identity()
        self.owner_user_id = str(owner_user_id or "").strip()

    def _load_identity(self) -> BotIdentity:
        me = self.api.call("getMe")
        username = str(me.get("username") or "")
        if not username:
            raise RuntimeError("Telegram bot has no username")
        return BotIdentity(str(me["id"]), username)

    def _is_admin(self, chat_id: str, user_id: str) -> bool:
        member = self.api.call("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        return member.get("status") in {"creator", "administrator"}

    @staticmethod
    def _display_name(user: dict[str, Any]) -> str:
        value = " ".join(str(user.get(key) or "").strip() for key in ("first_name", "last_name")).strip()
        return " ".join(value.split())[:80] or str(user.get("username") or f"Участник {str(user.get('id') or '')[-4:]}")

    def _observe_participant(self, chat_id: str, user: dict[str, Any], *, source: str = "observed", explicit: bool = False) -> None:
        if not self.store.chat(chat_id) or not user.get("id") or user.get("is_bot"):
            return
        self.store.upsert_participant(
            chat_id, str(user["id"]), self._display_name(user), str(user.get("username") or "") or None,
            self.now(), source=source, explicit=explicit,
        )

    def _actor(self, chat_id: str, user_id: str, *, privileged: bool = False, display_name: str = "") -> Actor:
        if privileged:
            return Actor(user_id, Role.ADMIN if self._is_admin(chat_id, user_id) else Role.MEMBER, display_name)
        return Actor(user_id, Role.MEMBER, display_name)

    def process_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self._callback(update["callback_query"])
        elif "message" in update:
            self._message(update["message"])

    def _message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        text = message.get("text") or ""
        if chat.get("type") not in {"group", "supergroup"} or not user.get("id"):
            return
        chat_id, user_id = str(chat["id"]), str(user["id"])
        self._observe_participant(chat_id, user)
        for member in message.get("new_chat_members") or []:
            self._observe_participant(chat_id, member, source="joined")
        if not text:
            return
        addressed = re.match(r"^/[A-Za-z_]+@([A-Za-z0-9_]+)\b", text)
        if addressed and addressed.group(1).casefold() != self.identity.username.casefold():
            # Privacy-mode compatible boundary: another bot owns this update.
            return
        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""
        if command in {"/start", "/help"}:
            self._send(chat_id, self._help())
            return
        if command == "/setup":
            if self._setup(chat_id, user_id, text):
                self._observe_participant(chat_id, user, source="setup", explicit=True)
                self._send_onboarding(chat_id)
            return
        if command == "/gosha_invite":
            if not self.store.chat(chat_id):
                self._send(chat_id, "Сначала администратор должен настроить бота: /setup Europe/Moscow")
            elif not self._is_admin(chat_id, user_id):
                self._send(chat_id, "Повторно показать приглашение может только администратор чата.")
            else:
                self._send_onboarding(chat_id)
            return
        if command == "/gosha_join":
            self._observe_participant(chat_id, user, source="explicit_join", explicit=True)
            self._send(chat_id, "Вы зарегистрированы для группового вызова Gosha.")
            return
        if command == "/gosha_leave":
            self.store.opt_out_participant(chat_id, user_id, self.now())
            self._send(chat_id, "Вы исключены из групповых вызовов. Вернуться: /gosha_join")
            return
        if command == "/csat_stats":
            if not self.owner_user_id or user_id != self.owner_user_id:
                self._send(chat_id, "Команда доступна только владельцу Gosha.")
                return
            argument = re.sub(
                rf"^/csat_stats(?:@{re.escape(self.identity.username)})?\s*", "", text, flags=re.I,
            ).strip().lower()
            if argument and argument != "all" and not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", argument):
                self._send(chat_id, "Формат: /csat_stats, /csat_stats YYYY-MM или /csat_stats all")
                return
            self._send(chat_id, self._format_csat_statistics(self.store.csat_statistics(argument or None)))
            return
        if command == "/material_add":
            normalized = re.sub(rf"^/material_add(?:@{re.escape(self.identity.username)})?\s*", "", text, flags=re.I)
            parts = [part.strip() for part in normalized.split("|", 1)]
            if len(parts) != 2:
                self._send(chat_id, "Формат: /material_add https://... | Краткое описание")
                return
            self._send_response(chat_id, self.service.preview_material(chat_id, Actor(user_id), parts[0], parts[1], self.now()))
            return
        if command == "/materials":
            query = re.sub(rf"^/materials(?:@{re.escape(self.identity.username)})?\s*", "", text, flags=re.I)
            self._send_response(chat_id, self.service.list_materials(chat_id, query))
            return
        if command in {"/cancel_deadline", "/cancel_material"}:
            expected = 8 if command == "/cancel_deadline" else 10
            object_type = "deadline" if expected == 8 else "material"
            normalized = re.sub(rf"^{re.escape(command)}(?:@{re.escape(self.identity.username)})?\s*", "", text, flags=re.I)
            if not re.fullmatch(rf"[0-9a-f]{{{expected}}}", normalized, re.I):
                self._send(chat_id, f"Формат: {command} ID")
                return
            self._send_response(chat_id, self.service.cancel_created(chat_id, Actor(user_id), object_type, normalized, self.now()))
            return
        reply = message.get("reply_to_message") or {}
        reply_from = reply.get("from") or {}
        entry_point: str | None = None
        if text.startswith("/"):
            entry_point = "command"
        elif re.search(rf"@{re.escape(self.identity.username)}\b", text, re.I):
            entry_point = "mention"
        elif str(reply_from.get("id") or "") == self.identity.id:
            entry_point = "bot_reply"
            # A reply like "сколько осталось?" is grounded by an ID printed
            # in Gosha's own message, never by arbitrary chat history.
            reply_text = reply.get("text") or ""
            material_matches = list(dict.fromkeys(re.findall(r"\b[0-9a-f]{10}\b", reply_text, re.I)))
            deadline_matches = list(dict.fromkeys(re.findall(r"\b[0-9a-f]{8}\b", reply_text, re.I)))
            visible_ids = material_matches + deadline_matches
            explicit_ids = [item for item in visible_ids if re.search(rf"(?<![\w-]){re.escape(item)}(?![\w-])", text, re.I)]
            if len(visible_ids) > 1 and not explicit_ids:
                self._send(chat_id, "В сообщении несколько объектов. Укажите нужный ID прямо в ответе — я не буду выбирать за вас.")
                return
            material_match = re.search(r"\b[0-9a-f]{10}\b", reply_text, re.I) if material_matches else None
            deadline_match = re.search(r"\b[0-9a-f]{8}\b", reply_text, re.I) if deadline_matches else None
            match = material_match or deadline_match
            time_only = re.fullmatch(
                r"\s*(?:(?:только\s+)?время(?:\s+на)?|поставь(?:\s+время)?(?:\s+на)?|на)?\s*"
                r"((?:[01]\d|2[0-3]):[0-5]\d)\s*[.!]?\s*",
                text,
                re.I,
            )
            if deadline_match and time_only:
                # A terse reply is safe to ground only in the visible deadline
                # ID from Gosha's own message. The date is preserved by the
                # correction flow and the new time still requires preview.
                text = f"исправь дедлайн {deadline_match.group(0)} время на {time_only.group(1)}"
            elif match and match.group(0).lower() not in text.lower():
                object_word = "материал" if material_match else "дедлайн"
                text = f"{text} {object_word} {match.group(0)}"
        if not entry_point:
            return

        # Telegram may suffix group commands with @bot_username. Normalize
        # only the authenticated bot's own suffix; leave user content intact.
        text = re.sub(rf"^(/[A-Za-z_]+)@{re.escape(self.identity.username)}\b", r"\1", text, flags=re.I)
        text = re.sub(rf"@{re.escape(self.identity.username)}\b", "@gosha", text, flags=re.I)

        try:
            # Resolve the real Telegram role for every explicit invocation.
            # Authorization then follows the parsed intent, not a keyword guess.
            actor = self._actor(chat_id, user_id, privileged=True, display_name=self._display_name(user))
            response = self.service.handle(chat_id, actor, text, entry_point=entry_point, now=self.now())
            self._send_response(chat_id, response)
        except TelegramAPIError as exc:
            if exc.code not in {400, 403}:
                raise

    def _setup(self, chat_id: str, user_id: str, text: str) -> bool:
        if not self._is_admin(chat_id, user_id):
            self._send(chat_id, "Настроить Gosha может только администратор чата.")
            return False
        parts = text.split(maxsplit=1)
        timezone_id = parts[1].strip() if len(parts) == 2 else ""
        try:
            ZoneInfo(timezone_id)
        except (ZoneInfoNotFoundError, ValueError):
            self._send(chat_id, "Укажите IANA timezone, например: /setup Europe/Moscow")
            return False
        self.store.add_chat(chat_id, timezone_id)
        self._send(chat_id, f"Gosha настроен. Часовой пояс: {timezone_id}.")
        return True

    @staticmethod
    def _onboarding_markup() -> dict[str, Any]:
        return {"inline_keyboard": [[{
            "text": "✅ Подключиться к Gosha",
            "callback_data": "g:join",
        }]]}

    def _explicit_participant_count(self, chat_id: str) -> int:
        explicit_sources = {"setup", "explicit_join", "onboarding"}
        return sum(item.get("source") in explicit_sources for item in self.store.list_participants(chat_id))

    def _onboarding_text(self, chat_id: str) -> str:
        count = self._explicit_participant_count(chat_id)
        return (
            "👋 Gosha помогает участникам этого чата и может позвать всех, когда это важно.\n\n"
            "Важно: кнопку ниже нужно нажать каждому участнику. Без нажатия Gosha может не суметь "
            "упомянуть вас при общем вызове. Это занимает одну секунду.\n\n"
            "Я сохраню только ваш Telegram ID, имя и username — текст обычных "
            "сообщений не сохраняю и не отправляю в AI. Отказаться можно в любой момент: /gosha_leave\n\n"
            f"Уже подключились: {count}"
        )

    def _send_onboarding(self, chat_id: str) -> None:
        self._send(chat_id, self._onboarding_text(chat_id), reply_markup=self._onboarding_markup())

    def _callback(self, query: dict[str, Any]) -> None:
        callback_id = str(query.get("id") or "")
        acknowledged = False
        try:
            message, user = query.get("message") or {}, query.get("from") or {}
            chat = message.get("chat") or {}
            chat_id, user_id = str(chat.get("id") or ""), str(user.get("id") or "")
            self._observe_participant(chat_id, user, source="callback")
            data = str(query.get("data") or "")
            join_action = data == "g:join"
            csat_action = re.fullmatch(r"g:csat:([0-9a-f]{12}):([1-6])", data)
            pending_action = re.fullmatch(r"g:(confirm|cancel):([0-9a-f]{12})", data)
            undo_action = re.fullmatch(r"g:undo:(deadline|material):([0-9a-f]{8,10})", data)
            if not chat_id or not user_id or not (join_action or csat_action or pending_action or undo_action):
                self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Некорректное действие"})
                acknowledged = True
                return
            if csat_action:
                survey_id, score_text = csat_action.groups()
                result = self.store.record_csat_response(survey_id, chat_id, user_id, int(score_text), self.now())
                if result is None:
                    answer = "Этот опрос уже недоступен"
                elif result == "updated":
                    answer = "Спасибо! Ваш ответ обновлён ✅"
                else:
                    answer = "Спасибо! Ответ сохранён ✅"
                self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": answer})
                acknowledged = True
                return
            if join_action:
                if not self.store.chat(chat_id):
                    self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Сначала администратор должен настроить Gosha", "show_alert": True})
                    acknowledged = True
                    return
                explicit_sources = {"setup", "explicit_join", "onboarding"}
                previous = next((item for item in self.store.list_participants(chat_id) if item["user_id"] == user_id), None)
                already_joined = bool(previous and previous.get("source") in explicit_sources)
                self._observe_participant(chat_id, user, source="onboarding", explicit=True)
                answer = "Вы уже подключены к Gosha ✅" if already_joined else "Готово! Теперь Gosha сможет позвать вас ✅"
                self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": answer})
                acknowledged = True
                if not already_joined and message.get("message_id"):
                    try:
                        self.api.call("editMessageText", {
                            "chat_id": chat_id,
                            "message_id": message["message_id"],
                            "text": self._onboarding_text(chat_id),
                            "reply_markup": self._onboarding_markup(),
                        })
                    except TelegramAPIError as exc:
                        if exc.code != 400:
                            raise
                return
            if undo_action:
                object_type, object_id = undo_action.groups()
                if (object_type == "deadline" and len(object_id) != 8) or (object_type == "material" and len(object_id) != 10):
                    self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Некорректное действие"})
                    acknowledged = True
                    return
                response = self.service.cancel_created(chat_id, Actor(user_id), object_type, object_id, self.now())
                self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": response.message[:180]})
                acknowledged = True
                if response.status == "success":
                    self._edit_response(chat_id, str(message.get("message_id")), response)
                return
            action, pending_id = pending_action.groups()
            pending = self.store.pending(pending_id, chat_id, user_id, self.now())
            if not pending:
                self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Предпросмотр истёк или принадлежит другому пользователю"})
                acknowledged = True
                return
            privileged = pending["action"] in {"correct", "deactivate", "material_correct", "material_deactivate"}
            actor = self._actor(chat_id, user_id, privileged=privileged)
            if action == "confirm":
                response = self.service.confirm(chat_id, actor, pending_id, f"tg-callback:{callback_id}", self.now())
            elif hasattr(self.service, "cancel_pending"):
                response = self.service.cancel_pending(chat_id, actor, pending_id, self.now())
            else:
                response = Response("cancelled", "Предпросмотр отменён.")
            self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": response.message[:180]})
            acknowledged = True
            self._edit_response(chat_id, str(message.get("message_id")), response)
        except Exception:
            # Telegram requires every callback to be acknowledged, including
            # safe failures. Do not include exception or token in the answer.
            if not acknowledged:
                try:
                    self.api.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Не удалось выполнить действие"})
                except Exception:
                    pass
            raise

    def _help(self) -> str:
        return (
            "Gosha работает в групповом учебном чате.\n"
            "Пример: @goshadrugbot добавь дедлайн защита 27 июля в 18:00\n"
            "/setup Europe/Moscow — настройка администратором\n"
            "/gosha_invite — повторно показать кнопку подключения\n"
            "/deadline_add Название | YYYY-MM-DD | HH:MM\n"
            "/deadlines — общий список\n"
            "/deadline_correct ID | YYYY-MM-DD | HH:MM\n"
            "/deadline_deactivate ID\n"
            "/cancel_deadline ID — отмена своего создания в течение 10 минут\n"
            "/material_add https://... | Описание\n"
            "/materials [поиск]\n"
            "/material_correct ID | новый URL (необязательно) | новое описание (необязательно)\n"
            "/material_deactivate ID\n"
            "/cancel_material ID — отмена своего создания в течение 10 минут\n"
            "/call_all — позвать зарегистрированных участников с подтверждением"
            "\n/gosha_join — включить себя в групповые вызовы"
            "\n/gosha_leave — исключить себя из групповых вызовов"
        )

    @staticmethod
    def _format_csat_statistics(stats: dict) -> str:
        period = "за всё время" if stats.get("period") == "all" else f"за {stats.get('period') or 'текущий период'}"
        if not stats.get("count"):
            return f"CSAT по всем чатам {period}: ответов пока нет."

        def number(value: float) -> str:
            return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")

        return (
            f"CSAT по всем чатам {period}:\n"
            f"Средняя оценка: {number(float(stats['average']))} из 6\n"
            f"Медианная оценка: {number(float(stats['median']))} из 6\n"
            f"Количество ответов: {stats['count']}"
        )

    @staticmethod
    def _deadline_text(item: dict[str, Any]) -> str:
        due = str(item.get("due_local") or "").replace("T", " ")[:16]
        weekday = ""
        try:
            weekdays = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
            weekday = weekdays[datetime.fromisoformat(str(item.get("due_local"))).weekday()]
        except (TypeError, ValueError):
            pass
        zone = str(item.get("timezone_id") or "")
        context = ", ".join(value for value in (weekday, zone) if value)
        suffix = f" ({context})" if context else ""
        return f"• {item.get('title', 'Без названия')} — {due}{suffix} [{item.get('id', '?')}]"

    @staticmethod
    def _deadline_preview_lines(item: dict[str, Any], *, prefix: str = "") -> list[str]:
        due = str(item.get("due_local") or "").replace("T", " ")[:16]
        title = str(item.get("title") or "Без названия")
        weekday = str(item.get("weekday") or "")
        if not weekday:
            try:
                weekdays = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
                weekday = weekdays[datetime.fromisoformat(str(item.get("due_local"))).weekday()]
            except (TypeError, ValueError):
                weekday = "не определён"
        zone = str(item.get("timezone_id") or "не определён")
        lead = f"{prefix}: " if prefix else ""
        return [f"{lead}{title} — {due} ({weekday})", f"Часовой пояс: {zone}"]

    def _format_response(self, response: Response) -> str:
        data = response.data
        if data.get("deadlines") is not None:
            rows = data["deadlines"]
            return "Актуальные дедлайны:\n" + ("\n".join(self._deadline_text(x) for x in rows) if rows else "пока нет")
        if data.get("deadline"):
            return f"{response.message}\n{self._deadline_text(data['deadline'])}"
        if data.get("material"):
            item = data["material"]
            return f"{response.message}\n• {item['description']} — {item['url']} [{item['id']}]"
        if data.get("materials") is not None:
            rows = data["materials"]
            return response.message + ("\n" + "\n".join(f"• {x['description']} — {x['url']} [{x['id']}]" for x in rows) if rows else "")
        if response.status == "preview":
            lines = [response.message]
            if data.get("before") and data.get("after") and data["before"].get("url"):
                lines.append(f"До: {data['before']['description']} — {data['before']['url']}")
                lines.append(f"После: {data['after']['description']} — {data['after']['url']}")
                return "\n".join(lines)
            if data.get("title"):
                lines.extend(self._deadline_preview_lines(data))
            if data.get("before"):
                lines.extend(self._deadline_preview_lines(data["before"], prefix="До"))
                after = {
                    "title": data["before"].get("title"),
                    "due_local": data.get("due_local"),
                    "timezone_id": data.get("timezone_id") or data["before"].get("timezone_id"),
                    "weekday": data.get("weekday"),
                }
                lines.extend(self._deadline_preview_lines(after, prefix="После"))
            if data.get("url"):
                lines.append(f"{data.get('description', '')} — {data['url']}")
            if data.get("time_defaulted"):
                lines.append("Время не указано: 09:00 по умолчанию.")
            return "\n".join(lines)
        return response.message

    def _send_response(self, chat_id: str, response: Response) -> None:
        markup = self._undo_markup(response)
        pending = response.data.get("pending_id")
        if response.status == "preview" and pending:
            markup = {"inline_keyboard": [[
                {"text": "✅ Подтвердить", "callback_data": f"g:confirm:{pending}"},
                {"text": "Отменить", "callback_data": f"g:cancel:{pending}"},
            ]]}
        self._send(chat_id, self._format_response(response), reply_markup=markup)

    @staticmethod
    def _undo_markup(response: Response) -> dict[str, Any] | None:
        undo = response.data.get("undo")
        if response.status != "success" or not undo:
            return None
        return {"inline_keyboard": [[{
            "text": "↩️ Отменить — 10 минут",
            "callback_data": f"g:undo:{undo['object_type']}:{undo['object_id']}",
        }]]}

    def _send(
        self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self.api.call("sendMessage", payload)

    def _edit_response(self, chat_id: str, message_id: str, response: Response) -> None:
        markup = self._undo_markup(response) or {"inline_keyboard": []}
        self.api.call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": self._format_response(response)[:4096], "reply_markup": markup},
        )

    def deliver_due(self, *, limit: int = 20) -> int:
        now = self.now()
        self.store.recover_expired_deliveries(now)
        delivered = 0
        for job in self.store.claim_due_deliveries(now, limit=limit):
            if not self.store.mark_delivery_sending(job["job_key"], now):
                continue
            try:
                kind = job.get("kind") or job.get("type")
                reply_markup = self._csat_markup(job) if kind == "csat_survey" else None
                message = self._send(
                    job["chat_id"], self._format_delivery(job),
                    parse_mode="HTML" if kind == "call_all" else None,
                    reply_markup=reply_markup,
                )
            except TelegramAPIError as exc:
                if exc.delivery_unknown and hasattr(self.store, "mark_delivery_unknown"):
                    self.store.mark_delivery_unknown(job["job_key"], "telegram_transport_failure", now)
                else:
                    self.store.mark_delivery_failed(job["job_key"], str(exc), now, retryable=exc.retryable)
            else:
                self.store.mark_delivery_succeeded(job["job_key"], str(message["message_id"]), now)
                delivered += 1
        return delivered

    def schedule_monthly_csat(self) -> int:
        return self.store.ensure_monthly_csat(self.now())

    @staticmethod
    def _csat_markup(job: dict[str, Any]) -> dict[str, Any]:
        survey_id = str((job.get("payload") or {}).get("survey_id") or "")
        emojis = ("😡", "😞", "🙁", "😐", "🙂", "🤩")
        return {"inline_keyboard": [[
            {"text": emoji, "callback_data": f"g:csat:{survey_id}:{score}"}
            for score, emoji in enumerate(emojis, start=1)
        ]]}

    def _format_delivery(self, job: dict[str, Any]) -> str:
        kind, payload = job.get("kind") or job.get("type"), job.get("payload") or {}
        if kind == "csat_survey":
            return (
                "📊 Ежемесячный опрос Gosha\n"
                "Насколько вы довольны тем, как Gosha помогал в этом чате за последний месяц?\n\n"
                "Выберите подходящий смайлик — это займёт одну секунду."
            )
        if kind == "call_all":
            mentions = []
            for participant in payload.get("participants") or []:
                username = str(participant.get("username") or "")
                if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
                    mentions.append(f"@{username}")
                else:
                    user_id = html.escape(str(participant.get("user_id") or ""), quote=True)
                    name = html.escape(str(participant.get("display_name") or "Участник"))
                    mentions.append(f'<a href="tg://user?id={user_id}">{name}</a>')
            caller = html.escape(str(payload.get("caller_name") or "Участник"))
            return " ".join(mentions) + f"\n{caller} зовет всех в чат"
        if kind == "sunday_digest":
            deadlines = payload.get("deadlines") or []
            return "Дедлайны на следующую неделю:\n" + ("\n".join(self._deadline_text(x) for x in deadlines) if deadlines else "актуальных нет")
        deadline = payload.get("deadline") or {}
        labels = {"t24": "через сутки"}
        return f"Напоминание: дедлайн {labels.get(kind, 'скоро')}\n{self._deadline_text(deadline)}"


def run_polling(bot: TelegramBot, offset_file: OffsetFile, stop: threading.Event, *, poll_timeout: int = 25) -> None:
    offset = offset_file.load()
    bot.store.recover_expired_deliveries(bot.now())
    bot.schedule_monthly_csat()
    while not stop.is_set():
        try:
            updates = bot.api.call(
                "getUpdates",
                {"offset": offset, "timeout": poll_timeout, "allowed_updates": ["message", "callback_query"]},
            )
            for update in updates:
                bot.process_update(update)
                offset = int(update["update_id"]) + 1
                offset_file.save(offset)
            bot.schedule_monthly_csat()
            bot.deliver_due()
        except TelegramAPIError as exc:
            if not exc.retryable:
                raise
            stop.wait(1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gosha Telegram-first bot")
    parser.add_argument("--db", default=os.environ.get("GOSHA_DB", "gosha.db"))
    parser.add_argument("--provider", choices=("offline", "openai"), default=os.environ.get("GOSHA_PROVIDER", "offline"))
    parser.add_argument("--offset-file", default=os.environ.get("GOSHA_TELEGRAM_OFFSET_FILE"))
    parser.add_argument("--api-base", default=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"))
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        parser.error("TELEGRAM_BOT_TOKEN is required")
    owner_user_id = os.environ.get("GOSHA_OWNER_USER_ID", "").strip()
    if owner_user_id and not re.fullmatch(r"[1-9][0-9]{0,19}", owner_user_id):
        parser.error("GOSHA_OWNER_USER_ID must be a Telegram numeric user ID")
    database_url = os.environ.get("DATABASE_URL")
    store = build_store(database_url=database_url, sqlite_path=args.db)
    service = GoshaService(
        store, build_provider(args.provider),
        telemetry_hmac_key=telemetry_hmac_key(required=bool(database_url)),
    )
    api = TelegramAPI(token, base_url=args.api_base)
    bot = TelegramBot(api, service, owner_user_id=owner_user_id)
    offset_path = args.offset_file or (".gosha-telegram-offset" if database_url else f"{args.db}.telegram-offset")
    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    run_polling(bot, OffsetFile(offset_path), stop)


if __name__ == "__main__":
    main()
