from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from .store_factory import build_store


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gosha audited operator controls")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--db", default=os.environ.get("GOSHA_DB", "gosha.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("delivery-unknown-list"); ls.add_argument("--limit", type=int, default=100)
    inspect = sub.add_parser("delivery-inspect"); inspect.add_argument("job_key")
    resolve = sub.add_parser("delivery-unknown-resolve")
    resolve.add_argument("job_key"); resolve.add_argument("--decision", choices=("retry", "failed_permanent"), required=True)
    resolve.add_argument("--actor", required=True); resolve.add_argument("--reason", required=True)
    global_stop = sub.add_parser("sends-global")
    global_stop.add_argument("--enabled", choices=("on", "off"), required=True)
    global_stop.add_argument("--actor", required=True); global_stop.add_argument("--reason", required=True)
    chat_stop = sub.add_parser("sends-chat")
    chat_stop.add_argument("chat_id"); chat_stop.add_argument("--enabled", choices=("on", "off"), required=True)
    chat_stop.add_argument("--actor", required=True); chat_stop.add_argument("--reason", required=True)
    writes_stop = sub.add_parser("writes-global")
    writes_stop.add_argument("--enabled", choices=("on", "off"), required=True)
    writes_stop.add_argument("--actor", required=True); writes_stop.add_argument("--reason", required=True)
    llm_stop = sub.add_parser("llm-global")
    llm_stop.add_argument("--enabled", choices=("on", "off"), required=True)
    llm_stop.add_argument("--actor", required=True); llm_stop.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    store = build_store(database_url=args.database_url, sqlite_path=args.db)
    now = datetime.now(timezone.utc)
    try:
        if args.command == "delivery-unknown-list":
            _print({"items": store.list_unknown_deliveries(args.limit)}); return 0
        if args.command == "delivery-inspect":
            item = store.inspect_delivery(args.job_key)
            if not item:
                _print({"error": "not_found", "job_key": args.job_key}); return 2
            _print(item); return 0
        if args.command == "delivery-unknown-resolve":
            try:
                changed = store.resolve_delivery_unknown(
                    args.job_key, args.decision, args.actor, now, reason=args.reason,
                )
            except ValueError as exc:
                _print({"error": str(exc), "job_key": args.job_key}); return 2
            _print({"status": "resolved" if changed else "not_found_or_not_unknown", "job_key": args.job_key, "decision": args.decision})
            return 0 if changed else 2
        if args.command == "sends-global":
            enabled = args.enabled == "on"
            store.set_global_sends_enabled(enabled, actor_id=args.actor, reason=args.reason, now=now)
            _print({"scope": "global", "enabled": enabled}); return 0
        if args.command in {"writes-global", "llm-global"}:
            enabled = args.enabled == "on"
            key = "global_writes_enabled" if args.command == "writes-global" else "global_llm_enabled"
            store.set_runtime_setting(key, enabled, actor_id=args.actor, reason=args.reason, now=now)
            _print({"scope": "global", "control": key, "enabled": enabled}); return 0
        enabled = args.enabled == "on"
        store.set_chat_enabled(args.chat_id, enabled, actor_id=args.actor, reason=args.reason, now=now)
        _print({"scope": "chat", "chat_id": args.chat_id, "enabled": enabled}); return 0
    finally:
        close = getattr(store, "close", None)
        if close:
            close()


if __name__ == "__main__":
    raise SystemExit(main())
