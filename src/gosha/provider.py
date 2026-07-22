from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .models import Intent, ProviderResult, ProviderUsage
from .time_rules import strip_temporal_expressions


class ProviderError(RuntimeError):
    pass


class IntentProvider(Protocol):
    def parse(self, text: str) -> ProviderResult: ...


DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
TIME = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")
ID = re.compile(r"\b([0-9a-f]{8})\b", re.I)
MATERIAL_ID = re.compile(r"\b([0-9a-f]{10})\b", re.I)
URL = re.compile(r"https?://[^\s|<>\"]+", re.I)


def _url(text: str) -> str | None:
    match = URL.search(text)
    return match.group(0).rstrip(".,;:!?)]") if match else None


class OfflineProvider:
    """Deterministic demo baseline; its metrics are not LLM quality."""

    name = "offline-rules-v1"

    def parse(self, text: str) -> ProviderResult:
        clean = re.sub(r"@gosha(?:space)?", "", text, flags=re.I).strip()
        low = clean.lower()
        if low.startswith("/material_add"):
            parts = [p.strip() for p in clean[len("/material_add"):].split("|", 1)]
            return ProviderResult(Intent.MATERIAL_SAVE, {"url": parts[0] or None if parts else None, "description": parts[1] if len(parts) > 1 and parts[1] else None}, self.name, 1.0)
        if low.startswith("/material_correct"):
            parts = [p.strip() for p in clean[len("/material_correct"):].split("|", 2)]
            return ProviderResult(Intent.MATERIAL_CORRECT, {"material_id": parts[0] if parts else None, "url": parts[1] if len(parts) > 1 and parts[1] else None, "description": parts[2] if len(parts) > 2 and parts[2] else None}, self.name, 1.0)
        if low.startswith("/material_deactivate"):
            return ProviderResult(Intent.MATERIAL_DEACTIVATE, {"material_id": clean[len("/material_deactivate"):].strip() or None}, self.name, 1.0)
        if low.startswith("/materials"):
            query = clean[len("/materials"):].strip()
            return ProviderResult(Intent.MATERIAL_FIND if query else Intent.MATERIAL_LIST, {"query": query or None}, self.name, 1.0)
        if any(phrase in low for phrase in ("покажи материалы", "список материалов", "какие материалы", "покажи ссылки", "список ссылок")):
            return ProviderResult(Intent.MATERIAL_LIST, {}, self.name, 0.95)
        if any(phrase in low for phrase in ("найди материал", "найди ссылку", "поищи материал", "поищи ссылку")):
            query = re.sub(r"(?i)^.*?(?:найди|поищи)\s+(?:материал|ссылку)\s*", "", clean).strip()
            return ProviderResult(Intent.MATERIAL_FIND, {"query": query or None}, self.name, 0.9)
        if ("материал" in low or "ссылк" in low) and any(word in low for word in ("деактив", "удали", "архив")):
            match = MATERIAL_ID.search(low)
            return ProviderResult(Intent.MATERIAL_DEACTIVATE, {"material_id": match.group(1) if match else None}, self.name, 0.9)
        if ("материал" in low or "ссылк" in low) and any(word in low for word in ("исправ", "измени", "обнови")):
            match = MATERIAL_ID.search(low)
            url = _url(clean)
            description = re.sub(r"(?is)^.*?\b(?:описание|название)\s*(?:на|:)?\s*", "", clean).strip() if re.search(r"(?i)\b(?:описание|название)\b", clean) else None
            return ProviderResult(Intent.MATERIAL_CORRECT, {"material_id": match.group(1) if match else None, "url": url, "description": description or None}, self.name, 0.85)
        if _url(clean) and any(word in low for word in ("сохрани", "добавь", "запиши")):
            url = _url(clean)
            description = clean.replace(url or "", " ")
            description = re.sub(r"(?i)\b(?:сохрани|добавь|запиши|ссылку|ссылка|материал)\b", " ", description)
            description = re.sub(r"\s+", " ", description).strip(" —:-")
            return ProviderResult(Intent.MATERIAL_SAVE, {"url": url, "description": description or None}, self.name, 0.9)
        if low.startswith("/deadline_add"):
            parts = [p.strip() for p in clean[len("/deadline_add"):].split("|")]
            return ProviderResult(Intent.ADD, {"title": parts[0] or None if parts else None, "date": parts[1] if len(parts) > 1 else None, "time": parts[2] if len(parts) > 2 and parts[2] else None}, self.name, 1.0)
        if low.startswith("/deadline_correct"):
            parts = [p.strip() for p in clean[len("/deadline_correct"):].split("|")]
            return ProviderResult(Intent.CORRECT, {"deadline_id": parts[0] if parts else None, "date": parts[1] if len(parts) > 1 else None, "time": parts[2] if len(parts) > 2 else None}, self.name, 1.0)
        if low.startswith("/deadline_deactivate"):
            return ProviderResult(Intent.DEACTIVATE, {"deadline_id": clean[len("/deadline_deactivate"):].strip() or None}, self.name, 1.0)
        if low.startswith("/deadlines") or any(x in low for x in ("покажи дедлайн", "какие дедлайн", "список дедлайн")):
            return ProviderResult(Intent.LIST, {}, self.name, 0.95)
        if low.startswith("/deadline_get") or any(x in low for x in ("когда дедлайн", "что с дедлайн", "срок по")):
            match = ID.search(low)
            query = clean.split(maxsplit=2)[-1] if len(clean.split()) > 2 else ""
            return ProviderResult(Intent.QUESTION, {"deadline_id": match.group(1) if match else None, "query": query}, self.name, 0.9)
        if low.startswith("/cancel") or "отмени последнее" in low:
            return ProviderResult(Intent.CANCEL_LAST, {}, self.name, 0.95)
        if low.startswith("/call_all") or any(phrase in low for phrase in (
            "позови всех", "зови всех", "тегни всех", "отметь всех", "вызови всех",
            "созови всех", "собери всех", "позови участников", "позови народ",
            "позови весь", "тегни весь", "отметь весь", "собери весь", "созови весь",
        )):
            return ProviderResult(Intent.CALL_ALL, {}, self.name, 0.95)
        if any(x in low for x in ("деактив", "отмени дедлайн")):
            match = ID.search(low)
            return ProviderResult(Intent.DEACTIVATE, {"deadline_id": match.group(1) if match else None}, self.name, 0.85)
        if any(x in low for x in ("исправ", "перенеси", "измени")):
            match, date, time = ID.search(low), DATE.search(low), TIME.search(low)
            return ProviderResult(Intent.CORRECT, {"deadline_id": match.group(1) if match else None, "date": date.group(0) if date else None, "time": time.group(0) if time else None}, self.name, 0.82)
        if any(x in low for x in ("добав", "создай", "запиши", "дедлайн")):
            date, time = DATE.search(low), TIME.search(low)
            title = clean
            for pattern in (r"(?i)добавь\s+(?:дедлайн\s+)?", r"(?i)создай\s+(?:дедлайн\s+)?", r"(?i)запиши\s+(?:дедлайн\s+)?"):
                title = re.sub(pattern, "", title)
            title = strip_temporal_expressions(title)
            return ProviderResult(Intent.ADD, {"title": title or None, "date": date.group(0) if date else None, "time": time.group(0) if time else None}, self.name, 0.8)
        return ProviderResult(Intent.UNKNOWN, {}, self.name, 0.2)


