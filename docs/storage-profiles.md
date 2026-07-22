# Storage profiles and delivery contract

Authoritative public scope: [`technical-contract.md`](technical-contract.md). Internal signed decisions remain in the non-public evidence package.

## Profiles

- **PostgreSQL is the production/live JMLC profile.** Install `.[postgres]`, set a `postgresql://` `DATABASE_URL`, and construct the repository with `build_store(database_url=...)`. Startup applies ordered files from `migrations/postgres/` and records them in `schema_migrations`.
- **SQLite is local/tests only.** `build_store(sqlite_path=...)` keeps the deterministic single-process profile used by unit tests and the debug server.
- An invalid non-PostgreSQL `DATABASE_URL` fails; there is no silent production downgrade to SQLite.

CI starts PostgreSQL 16 and runs the opt-in repository smoke through `GOSHA_TEST_POSTGRES_DSN`. The same gate was reproduced locally on 20 July 2026: migrations `001–003` applied, `133` tests passed and total branch coverage was `86%`. This is executable parity evidence for the current build, not load, failover or production-readiness evidence.

Container configuration can be validated without a Telegram token:

```bash
docker compose config
docker compose up --build config-check
```

The second command starts PostgreSQL with persistent storage, applies migrations and checks the connection. The live bot is an explicit profile and requires a real secret at runtime:

```bash
TELEGRAM_BOT_TOKEN='...' docker compose --profile live up --build bot
```

The token is never needed for `config-check`. `debug-web` is a separate `--profile debug` local surface and is not the product.

## Transaction and isolation rules

- Every object lookup includes `chat_id`.
- Pending actions are actor/chat/TTL-bound and locked before consumption.
- PostgreSQL uses a transaction-scoped advisory lock for an idempotency key; same-key parallel confirm returns the one committed response.
- Material URL uniqueness is `(chat_id, canonical_url)`. URL normalization never performs a server-side request.
- SQLite uses `BEGIN IMMEDIATE` plus a process lock. It is not evidence of multi-process readiness.

## Delivery states

```text
scheduled -> claimed -> sending -> delivered
                              |-> retry_wait -> claimed
                              |-> delivery_unknown
                              `-> failed_permanent
any not-yet-sent item -> cancelled
```

Worker contract:

1. `claim_due_deliveries(now)` durably leases due `scheduled/retry_wait` rows.
2. Immediately before `sendMessage`, call `mark_delivery_sending(job_key, now)`.
3. Telegram success with `message_id` calls `mark_delivery_succeeded`.
4. An explicit retryable rejection calls `mark_delivery_failed(..., retryable=True)` and reuses the same `job_key` after backoff.
5. A permanent rejection calls `mark_delivery_failed(..., retryable=False)`.
6. Transport loss after the request may have left the process calls `mark_delivery_unknown`; automatic retry is prohibited.
7. Expired `claimed` leases safely become `retry_wait`; expired `sending` leases become `delivery_unknown`.
8. Only an explicit audited operator call `resolve_delivery_unknown` may retry or close an unknown delivery.

## Scheduled-send stops

Global and per-chat send controls are persistent database state. Disabling either scope atomically cancels `scheduled`, `retry_wait` and `claimed` rows. A row already marked `sending` becomes `delivery_unknown` with an audit entry because Telegram acceptance cannot be ruled out. Claim and the final `claimed → sending` transition both check the controls fail closed.

Re-enabling does **not** resurrect or catch up cancelled jobs. This is deliberate: an operator or a new confirmed domain change must create a new future job. It avoids unexpected messages immediately after a privacy/incident stop.

```bash
gosha-operator --database-url "$DATABASE_URL" sends-global --enabled off --actor operator-id --reason 'incident INC-42'
gosha-operator --database-url "$DATABASE_URL" sends-global --enabled on  --actor operator-id --reason 'INC-42 reviewed'
gosha-operator --database-url "$DATABASE_URL" sends-chat CHAT_ID --enabled off --actor operator-id --reason 'admin request'
```

## `delivery_unknown` operator runbook

1. Stop scheduled sends for the affected chat or globally if impact is unclear.
2. List quarantined rows and inspect one without exposing message payload/content:

```bash
gosha-operator --database-url "$DATABASE_URL" delivery-unknown-list
gosha-operator --database-url "$DATABASE_URL" delivery-inspect JOB_KEY
```

3. Check Telegram/test-group evidence outside Gosha. Never infer delivery from a timeout alone.
4. Record an explicit actor and non-empty incident reason. Retry reuses the same job key; permanent closure never claims delivery:

```bash
gosha-operator --database-url "$DATABASE_URL" delivery-unknown-resolve JOB_KEY \
  --decision retry --actor operator-id --reason 'Telegram confirmed no message; INC-42'

gosha-operator --database-url "$DATABASE_URL" delivery-unknown-resolve JOB_KEY \
  --decision failed_permanent --actor operator-id --reason 'Acceptance could not be disproved; no resend; INC-42'
```

5. Inspect the row again and attach the audit reference to the incident. Re-running resolve on a non-unknown row fails without creating a new job.

This supports durable, deduplicated delivery with conservative ambiguous-outcome handling. It does not claim mathematical exactly-once delivery over Telegram Bot API.
