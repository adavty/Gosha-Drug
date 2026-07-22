from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from .models import Actor, Deadline, Intent, Response, Role
from .provider import IntentProvider, OfflineProvider, ProviderError
from .repository import Repository
from .store import Store
from .time_rules import TimeRuleError, normalize_due, reminder_schedule, resolve_user_dates
from .url_rules import URLRuleError, normalize_material_url

WEEKDAYS_RU = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


class GoshaService:
    def __init__(
        self, store: Repository | None = None, provider: IntentProvider | None = None,
        *, telemetry_hmac_key: str | bytes | None = None,
    ):
        self.store = store or Store()
        self.provider = provider or OfflineProvider()
        configured_key = telemetry_hmac_key or os.environ.get("GOSHA_TELEMETRY_HMAC_KEY")
        if isinstance(configured_key, str):
            configured_key = configured_key.encode("utf-8")
        # Local/offline runs receive an unlinkable process-ephemeral key. A live
        # deployment must inject a stable, rotatable deployment key as a secret.
        self._telemetry_hmac_key = configured_key or secrets.token_bytes(32)

    @staticmethod
    def _entry_allowed(text: str, entry_point: str) -> bool:
        return entry_point in {"mention", "command", "button", "bot_reply"} and ("@gosha" in text.lower() or text.startswith("/") or entry_point in {"button", "bot_reply"})

    @staticmethod
    def _title_tokens(value: str) -> set[str]:
        stop = {
            "дедлайн", "дедлайна", "срок", "срока", "новый", "новая", "новое",
            "по", "на", "для", "про", "там", "его", "ее", "её",
        }
        words = re.findall(r"[0-9a-zа-яё]+", value.casefold().replace("ё", "е"))
        return {word[:6] if len(word) > 6 else word for word in words if len(word) > 1 and word not in stop}

    @classmethod
    def _grounded_target(cls, normalized: str, evidence: str) -> bool:
        normalized_tokens = cls._title_tokens(normalized)
        evidence_tokens = cls._title_tokens(evidence)
        if not normalized_tokens or not evidence_tokens:
            return False
        return len(normalized_tokens & evidence_tokens) / max(len(normalized_tokens), len(evidence_tokens)) >= 0.6

    def _deadline_title_matches(self, chat_id: str, target: str) -> list[Deadline]:
        normalized = " ".join(re.findall(r"[0-9a-zа-яё]+", target.casefold().replace("ё", "е")))
        target_tokens = self._title_tokens(target)
        ranked: list[tuple[float, Deadline]] = []
        for deadline in self.store.list_deadlines(chat_id):
            title_normalized = " ".join(re.findall(r"[0-9a-zа-яё]+", deadline.title.casefold().replace("ё", "е")))
            if normalized == title_normalized:
                ranked.append((1.0, deadline))
                continue
            if len(target_tokens) < 2:
                continue
            title_tokens = self._title_tokens(deadline.title)
            if not title_tokens:
                continue
            overlap = len(target_tokens & title_tokens)
            score = 0.7 * (overlap / len(target_tokens)) + 0.3 * (overlap / len(title_tokens))
            if score >= 0.8:
                ranked.append((score, deadline))
        ranked.sort(key=lambda item: (-item[0], item[1].due_utc, item[1].id))
        return [deadline for _, deadline in ranked]

    def _event(self, name: str, chat_id: str, actor: Actor, result: str, correlation: str, now: datetime) -> None:
        chat_key = hmac.new(self._telemetry_hmac_key, f"chat:{chat_id}".encode(), hashlib.sha256).hexdigest()[:16]
        user_key = hmac.new(self._telemetry_hmac_key, f"user:{actor.user_id}".encode(), hashlib.sha256).hexdigest()[:16]
        with self.store.lock:
            self.store.conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)", (uuid.uuid4().hex, name, chat_key, user_key, result, correlation, now.isoformat()))
            self.store.conn.commit()

    def _stopped(self, chat_id: str) -> bool:
        chat = self.store.chat(chat_id)
        return bool(chat and not chat["enabled"])

    @staticmethod
    def _scheduled_sends_allowed(conn, chat_id: str) -> bool:
        chat = conn.execute("SELECT enabled FROM chats WHERE chat_id=?", (chat_id,)).fetchone()
        setting = conn.execute("SELECT value FROM runtime_settings WHERE key='global_sends_enabled'").fetchone()
        return bool(chat and chat["enabled"] and setting and setting["value"] == "1")

    @staticmethod
    def _rebuild_digest_jobs(conn, chat_id: str, now: datetime) -> None:
        conn.execute("UPDATE reminders SET status='cancelled' WHERE chat_id=? AND type='sunday_digest' AND status IN ('scheduled','retry_wait','claimed')", (chat_id,))
        rows = conn.execute("SELECT due_local, timezone_id FROM deadlines WHERE chat_id=? AND status='active'", (chat_id,)).fetchall()
        for row in rows:
            for kind, scheduled in reminder_schedule(row["due_local"], row["timezone_id"], now.isoformat()):
                if kind != "sunday_digest":
                    continue
                job_key = f"{chat_id}:*:sunday_digest:{scheduled}"
                status = "scheduled" if GoshaService._scheduled_sends_allowed(conn, chat_id) else "cancelled"
                conn.execute(
                    "INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,available_at,last_error) "
                    "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_key) DO UPDATE SET status=excluded.status,"
                    "available_at=excluded.available_at,last_error=excluded.last_error "
                    "WHERE reminders.status IN ('scheduled','retry_wait','claimed','cancelled')",
                    (job_key, chat_id, "*", kind, scheduled, status, scheduled, None if status == "scheduled" else "scheduled_sends_stopped"),
                )

    def preview_material(self, chat_id: str, actor: Actor, url: str, description: str, now: datetime | None = None) -> Response:
        now = now or datetime.now(timezone.utc)
        if self._stopped(chat_id):
            return Response("stopped", "Gosha остановлен для этого чата.")
        if not self.store.chat(chat_id):
            return Response("setup_required", "Администратор должен настроить чат.")
        description = description.strip()
        if not description:
            return Response("clarification", "Добавьте описание материала.")
        if len(description) > 500:
            return Response("rejected", "Описание материала длиннее 500 символов.")
        try:
            normalized = normalize_material_url(url)
        except URLRuleError as exc:
            return Response("rejected", f"Материал не сохранён: {exc}.")
        duplicate = self.store.find_material_by_canonical_url(chat_id, normalized.canonical_url)
        if duplicate:
            return Response("possible_duplicate", "Эта ссылка уже сохранена в этом чате.", {"material": duplicate})
        payload = {
            "url": normalized.display_url,
            "canonical_url": normalized.canonical_url,
            "domain": normalized.domain,
            "description": description,
        }
        pending = self.store.create_pending(chat_id, actor.user_id, "material_create", payload, now)
        return Response(
            "preview",
            "Проверьте материал. Только этот чат; содержимое страницы не читалось.",
            {"pending_id": pending, **payload, "scope": "chat_only", "content_fetched": False},
        )

    def list_materials(self, chat_id: str, query: str = "") -> Response:
        if not self.store.chat(chat_id):
            return Response("setup_required", "Администратор должен настроить чат.")
        items = self.store.search_materials(chat_id, query) if query.strip() else self.store.list_materials(chat_id)
        return Response("ok" if items else "not_found", "Материалы этого чата." if items else "В этом чате ничего не найдено.", {"materials": items})

    def preview_material_correct(
        self, chat_id: str, actor: Actor, material_id: str, *, url: str | None = None,
        description: str | None = None, now: datetime | None = None,
    ) -> Response:
        now = now or datetime.now(timezone.utc)
        if actor.role not in {Role.STEWARD, Role.ADMIN}:
            return Response("forbidden", "Требуется подтверждённая роль администратора Telegram-чата.")
        current = self.store.get_material(chat_id, material_id)
        if not current or current["status"] != "active":
            return Response("not_found", "Материал этого чата не найден.")
        if url is None and description is None:
            return Response("clarification", "Укажите новый URL или описание.")
        try:
            normalized = normalize_material_url(url or current["url"])
        except URLRuleError as exc:
            return Response("rejected", f"Исправление отклонено: {exc}.")
        new_description = current["description"] if description is None else description.strip()
        if not new_description or len(new_description) > 500:
            return Response("rejected", "Описание обязательно и должно быть не длиннее 500 символов.")
        duplicate = self.store.find_material_by_canonical_url(chat_id, normalized.canonical_url)
        if duplicate and duplicate["id"] != material_id:
            return Response("possible_duplicate", "Такой URL уже сохранён в этом чате.", {"material": duplicate})
        after = {**current, "url": normalized.display_url, "canonical_url": normalized.canonical_url, "domain": normalized.domain, "description": new_description}
        payload = {"material_id": material_id, "before": current, "after": after, "expected_version": current["version"]}
        pending = self.store.create_pending(chat_id, actor.user_id, "material_correct", payload, now)
        return Response("preview", "Проверьте before/after. Содержимое страницы не читалось.", {"pending_id": pending, **payload})

    def preview_material_deactivate(self, chat_id: str, actor: Actor, material_id: str, now: datetime | None = None) -> Response:
        now = now or datetime.now(timezone.utc)
        if actor.role not in {Role.STEWARD, Role.ADMIN}:
            return Response("forbidden", "Требуется подтверждённая роль администратора Telegram-чата.")
        current = self.store.get_material(chat_id, material_id)
        if not current or current["status"] != "active":
            return Response("not_found", "Материал этого чата не найден.")
        payload = {"material_id": material_id, "before": current, "expected_version": current["version"]}
        pending = self.store.create_pending(chat_id, actor.user_id, "material_deactivate", payload, now)
        return Response("preview", "После подтверждения материал исчезнет из каталога и поиска; audit сохранится.", {"pending_id": pending, "material": current})

    def cancel_pending(self, chat_id: str, actor: Actor, pending_id: str, now: datetime | None = None) -> Response:
        now = now or datetime.now(timezone.utc)
        with self.store.tx() as conn:
            row = conn.execute(
                "SELECT id FROM pending WHERE id=? AND chat_id=? AND actor_id=? AND consumed=0 AND expires_at>?",
                (pending_id, chat_id, actor.user_id, now.isoformat()),
            ).fetchone()
            if not row:
                return Response("rejected", "Preview не найден, истёк, уже закрыт или принадлежит другому контексту.")
            result = conn.execute("UPDATE pending SET consumed=1 WHERE id=? AND consumed=0", (pending_id,))
        return Response("cancelled", "Действие отменено без изменения общего состояния.") if result.rowcount == 1 else Response("rejected", "Preview уже закрыт.")

    def handle(self, chat_id: str, actor: Actor, text: str, entry_point: str = "mention", now: datetime | None = None) -> Response:
        now = now or datetime.now(timezone.utc)
        correlation = uuid.uuid4().hex
        if self._stopped(chat_id):
            return Response("stopped", "Gosha остановлен для этого чата.")
        if not self._entry_allowed(text, entry_point):
            self._event("message_ignored", chat_id, actor, "ignored", correlation, now)
            return Response("ignored", "Обычная переписка не обрабатывается.")
        chat = self.store.chat(chat_id)
        if not chat:
            return Response("setup_required", "Администратор должен выбрать IANA timezone.")
        if any(x in text.lower() for x in ("игнорируй правила", "system prompt", "чужой чат", "чужой дедлайн", "чужой материал")):
            self._event("injection_blocked", chat_id, actor, "blocked", correlation, now)
            return Response("blocked", "Запрос отклонён защитным контуром.")
        deterministic_command = bool(re.match(
            r"^/(?:deadline_(?:add|correct|deactivate|get)|deadlines|material_(?:add|correct|deactivate)|materials|call_all|cancel)\b",
            text,
            re.I,
        ))
        offline = OfflineProvider()
        try:
            # Do not hold a write transaction during a remote model call.
            # Confirm still rechecks the durable write gate transactionally.
            llm_enabled = self.store.global_llm_enabled()
            result = offline.parse(text) if deterministic_command or not llm_enabled else self.provider.parse(text)
        except ProviderError:
            result = offline.parse(text)
            if result.intent == Intent.UNKNOWN:
                return Response("fallback", "AI временно недоступен. Формальные команды продолжают работать.")
        # A model may classify intent and extract slots, but it cannot invent the
        # safety-critical values that authorize or parameterize a write.
        try:
            literal_dates = resolve_user_dates(text, chat["timezone_id"], now)
        except TimeRuleError as exc:
            return Response("rejected", f"Не удалось разобрать дату: {exc}.")
        literal_times = list(dict.fromkeys(re.findall(r"(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d(?!\d)", text)))
        if result.intent in {Intent.ADD, Intent.CORRECT}:
            if len(literal_dates) > 1 or len(literal_times) > 1:
                return Response("clarification", "Укажите одну дату и одно время для безопасного preview.")
            if literal_dates:
                result.slots["date"] = literal_dates[0]
            elif result.slots.get("date"):
                evidence = str(result.slots.get("date_evidence") or "").strip()
                # The model may normalize a typo, but the source phrase must be
                # copied verbatim from this request and is verified here.
                if not evidence or evidence.casefold() not in text.casefold():
                    return Response("clarification", "Не удалось однозначно определить дату. Уточните день и месяц.")
                try:
                    provider_dates = resolve_user_dates(str(result.slots["date"]), chat["timezone_id"], now)
                except TimeRuleError as exc:
                    return Response("rejected", f"Не удалось разобрать дату: {exc}.")
                if len(provider_dates) != 1:
                    return Response("clarification", "Не удалось однозначно определить дату. Уточните день и месяц.")
                result.slots["date"] = provider_dates[0]
            if literal_times:
                result.slots["time"] = literal_times[0]
            elif result.slots.get("time"):
                evidence = str(result.slots.get("time_evidence") or "").strip()
                candidate = str(result.slots["time"])
                if not evidence:
                    # No source span means the candidate is ungrounded. Ignore
                    # it and use the explicit default/preserve-time policy.
                    result.slots["time"] = None
                elif evidence.casefold() not in text.casefold() or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", candidate):
                    return Response("clarification", "Не удалось однозначно определить время. Уточните его, например «18:00».")
                else:
                    result.slots["time"] = candidate
            elif result.slots.get("time_evidence"):
                return Response("clarification", "Не удалось однозначно определить время. Уточните его, например «18:00».")
            else:
                # Ignore a hallucinated time: ADD uses the explicit 09:00
                # default, while CORRECT preserves the stored time.
                result.slots["time"] = None
        if result.intent == Intent.CORRECT and actor.role not in {Role.STEWARD, Role.ADMIN}:
            return Response("forbidden", "Требуется подтверждённая роль администратора Telegram-чата.")
        if result.intent in {Intent.CORRECT, Intent.DEACTIVATE}:
            deadline_id = result.slots.get("deadline_id")
            literal_id = bool(deadline_id and re.search(rf"(?<![\w-]){re.escape(deadline_id)}(?![\w-])", text, re.IGNORECASE))
            if result.intent == Intent.CORRECT and not literal_id:
                target = str(result.slots.get("target_title") or "").strip()
                evidence = str(result.slots.get("target_evidence") or "").strip()
                if not target or not evidence or evidence.casefold() not in text.casefold() or not self._grounded_target(target, evidence):
                    return Response("clarification", "Какой дедлайн изменить? Укажите его название или ID.")
                matches = self._deadline_title_matches(chat_id, target)
                if not matches:
                    return Response("not_found", "Не нашёл активный дедлайн с таким названием в этом чате.")
                if len(matches) > 1:
                    choices = "\n".join(f"• {item.title} [{item.id}]" for item in matches[:5])
                    return Response("clarification", f"Нашёл несколько подходящих дедлайнов:\n{choices}\nУкажите нужный ID.")
                result.slots["deadline_id"] = matches[0].id
            elif not literal_id:
                return Response("clarification", "Укажите ID изменяемого дедлайна прямо в запросе.")
        material_write_intents = {Intent.MATERIAL_SAVE, Intent.MATERIAL_CORRECT, Intent.MATERIAL_DEACTIVATE}
        if result.intent in material_write_intents:
            literal_urls = [item.rstrip(".,;:!?)]") for item in re.findall(r"https?://[^\s|<>\"]+", text, flags=re.I)]
            literal_urls = list(dict.fromkeys(literal_urls))
            if len(literal_urls) > 1:
                return Response("clarification", "Укажите один URL для безопасного preview.")
            if result.intent == Intent.MATERIAL_SAVE:
                if len(literal_urls) != 1:
                    return Response("clarification", "Укажите сохраняемый URL прямо в запросе.")
                result.slots["url"] = literal_urls[0]
            elif result.intent == Intent.MATERIAL_CORRECT:
                if literal_urls:
                    result.slots["url"] = literal_urls[0]
                elif result.slots.get("url"):
                    return Response("clarification", "Новый URL должен быть указан прямо в запросе.")
            if result.intent in {Intent.MATERIAL_CORRECT, Intent.MATERIAL_DEACTIVATE}:
                material_id = result.slots.get("material_id")
                if not material_id or not re.search(rf"(?<![\w-]){re.escape(material_id)}(?![\w-])", text, re.I):
                    return Response("clarification", "Укажите ID изменяемого материала прямо в запросе.")
        self._event("intent_classified", chat_id, actor, result.intent.value, correlation, now)
        if result.usage is not None:
            # Operational AI telemetry contains counts and latency only. Raw
            # messages, extracted slots, chat IDs and user IDs are not stored.
            usage_payload = {
                "provider": result.provider,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cached_input_tokens": result.usage.cached_input_tokens,
                "reasoning_tokens": result.usage.reasoning_tokens,
                "latency_ms": result.usage.latency_ms,
            }
            self._event(
                "llm_usage", chat_id, actor,
                json.dumps(usage_payload, ensure_ascii=True, separators=(",", ":")),
                correlation, now,
            )
        if result.intent == Intent.LIST:
            items = [d.to_dict() for d in self.store.list_deadlines(chat_id)]
            return Response("ok", "Актуальные дедлайны." if items else "Активных дедлайнов нет.", {"deadlines": items})
        if result.intent == Intent.QUESTION:
            deadline = self.store.get_deadline(chat_id, result.slots.get("deadline_id") or "")
            matches = [deadline] if deadline else self.store.find_deadlines(chat_id, result.slots.get("query") or "")
            matches = [item for item in matches if item and item.status == "active"]
            if not matches:
                return Response("not_found", "Дедлайн этого чата не найден.")
            if len(matches) > 1:
                return Response("clarification", "Нашёл несколько дедлайнов — выберите ID.", {"matches": [d.to_dict() for d in matches]})
            return Response("ok", "Ответ построен только из сохранённого состояния.", {"deadline": matches[0].to_dict()})
        if result.intent == Intent.ADD:
            return self._preview_add(chat_id, actor, result.slots, now)
        if result.intent == Intent.CORRECT:
            return self._preview_correct(chat_id, actor, result.slots, now)
        if result.intent == Intent.DEACTIVATE:
            return self._preview_deactivate(chat_id, actor, result.slots, now)
        if result.intent == Intent.CANCEL_LAST and str(result.provider).startswith("offline-rules-v1"):
            return self.cancel_last(chat_id, actor, now)
        if result.intent == Intent.MATERIAL_SAVE:
            return self.preview_material(chat_id, actor, result.slots.get("url") or "", result.slots.get("description") or "", now)
        if result.intent == Intent.MATERIAL_LIST:
            return self.list_materials(chat_id)
        if result.intent == Intent.MATERIAL_FIND:
            query = result.slots.get("query") or ""
            return self.list_materials(chat_id, query) if query else Response("clarification", "Что искать в материалах?")
        if result.intent == Intent.MATERIAL_CORRECT:
            return self.preview_material_correct(
                chat_id,
                actor,
                result.slots.get("material_id") or "",
                url=result.slots.get("url"),
                description=result.slots.get("description"),
                now=now,
            )
        if result.intent == Intent.MATERIAL_DEACTIVATE:
            return self.preview_material_deactivate(chat_id, actor, result.slots.get("material_id") or "", now)
        if result.intent == Intent.CALL_ALL:
            return self._preview_call_all(chat_id, actor, now)
        return Response("clarification", "Я работаю с общими дедлайнами и URL-материалами этого чата.")

    def _preview_call_all(self, chat_id: str, actor: Actor, now: datetime) -> Response:
        if self.store.recent_call_all(chat_id, now - timedelta(minutes=10)):
            return Response("rate_limited", "Всех уже звали менее 10 минут назад. Попробуйте позже.")
        participants = [item for item in self.store.list_participants(chat_id) if item["user_id"] != actor.user_id]
        if not participants:
            return Response(
                "clarification",
                "Пока некого тегать: участники должны написать в чат после подключения Gosha или выполнить /gosha_join.",
            )
        if len(participants) > 30:
            return Response("rejected", "В реестре больше 30 участников; массовый вызов ограничен небольшими учебными группами.")
        caller_name = " ".join((actor.display_name or f"Участник {actor.user_id[-4:]}").split())[:80]
        payload = {
            "caller_name": caller_name,
            "participant_ids": [item["user_id"] for item in participants],
            "participant_count": len(participants),
        }
        pending = self.store.create_pending(chat_id, actor.user_id, "call_all", payload, now)
        return Response(
            "preview",
            f"Позвать всех известных участников? Будут отмечены: {len(participants)}. Повторный вызов доступен через 10 минут.",
            {"pending_id": pending, "participant_count": len(participants), "call_all_preview": True},
        )

    def _preview_add(self, chat_id: str, actor: Actor, slots: dict, now: datetime) -> Response:
        title, date = slots.get("title"), slots.get("date")
        if not title:
            return Response("clarification", "Как называется дедлайн?")
        if not date:
            return Response("clarification", "Укажите дату, например «27 июля», «завтра» или «2026-07-27».")
        timezone_id = self.store.chat(chat_id)["timezone_id"]
        try:
            local, utc, defaulted = normalize_due(date, slots.get("time"), timezone_id, now)
        except TimeRuleError as exc:
            return Response("rejected", f"Дедлайн не создан: {exc}.")
        weekday = WEEKDAYS_RU[datetime.fromisoformat(local).weekday()]
        payload = {"title": title[:200], "due_local": local, "due_utc": utc, "timezone_id": timezone_id, "weekday": weekday}
        duplicate = next((d for d in self.store.list_deadlines(chat_id) if d.title.casefold() == payload["title"].casefold() and d.due_utc == utc), None)
        if duplicate:
            return Response("possible_duplicate", "Такой дедлайн уже существует; используйте сохранённый объект.", {"deadline": duplicate.to_dict()})
        pending = self.store.create_pending(chat_id, actor.user_id, "create", payload, now)
        return Response("preview", "Проверьте дедлайн и подтвердите создание.", {"pending_id": pending, **payload, "time_defaulted": defaulted})

    def _preview_correct(self, chat_id: str, actor: Actor, slots: dict, now: datetime) -> Response:
        if actor.role not in {Role.STEWARD, Role.ADMIN}:
            return Response("forbidden", "Требуется подтверждённая роль администратора Telegram-чата.")
        deadline_id = slots.get("deadline_id")
        current = self.store.get_deadline(chat_id, deadline_id or "")
        if not current:
            return Response("not_found", "Дедлайн этого чата не найден.")
        date = slots.get("date") or current.due_local[:10]
        time_value = slots.get("time") or current.due_local[11:16]
        try:
            local, utc, _ = normalize_due(date, time_value, current.timezone_id, now)
        except TimeRuleError as exc:
            return Response("rejected", f"Исправление отклонено: {exc}.")
        payload = {
            "deadline_id": current.id, "due_local": local, "due_utc": utc,
            "timezone_id": current.timezone_id, "before": current.to_dict(),
            "expected_version": current.version,
            "weekday": WEEKDAYS_RU[datetime.fromisoformat(local).weekday()],
        }
        pending = self.store.create_pending(chat_id, actor.user_id, "correct", payload, now)
        return Response("preview", "Проверьте before/after и подтвердите изменение.", {"pending_id": pending, **payload})

    def _preview_deactivate(self, chat_id: str, actor: Actor, slots: dict, now: datetime) -> Response:
        if actor.role not in {Role.STEWARD, Role.ADMIN}:
            return Response("forbidden", "Требуется подтверждённая роль администратора Telegram-чата.")
        current = self.store.get_deadline(chat_id, slots.get("deadline_id") or "")
        if not current:
            return Response("not_found", "Дедлайн этого чата не найден.")
        pending = self.store.create_pending(chat_id, actor.user_id, "deactivate", {"deadline_id": current.id, "before": current.to_dict(), "expected_version": current.version}, now)
        return Response("preview", "После подтверждения будущие напоминания будут отменены.", {"pending_id": pending, "deadline": current.to_dict()})

    def confirm(self, chat_id: str, actor: Actor, pending_id: str, idempotency_key: str, now: datetime | None = None) -> Response:
        now = now or datetime.now(timezone.utc)
        scoped_key = hashlib.sha256(f"{chat_id}:{actor.user_id}:{idempotency_key}".encode()).hexdigest()
        fingerprint = hashlib.sha256(f"confirm:{chat_id}:{actor.user_id}:{pending_id}".encode()).hexdigest()
        if not self.store.global_writes_enabled() or self._stopped(chat_id):
            return Response("stopped", "Изменяющие операции остановлены kill switch.")
        correlation = uuid.uuid4().hex
        with self.store.tx() as conn:
            # Durable gate is re-read and locked inside the same transaction as
            # consume+commit, closing the stop-after-preview race.
            if not self.store.runtime_setting_enabled("global_writes_enabled", conn=conn, lock=True):
                return Response("stopped", "Изменяющие операции остановлены kill switch.")
            self.store.acquire_idempotency_lock(conn, scoped_key)
            cached = conn.execute("SELECT request_fingerprint,response_json FROM idempotency WHERE key=?", (scoped_key,)).fetchone()
            if cached:
                if cached["request_fingerprint"] != fingerprint:
                    return Response("idempotency_conflict", "Этот idempotency key уже связан с другим запросом.")
                return Response(**json.loads(cached["response_json"]))
            row = self.store.pending_for_update(conn, pending_id, chat_id, actor.user_id, now)
            if not row:
                return Response("rejected", "Preview не найден, истёк, уже использован или принадлежит другому контексту.")
            consumed = conn.execute("UPDATE pending SET consumed=1 WHERE id=? AND consumed=0", (pending_id,))
            if consumed.rowcount != 1:
                return Response("rejected", "Preview уже использован.")
            payload = json.loads(row["payload"])
            action = row["action"]
            if action == "create":
                object_type = "deadline"
                existing = conn.execute(
                    "SELECT * FROM deadlines WHERE chat_id=? AND lower(title)=lower(?) AND due_utc=? AND status='active' LIMIT 1",
                    (chat_id, payload["title"], payload["due_utc"]),
                ).fetchone()
                if existing:
                    return Response("possible_duplicate", "Такой дедлайн уже существует; повторная запись не создана.", {"deadline": dict(existing)})
                object_id = uuid.uuid4().hex[:8]
                deadline = Deadline(object_id, chat_id, payload["title"], payload["due_local"], payload["timezone_id"], payload["due_utc"], actor.user_id, "active", now.isoformat())
                conn.execute("INSERT INTO deadlines VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(deadline.to_dict().values()))
                after, before = deadline.to_dict(), None
            elif action == "correct":
                object_type = "deadline"
                current = self.store.get_deadline(chat_id, payload["deadline_id"])
                if not current or actor.role not in {Role.STEWARD, Role.ADMIN}:
                    return Response("rejected", "Объект недоступен или роль изменилась.")
                if current.version != payload["expected_version"]:
                    return Response("stale_preview", "Дедлайн изменился после preview; запросите новый preview.")
                before, object_id = current.to_dict(), current.id
                updated = conn.execute("UPDATE deadlines SET due_local=?, due_utc=?, version=version+1 WHERE chat_id=? AND id=? AND version=?", (payload["due_local"], payload["due_utc"], chat_id, current.id, payload["expected_version"]))
                if updated.rowcount != 1:
                    return Response("stale_preview", "Дедлайн изменился после preview; запросите новый preview.")
                after = self.store.get_deadline(chat_id, current.id).to_dict()
            elif action == "deactivate":
                object_type = "deadline"
                current = self.store.get_deadline(chat_id, payload["deadline_id"])
                if not current or actor.role not in {Role.STEWARD, Role.ADMIN}:
                    return Response("rejected", "Объект недоступен или роль изменилась.")
                if current.version != payload["expected_version"]:
                    return Response("stale_preview", "Дедлайн изменился после preview; запросите новый preview.")
                before, object_id = current.to_dict(), current.id
                updated = conn.execute("UPDATE deadlines SET status='inactive', version=version+1 WHERE chat_id=? AND id=? AND version=?", (chat_id, current.id, payload["expected_version"]))
                if updated.rowcount != 1:
                    return Response("stale_preview", "Дедлайн изменился после preview; запросите новый preview.")
                after = self.store.get_deadline(chat_id, current.id).to_dict()
            elif action == "call_all":
                object_type = "call_all"
                object_id = uuid.uuid4().hex[:12]
                self.store.acquire_idempotency_lock(conn, f"call-all:{chat_id}")
                recent = conn.execute(
                    "SELECT 1 FROM reminders WHERE chat_id=? AND type='call_all' AND scheduled_for>=? LIMIT 1",
                    (chat_id, (now - timedelta(minutes=10)).isoformat()),
                ).fetchone()
                if recent:
                    return Response("rate_limited", "Всех уже звали менее 10 минут назад. Попробуйте позже.")
                allowed_ids = set(payload["participant_ids"])
                participants = [
                    item for item in self.store.list_participants(chat_id)
                    if item["user_id"] in allowed_ids and item["user_id"] != actor.user_id
                ]
                if not participants:
                    return Response("rejected", "После preview не осталось активных участников для вызова.")
                if not self._scheduled_sends_allowed(conn, chat_id):
                    return Response("stopped", "Отправка сообщений остановлена оператором.")
                job_key = f"{chat_id}:call_all:{object_id}"
                delivery_payload = {"caller_name": payload["caller_name"], "participants": participants}
                conn.execute(
                    "INSERT INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,payload_json,attempt_count,max_attempts,available_at) "
                    "VALUES(?,?,?,'call_all',?,'scheduled',?,0,3,?)",
                    (job_key, chat_id, "*", now.isoformat(), json.dumps(delivery_payload, ensure_ascii=False), now.isoformat()),
                )
                before = None
                after = {"job_key": job_key, "participant_count": len(participants), "status": "scheduled"}
            elif action == "material_create":
                object_type = "material"
                self.store.acquire_idempotency_lock(conn, f"material-url:{chat_id}:{payload['canonical_url']}")
                existing = conn.execute(
                    "SELECT * FROM materials WHERE chat_id=? AND canonical_url=? AND status='active'",
                    (chat_id, payload["canonical_url"]),
                ).fetchone()
                if existing:
                    return Response("possible_duplicate", "Эта ссылка уже сохранена в этом чате.", {"material": dict(existing)})
                object_id = uuid.uuid4().hex[:10]
                inserted = conn.execute(
                    "INSERT INTO materials(id,chat_id,description,url,canonical_url,domain,author_id,status,created_at,version) "
                    "VALUES(?,?,?,?,?,?,?,'active',?,1) ON CONFLICT(chat_id,canonical_url) DO NOTHING",
                    (object_id, chat_id, payload["description"], payload["url"], payload["canonical_url"], payload["domain"], actor.user_id, now.isoformat()),
                )
                if inserted.rowcount != 1:
                    duplicate = conn.execute(
                        "SELECT * FROM materials WHERE chat_id=? AND canonical_url=?",
                        (chat_id, payload["canonical_url"]),
                    ).fetchone()
                    return Response("possible_duplicate", "Эта ссылка уже сохранена в этом чате.", {"material": dict(duplicate)})
                after = dict(conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, object_id)).fetchone())
                before = None
            elif action == "material_correct":
                object_type = "material"
                current = conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, payload["material_id"])).fetchone()
                if not current or actor.role not in {Role.STEWARD, Role.ADMIN}:
                    return Response("rejected", "Объект недоступен или роль изменилась.")
                if current["version"] != payload["expected_version"]:
                    return Response("stale_preview", "Материал изменился после preview; запросите новый preview.")
                before, object_id = dict(current), current["id"]
                target = payload["after"]
                self.store.acquire_idempotency_lock(conn, f"material-url:{chat_id}:{target['canonical_url']}")
                duplicate = conn.execute(
                    "SELECT id FROM materials WHERE chat_id=? AND canonical_url=? AND status='active' AND id<>?",
                    (chat_id, target["canonical_url"], object_id),
                ).fetchone()
                if duplicate:
                    return Response("possible_duplicate", "Такой URL уже сохранён в этом чате.", {"material_id": duplicate["id"]})
                updated = conn.execute(
                    "UPDATE materials SET description=?,url=?,canonical_url=?,domain=?,version=version+1 "
                    "WHERE chat_id=? AND id=? AND version=?",
                    (target["description"], target["url"], target["canonical_url"], target["domain"], chat_id, object_id, payload["expected_version"]),
                )
                if updated.rowcount != 1:
                    return Response("stale_preview", "Материал изменился после preview; запросите новый preview.")
                after = dict(conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, object_id)).fetchone())
            elif action == "material_deactivate":
                object_type = "material"
                current = conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, payload["material_id"])).fetchone()
                if not current or actor.role not in {Role.STEWARD, Role.ADMIN}:
                    return Response("rejected", "Объект недоступен или роль изменилась.")
                if current["version"] != payload["expected_version"]:
                    return Response("stale_preview", "Материал изменился после preview; запросите новый preview.")
                before, object_id = dict(current), current["id"]
                updated = conn.execute(
                    "UPDATE materials SET status='inactive',version=version+1 WHERE chat_id=? AND id=? AND version=?",
                    (chat_id, object_id, payload["expected_version"]),
                )
                if updated.rowcount != 1:
                    return Response("stale_preview", "Материал изменился после preview; запросите новый preview.")
                after = dict(conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, object_id)).fetchone())
            else:
                raise ValueError("unknown_action")
            if object_type == "deadline":
                conn.execute(
                    "UPDATE reminders SET status='cancelled' WHERE chat_id=? AND deadline_id=? AND type='t24' "
                    "AND status IN ('scheduled','retry_wait','claimed')", (chat_id, object_id),
                )
                if after["status"] == "active":
                    for kind, scheduled in reminder_schedule(after["due_local"], after["timezone_id"], now.isoformat()):
                        if kind == "sunday_digest":
                            continue
                        job_key = f"{chat_id}:{object_id}:{kind}:{scheduled}"
                        status = "scheduled" if self._scheduled_sends_allowed(conn, chat_id) else "cancelled"
                        conn.execute(
                            "INSERT OR IGNORE INTO reminders(job_key,chat_id,deadline_id,type,scheduled_for,status,available_at,last_error) "
                            "VALUES(?,?,?,?,?,?,?,?)",
                            (job_key, chat_id, object_id, kind, scheduled, status, scheduled, None if status == "scheduled" else "scheduled_sends_stopped"),
                        )
                self._rebuild_digest_jobs(conn, chat_id, now)
            conn.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, chat_id, actor.user_id, action, object_id, json.dumps(before, ensure_ascii=False) if before else None, json.dumps(after, ensure_ascii=False), correlation, now.isoformat()))
            response_data = {object_type: after}
            if action in {"create", "material_create"}:
                response_data["undo"] = {"object_type": object_type, "object_id": object_id, "window_seconds": 600}
            message = "Вызов подтверждён и поставлен в очередь отправки." if action == "call_all" else "Изменение сохранено после подтверждения."
            response = Response("success", message, response_data)
            conn.execute("INSERT INTO idempotency(key,request_fingerprint,response_json,created_at) VALUES(?,?,?,?)", (scoped_key, fingerprint, json.dumps(response.to_dict(), ensure_ascii=False), now.isoformat()))
        return response

    def cancel_created(self, chat_id: str, actor: Actor, object_type: str, object_id: str, now: datetime | None = None) -> Response:
        """Undo one actor-owned creation by visible object ID within 10 minutes."""
        now = now or datetime.now(timezone.utc)
        if not self.store.global_writes_enabled() or self._stopped(chat_id):
            return Response("stopped", "Изменяющие операции остановлены kill switch.")
        if object_type not in {"deadline", "material"}:
            return Response("rejected", "Неизвестный тип объекта.")
        table = "deadlines" if object_type == "deadline" else "materials"
        with self.store.tx() as conn:
            if not self.store.runtime_setting_enabled("global_writes_enabled", conn=conn, lock=True):
                return Response("stopped", "Изменяющие операции остановлены kill switch.")
            row = conn.execute(
                f"SELECT * FROM {table} WHERE chat_id=? AND id=? AND author_id=?",
                (chat_id, object_id, actor.user_id),
            ).fetchone()
            if not row or (now - datetime.fromisoformat(row["created_at"])).total_seconds() > 600:
                return Response("not_found", "Объект не найден у этого автора или 10-минутное окно истекло.")
            before = dict(row)
            if row["status"] == "cancelled":
                return Response("success", "Создание уже отменено.", {f"{object_type}_id": object_id, "idempotent_replay": True})
            if row["status"] != "active":
                return Response("rejected", "Отменить можно только активное создание.")
            conn.execute(f"UPDATE {table} SET status='cancelled',version=version+1 WHERE chat_id=? AND id=?", (chat_id, object_id))
            if object_type == "deadline":
                conn.execute(
                    "UPDATE reminders SET status='cancelled' WHERE chat_id=? AND deadline_id=? "
                    "AND status IN ('scheduled','retry_wait','claimed')",
                    (chat_id, object_id),
                )
                self._rebuild_digest_jobs(conn, chat_id, now)
            after = dict(conn.execute(f"SELECT * FROM {table} WHERE chat_id=? AND id=?", (chat_id, object_id)).fetchone())
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, chat_id, actor.user_id, f"{object_type}_undo_creation", object_id,
                 json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()),
            )
        return Response("success", "Создание отменено в 10-минутном окне.", {f"{object_type}_id": object_id})

    def cancel_last(self, chat_id: str, actor: Actor, now: datetime) -> Response:
        if not self.store.global_writes_enabled() or self._stopped(chat_id):
            return Response("stopped", "Изменяющие операции остановлены kill switch.")
        with self.store.tx() as conn:
            if not self.store.runtime_setting_enabled("global_writes_enabled", conn=conn, lock=True):
                return Response("stopped", "Изменяющие операции остановлены kill switch.")
            row = conn.execute("SELECT * FROM deadlines WHERE chat_id=? AND author_id=? AND status IN ('active','cancelled') ORDER BY created_at DESC LIMIT 1", (chat_id, actor.user_id)).fetchone()
            if not row or (now - datetime.fromisoformat(row["created_at"])).total_seconds() > 600:
                return Response("not_found", "Нет доступного создания для отмены в 10-минутном окне.")
            deadline = Deadline(**dict(row))
            if deadline.status == "cancelled":
                return Response("success", "Последнее создание уже отменено.", {"deadline_id": deadline.id, "idempotent_replay": True})
            conn.execute("UPDATE deadlines SET status='cancelled', version=version+1 WHERE chat_id=? AND id=?", (chat_id, deadline.id))
            conn.execute("UPDATE reminders SET status='cancelled' WHERE chat_id=? AND deadline_id=? AND type='t24' AND status IN ('scheduled','retry_wait','claimed')", (chat_id, deadline.id))
            self._rebuild_digest_jobs(conn, chat_id, now)
            after = self.store.get_deadline(chat_id, deadline.id).to_dict()
            conn.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, chat_id, actor.user_id, "cancel_last", deadline.id, json.dumps(deadline.to_dict(), ensure_ascii=False), json.dumps(after, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()))
        return Response("success", "Последнее создание отменено.", {"deadline_id": deadline.id})

    def cancel_last_material(self, chat_id: str, actor: Actor, now: datetime) -> Response:
        if not self.store.global_writes_enabled() or self._stopped(chat_id):
            return Response("stopped", "Изменяющие операции остановлены kill switch.")
        with self.store.tx() as conn:
            if not self.store.runtime_setting_enabled("global_writes_enabled", conn=conn, lock=True):
                return Response("stopped", "Изменяющие операции остановлены kill switch.")
            row = conn.execute(
                "SELECT * FROM materials WHERE chat_id=? AND author_id=? AND status IN ('active','cancelled') "
                "ORDER BY created_at DESC LIMIT 1", (chat_id, actor.user_id),
            ).fetchone()
            if not row or (now - datetime.fromisoformat(row["created_at"])).total_seconds() > 600:
                return Response("not_found", "Нет доступного материала для отмены в 10-минутном окне.")
            before = dict(row)
            if row["status"] == "cancelled":
                return Response("success", "Последнее создание уже отменено.", {"material_id": row["id"], "idempotent_replay": True})
            conn.execute("UPDATE materials SET status='cancelled',version=version+1 WHERE chat_id=? AND id=?", (chat_id, row["id"]))
            after = dict(conn.execute("SELECT * FROM materials WHERE chat_id=? AND id=?", (chat_id, row["id"])).fetchone())
            conn.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, chat_id, actor.user_id, "material_cancel_last", row["id"], json.dumps(before, ensure_ascii=False),
                 json.dumps(after, ensure_ascii=False), uuid.uuid4().hex, now.isoformat()),
            )
        return Response("success", "Последнее создание материала отменено.", {"material_id": row["id"]})
