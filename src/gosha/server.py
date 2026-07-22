from __future__ import annotations

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .models import Actor, Role
from .config import build_provider
from .service import GoshaService
from .store import Store


ROOT = Path(__file__).resolve().parent / "static"


class Handler(SimpleHTTPRequestHandler):
    service: GoshaService

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "version": __version__}); return
        if parsed.path == "/api/state":
            chat_id = parse_qs(parsed.query).get("chat_id", ["demo-study-group"])[0]
            store = self.service.store
            if not store.chat(chat_id):
                self._json(404, {"error": "unknown_chat"}); return
            self._json(200, {"chat_id": chat_id, "deadlines": [d.to_dict() for d in store.list_deadlines(chat_id)], "audit": store.audit(chat_id), "jobs": store.jobs(chat_id)}); return
        super().do_GET()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(length) or b"{}")
            actor = Actor(body.get("user_id", "alen"), Role(body.get("role", "member")))
            if self.path == "/api/ask":
                result = self.service.handle(body.get("chat_id", "demo-study-group"), actor, body.get("text", ""), body.get("entry_point", "mention"))
            elif self.path == "/api/confirm":
                result = self.service.confirm(body.get("chat_id", "demo-study-group"), actor, body["pending_id"], body.get("idempotency_key", body["pending_id"]))
            else:
                self._json(404, {"error": "not_found"}); return
            self._json(200, result.to_dict())
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json(400, {"error": type(exc).__name__})


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--db", default="gosha-demo.db"); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8080); parser.add_argument("--provider", choices=("offline", "openai"), default="offline"); args = parser.parse_args()
    store = Store(args.db); store.add_chat("demo-study-group", "Europe/Moscow"); store.add_chat("demo-other-group", "Europe/Moscow")
    Handler.service = GoshaService(store, build_provider(args.provider))
    print(f"Gosha local demo: http://{args.host}:{args.port} · provider={args.provider}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
