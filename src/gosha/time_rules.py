from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimeRuleError(ValueError):
    pass


MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
WEEKDAYS_RU = {
    "понедельник": 0, "понедельника": 0,
    "вторник": 1, "вторника": 1,
    "среда": 2, "среду": 2, "среды": 2,
    "четверг": 3, "четверга": 3,
    "пятница": 4, "пятницу": 4, "пятницы": 4,
    "суббота": 5, "субботу": 5, "субботы": 5,
    "воскресенье": 6,
}
_MONTH_WORDS = "|".join(MONTHS_RU)
_WEEKDAY_WORDS = "|".join(WEEKDAYS_RU)
ISO_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
RU_DATE_RE = re.compile(rf"(?<!\d)([0-3]?\d)\s+({_MONTH_WORDS})(?:\s+(20\d{{2}}))?(?!\d)", re.I)
NUMERIC_DATE_RE = re.compile(r"(?<!\d)([0-3]?\d)[./]([01]?\d)(?:[./](20\d{2}))?(?!\d)")
RELATIVE_DATE_RE = re.compile(r"\b(послезавтра|завтра|сегодня)\b", re.I)
WEEKDAY_DATE_RE = re.compile(rf"\b(?:(?:в|на)\s+)?(?:(?:следующ(?:ий|ую|ее)|ближайш(?:ий|ую|ее))\s+)?({_WEEKDAY_WORDS})\b", re.I)
TIME_RE = re.compile(r"(?<!\d)(?:[01]\d|2[0-3]):[0-5]\d(?!\d)")


def _future_year(day: int, month: int, today: date, explicit_year: int | None) -> date:
    year = explicit_year or today.year
    try:
        candidate = date(year, month, day)
    except ValueError as exc:
        raise TimeRuleError("invalid_natural_date") from exc
    if explicit_year is None and candidate < today:
        try:
            candidate = date(year + 1, month, day)
        except ValueError as exc:
            raise TimeRuleError("invalid_natural_date") from exc
    return candidate


def resolve_user_dates(text: str, timezone_id: str, now: datetime) -> list[str]:
    """Normalize only date expressions explicitly present in the user text."""
    try:
        zone = ZoneInfo(timezone_id)
    except ZoneInfoNotFoundError as exc:
        raise TimeRuleError("unknown_timezone") from exc
    today = now.astimezone(zone).date()
    candidates: list[str] = []

    for match in ISO_DATE_RE.finditer(text):
        try:
            candidates.append(date.fromisoformat(match.group(0)).isoformat())
        except ValueError as exc:
            raise TimeRuleError("invalid_natural_date") from exc
    for match in RU_DATE_RE.finditer(text):
        day, month_word, year = match.groups()
        candidates.append(_future_year(int(day), MONTHS_RU[month_word.casefold()], today, int(year) if year else None).isoformat())
    for match in NUMERIC_DATE_RE.finditer(text):
        day, month, year = match.groups()
        candidates.append(_future_year(int(day), int(month), today, int(year) if year else None).isoformat())
    for match in RELATIVE_DATE_RE.finditer(text):
        delta = {"сегодня": 0, "завтра": 1, "послезавтра": 2}[match.group(1).casefold()]
        candidates.append((today + timedelta(days=delta)).isoformat())
    for match in WEEKDAY_DATE_RE.finditer(text):
        target = WEEKDAYS_RU[match.group(1).casefold()]
        delta = (target - today.weekday()) % 7 or 7
        candidates.append((today + timedelta(days=delta)).isoformat())

    return list(dict.fromkeys(candidates))


def strip_temporal_expressions(text: str) -> str:
    """Remove supported date/time phrases from an offline-provider title."""
    value = text
    for pattern in (ISO_DATE_RE, RU_DATE_RE, NUMERIC_DATE_RE, RELATIVE_DATE_RE, WEEKDAY_DATE_RE, TIME_RE):
        value = pattern.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" ,—-:|")
    return re.sub(r"(?i)\s+в$", "", value).strip()


def normalize_due(date_value: str, time_value: str | None, timezone_id: str, now: datetime) -> tuple[str, str, bool]:
    try:
        zone = ZoneInfo(timezone_id)
    except ZoneInfoNotFoundError as exc:
        raise TimeRuleError("unknown_timezone") from exc
    defaulted = not time_value
    time_value = time_value or "09:00"
    try:
        naive = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise TimeRuleError("invalid_date_or_time") from exc
    fold0 = naive.replace(tzinfo=zone, fold=0)
    fold1 = naive.replace(tzinfo=zone, fold=1)
    valid0 = fold0.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive
    valid1 = fold1.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive
    if not valid0 and not valid1:
        raise TimeRuleError("nonexistent_local_time")
    if valid0 and valid1 and fold0.utcoffset() != fold1.utcoffset():
        raise TimeRuleError("ambiguous_local_time")
    local = fold0 if valid0 else fold1
    if local.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
        raise TimeRuleError("past_date")
    return local.isoformat(), local.astimezone(timezone.utc).isoformat(), defaulted


def reminder_schedule(due_local_iso: str, timezone_id: str, created_at_iso: str) -> list[tuple[str, str]]:
    """Build frozen JMLC Pilot Cadence A: T-24 plus Sunday 19:00 digest."""
    try:
        zone = ZoneInfo(timezone_id)
    except ZoneInfoNotFoundError as exc:
        raise TimeRuleError("unknown_timezone") from exc
    due = datetime.fromisoformat(due_local_iso).astimezone(zone)
    created = datetime.fromisoformat(created_at_iso).astimezone(zone)
    jobs: list[tuple[str, str]] = []
    t24_utc = due.astimezone(timezone.utc) - timedelta(hours=24)
    if t24_utc > created.astimezone(timezone.utc):
        jobs.append(("t24", t24_utc.isoformat()))
    monday = (due - timedelta(days=due.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    digest = monday - timedelta(days=1) + timedelta(hours=19)
    if digest > created:
        jobs.append(("sunday_digest", digest.astimezone(timezone.utc).isoformat()))
    return jobs
