from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gosha.service import GoshaService  # noqa: E402
from gosha.store import Store  # noqa: E402
from gosha.telegram import BotIdentity, TelegramBot  # noqa: E402

WIDTH, HEIGHT = 960, 540
CHAT_ID = "-100424242"
NOW = datetime(2026, 7, 18, 12, tzinfo=timezone.utc)
FONT_PATH = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
if not FONT_PATH.exists():
    FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


class DeterministicUUID:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self):
        self.index += 1
        return SimpleNamespace(hex=hashlib.sha256(f"gosha-demo-{self.index}".encode()).hexdigest()[:32])


class MockTelegramAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.message_id = 100

    def call(self, method: str, payload: dict | None = None):
        payload = payload or {}
        self.calls.append((method, payload))
        if method == "sendMessage":
            self.message_id += 1
            return {"message_id": self.message_id, "text": payload.get("text", "")}
        return True


def message(text: str, user_id: str, update_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": int(CHAT_ID), "type": "supergroup"},
            "from": {"id": int(user_id), "first_name": f"Участник {user_id}"},
            "text": text,
        },
    }


def callback(data: str, user_id: str, update_id: int, message_id: int) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": int(user_id), "first_name": f"Участник {user_id}"},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": int(CHAT_ID), "type": "supergroup"}},
        },
    }


def last_call(api: MockTelegramAPI, method: str) -> dict:
    return [payload for name, payload in api.calls if name == method][-1]


def capture_flow() -> list[dict]:
    import uuid

    uuid.uuid4 = DeterministicUUID()  # isolated generator process; makes visible IDs reproducible
    store = Store()
    store.add_chat(CHAT_ID, "Europe/Moscow")
    api = MockTelegramAPI()
    bot = TelegramBot(
        api,
        GoshaService(store, telemetry_hmac_key="demo-only-not-a-live-secret"),
        now=lambda: NOW,
        identity=BotIdentity("999", "gosha_demo_bot"),
    )

    frames: list[dict] = []
    command = "/deadline_add Презентация | 2026-08-20"
    bot.process_update(message(command, "10", 1))
    preview = last_call(api, "sendMessage")
    pending = preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    frames.append({"section": "Дедлайн · предпросмотр", "messages": [("me", "Участник A", command), ("bot", "Gosha", preview["text"])], "button": "Подтвердить"})

    bot.process_update(callback(pending, "10", 2, api.message_id))
    confirmed = last_call(api, "editMessageText")
    frames.append({"section": "Дедлайн · после подтверждения", "messages": [("me", "Участник A", command), ("bot", "Gosha", confirmed["text"])]})

    bot.process_update(message("/deadlines", "20", 3))
    retrieved = last_call(api, "sendMessage")
    if "Презентация" not in retrieved["text"] or "Europe/Moscow" not in retrieved["text"]:
        raise RuntimeError(f"deadline retrieval demo is not grounded: {retrieved['text']!r}")
    frames.append({"section": "Дедлайн · получает другой участник", "messages": [("me", "Участник B", "/deadlines"), ("bot", "Gosha", retrieved["text"])]})

    material_command = "/material_add https://itmo.ru | Правила подачи"
    bot.process_update(message(material_command, "10", 4))
    material_preview = last_call(api, "sendMessage")
    material_pending = material_preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    frames.append({"section": "URL-материал · предпросмотр", "messages": [("me", "Участник A", material_command), ("bot", "Gosha", material_preview["text"])], "button": "Подтвердить"})

    bot.process_update(callback(material_pending, "10", 5, api.message_id))
    material_confirmed = last_call(api, "editMessageText")
    frames.append({"section": "URL-материал · после подтверждения", "messages": [("me", "Участник A", material_command), ("bot", "Gosha", material_confirmed["text"])]})

    bot.process_update(message("/materials", "20", 6))
    material_retrieved = last_call(api, "sendMessage")
    if "Правила подачи" not in material_retrieved["text"] or "https://itmo.ru/" not in material_retrieved["text"]:
        raise RuntimeError(f"material retrieval demo is not grounded: {material_retrieved['text']!r}")
    frames.append({"section": "URL-материал · получает другой участник", "messages": [("me", "Участник B", "/materials"), ("bot", "Gosha", material_retrieved["text"])]})
    store.close()
    return frames


def font(size: int, bold: bool = False):
    bold_path = FONT_PATH.with_name("Arial Bold.ttf")
    return ImageFont.truetype(str(bold_path if bold and bold_path.exists() else FONT_PATH), size)


def multiline_height(draw: ImageDraw.ImageDraw, lines: list[str], face) -> int:
    return sum(draw.textbbox((0, 0), line or " ", font=face)[3] + 4 for line in lines)


def render(frame: dict, number: int, total: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#e7f2f8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 74), fill="#17243b")
    draw.text((28, 20), "GOSHA AI · Telegram", font=font(25, True), fill="white")
    draw.rounded_rectangle((718, 15, 932, 58), radius=16, fill="#fff0cf")
    draw.text((747, 27), "MOCK SIMULATION", font=font(16, True), fill="#9b5b00")
    draw.text((30, 88), frame["section"], font=font(21, True), fill="#17243b")
    draw.text((842, 91), f"{number}/{total}", font=font(16, True), fill="#607086")

    y = 130
    for kind, who, text_value in frame["messages"]:
        lines: list[str] = []
        for paragraph in text_value.splitlines() or [""]:
            lines.extend(wrap(paragraph, width=68, break_long_words=False) or [""])
        body = font(18)
        box_height = max(76, multiline_height(draw, lines, body) + 48)
        left, right = ((265, 920) if kind == "me" else (40, 730))
        fill = "#d9f2ff" if kind == "me" else "#ffffff"
        draw.rounded_rectangle((left, y, right, y + box_height), radius=18, fill=fill, outline="#b7cbd8", width=2)
        draw.text((left + 20, y + 12), who, font=font(15, True), fill="#168bd1" if kind == "me" else "#6f55df")
        ty = y + 35
        for line in lines:
            draw.text((left + 20, ty), line, font=body, fill="#17243b")
            ty += draw.textbbox((0, 0), line or " ", font=body)[3] + 4
        y += box_height + 14

    if frame.get("button"):
        draw.rounded_rectangle((40, min(y, 450), 242, min(y, 450) + 48), radius=14, fill="#229ed9")
        draw.text((66, min(y, 450) + 13), frame["button"], font=font(17, True), fill="white")
        draw.text((265, min(y, 450) + 14), "До подтверждения общей записи нет", font=font(16, True), fill="#607086")
    draw.text((30, 510), "Локальный HTTP mock Bot API · это не живой Telegram и не пользовательский пилот", font=font(15), fill="#607086")
    return image


def main() -> None:
    output = ROOT / "assets" / "demo.gif"
    output.parent.mkdir(parents=True, exist_ok=True)
    flow = capture_flow()
    frames = [render(item, index, len(flow)) for index, item in enumerate(flow, 1)]
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=1450, loop=0, optimize=True, disposal=2)
    print(f"Built {output} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
