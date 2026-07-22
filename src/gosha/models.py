from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Intent(StrEnum):
    ADD = "add_deadline"
    LIST = "list_deadlines"
    QUESTION = "question_about_deadline"
    CORRECT = "correct_deadline"
    DEACTIVATE = "deactivate_deadline"
    CANCEL_LAST = "cancel_last_creation"
    MATERIAL_SAVE = "save_material"
    MATERIAL_LIST = "list_materials"
    MATERIAL_FIND = "find_material"
    MATERIAL_CORRECT = "correct_material"
    MATERIAL_DEACTIVATE = "deactivate_material"
    CALL_ALL = "call_all_participants"
    UNKNOWN = "unknown"


class Role(StrEnum):
    MEMBER = "member"
    STEWARD = "steward"
    ADMIN = "admin"


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: Role = Role.MEMBER
    display_name: str = ""


@dataclass
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: int | None = None


@dataclass
class ProviderResult:
    intent: Intent
    slots: dict[str, Any] = field(default_factory=dict)
    provider: str = "unknown"
    confidence: float | None = None
    usage: ProviderUsage | None = None


@dataclass
class Deadline:
    id: str
    chat_id: str
    title: str
    due_local: str
    timezone_id: str
    due_utc: str
    author_id: str
    status: str
    created_at: str
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Response:
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now().astimezone().astimezone(__import__("datetime").timezone.utc)
