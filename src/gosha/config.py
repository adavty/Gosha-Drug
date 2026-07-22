from __future__ import annotations

import os
from pathlib import Path

from .provider import OfflineProvider, OpenAICompatibleProvider


def build_provider(name: str):
    if name == "offline":
        return OfflineProvider()
    if name == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required when --provider openai is explicitly selected")
        model = os.environ.get("GOSHA_OPENAI_MODEL")
        if not model:
            raise ValueError("GOSHA_OPENAI_MODEL is required: select a model verified for your OpenAI project")
        return OpenAICompatibleProvider(key, model=model)
    raise ValueError("provider must be offline or openai")


def telemetry_hmac_key(*, required: bool = False) -> str | None:
    """Load a deployment-specific telemetry key from env or a mounted secret file."""
    value = os.environ.get("GOSHA_TELEMETRY_HMAC_KEY")
    file_path = os.environ.get("GOSHA_TELEMETRY_HMAC_KEY_FILE")
    if value and file_path:
        raise ValueError("set only one telemetry HMAC key source")
    if file_path:
        value = Path(file_path).read_text(encoding="utf-8").strip()
    if required and (not value or len(value.encode("utf-8")) < 32):
        raise ValueError("live profile requires a >=32-byte deployment-specific telemetry HMAC secret")
    return value or None