@dataclass
class OpenAICompatibleProvider:
    api_key: str
    model: str
    endpoint: str = "https://api.openai.com/v1/responses"
    name: str = "openai-structured-v1"

    def parse(self, text: str) -> ProviderResult:
        started = time.monotonic()
        slot_names = (
            "title", "date", "date_evidence", "time", "time_evidence",
            "deadline_id", "target_title", "target_evidence",
            "url", "description", "material_id", "query",
        )
        # CANCEL_LAST is deliberately absent: undo is a deterministic command /
        # button, never a model-selected side effect.
        model_intents = [i.value for i in Intent if i != Intent.CANCEL_LAST]
        schema = {"type": "object", "additionalProperties": False, "properties": {"intent": {"type": "string", "enum": model_intents}, "slots": {"type": "object", "additionalProperties": False, "properties": {name: {"type": ["string", "null"]} for name in slot_names}, "required": list(slot_names)}}, "required": ["intent", "slots"]}
        system = (
            "Understand an explicit, possibly informal or misspelled Gosha request about shared deadlines "
            "or saved URL materials. Return intent and candidate semantic slots only; never claim an action "
            "happened and never fetch a URL. Remove bot addresses, vocatives, filler, command words, and "
            "date/time phrases from the deadline title. For each expressed date or time, copy its exact, "
            "verbatim substring into date_evidence or time_evidence. Then normalize an obvious typo in date "
            "to a concise Russian expression (for example date_evidence='З авгсута', date='3 августа') and "
            "normalize colloquial time to HH:MM (for example time_evidence='в шесть вечера', time='18:00'). "
            "Evidence must be null when the user did not express that value; never invent evidence, a date, "
            "or a time. If an expressed value is ambiguous, preserve its exact evidence but return the "
            "normalized slot as null. Copy only URLs and object IDs present in user text. Backend validation "
            "and human preview own final normalization and every side effect. For a deadline correction without "
            "an ID, put the concise normalized name of the existing deadline in target_title and copy the exact "
            "noun phrase that identifies it in target_evidence. Example: target_evidence='загрузке презентации "
            "питча', target_title='загрузка презентации питча'. Do not put the new date/time or words like "
            "'дедлайн', 'обнови' into the target. Use call_all_participants when the user asks in any free "
            "form to tag, call, gather, summon, notify, or invite everyone/all participants in this group. "
            "Never select cancel_last_creation."
        )
        payload = {"model": self.model, "reasoning": {"effort": "none"}, "store": False, "input": [{"role": "system", "content": system}, {"role": "user", "content": text}], "text": {"format": {"type": "json_schema", "name": "intent_slots", "strict": True, "schema": schema}}}
        req = urllib.request.Request(self.endpoint, json.dumps(payload).encode(), {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, AttributeError) as exc:
            raise ProviderError("provider_unavailable") from exc
        if body.get("status") == "incomplete" or body.get("error"):
            raise ProviderError("provider_refused_or_incomplete")
        try:
            blocks = [block for item in body["output"] for block in item.get("content", [])]
            if any(block.get("type") == "refusal" for block in blocks):
                raise ProviderError("provider_refusal")
            raw = next(block for block in blocks if block.get("type") == "output_text")
            parsed = json.loads(raw["text"])
            if set(parsed) != {"intent", "slots"} or not isinstance(parsed["slots"], dict):
                raise ProviderError("invalid_structured_output")
            if set(parsed["slots"]) != set(slot_names) or any(value is not None and not isinstance(value, str) for value in parsed["slots"].values()):
                raise ProviderError("invalid_structured_output")
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
            output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}

            def token_count(source: dict, key: str) -> int | None:
                value = source.get(key)
                return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

            measured = ProviderUsage(
                input_tokens=token_count(usage, "input_tokens"),
                output_tokens=token_count(usage, "output_tokens"),
                cached_input_tokens=token_count(input_details, "cached_tokens"),
                reasoning_tokens=token_count(output_details, "reasoning_tokens"),
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
            return ProviderResult(
                Intent(parsed["intent"]), parsed["slots"], f"{self.name}:{self.model}", usage=measured,
            )
        except ProviderError:
            raise
        except (KeyError, IndexError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("invalid_structured_output") from exc
