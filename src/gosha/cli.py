from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from .evaluation import write_report
from .config import build_provider
from .models import Actor, Role
from .service import GoshaService
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Gosha AI local MVP")
    parser.add_argument("--db", default="gosha.db")
    parser.add_argument("--provider", choices=("offline", "openai"), default="offline")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup-chat"); setup.add_argument("chat"); setup.add_argument("timezone")
    ask = sub.add_parser("ask"); ask.add_argument("chat"); ask.add_argument("user"); ask.add_argument("text"); ask.add_argument("--role", choices=[r.value for r in Role], default="member")
    confirm = sub.add_parser("confirm"); confirm.add_argument("chat"); confirm.add_argument("user"); confirm.add_argument("pending"); confirm.add_argument("key"); confirm.add_argument("--role", choices=[r.value for r in Role], default="member")
    ev = sub.add_parser("evaluate"); ev.add_argument("dataset"); ev.add_argument("--output", default="artifacts/evaluation.json")
    ev.add_argument("--input-usd-per-million", type=float)
    ev.add_argument("--output-usd-per-million", type=float)
    args = parser.parse_args()
    if args.command == "evaluate":
        if (args.input_usd_per_million is None) != (args.output_usd_per_million is None):
            parser.error("both pricing arguments are required together")
        provider = build_provider(args.provider)
        print(json.dumps(write_report(
            args.dataset, args.output, provider,
            input_usd_per_million=args.input_usd_per_million,
            output_usd_per_million=args.output_usd_per_million,
        ), ensure_ascii=False, indent=2)); return
    store = Store(args.db); service = GoshaService(store, build_provider(args.provider))
    if args.command == "setup-chat":
        store.add_chat(args.chat, args.timezone); print("ok"); return
    actor = Actor(args.user, Role(args.role))
    if args.command == "ask":
        response = service.handle(args.chat, actor, args.text, now=datetime.now(timezone.utc))
    else:
        response = service.confirm(args.chat, actor, args.pending, args.key)
    print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
