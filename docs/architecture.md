# Архитектура MVP

```text
explicit mention / safe command
            |
      entry-point gate -------- ordinary chat -> ignored
            |
 LLM: намерение + кандидаты полей (или offline baseline)
            |
 backend: schema + allowlist + date + role + chat validation
            |
       pending preview
            |
 human review + explicit confirmation + idempotency
            |
 backend commit -> audit/event -> deterministic reminder jobs
            |
      response from committed state
```

Основные модули:

- `provider.py` — typed provider contract, offline baseline, optional OpenAI-compatible adapter;
- `service.py` — state machine, validation and application boundary;
- `store.py` — transactional SQLite repository with chat isolation;
- `time_rules.py` — IANA normalization and Pilot Cadence A;
- `evaluation.py` — reproducible synthetic intent/slot evaluation;
- `server.py` / `cli.py` — local demo surfaces over the same service.

`Store` сериализует операции через process-local `RLock`, а confirm повторно проверяет и атомарно потребляет pending preview внутри `BEGIN IMMEDIATE`. PostgreSQL-профиль использует транзакционные блокировки; migrations `001–005` применяются атомарно вместе с маркером версии. Persistent global writes/LLM controls читаются повторно в той же транзакции до side effect, поэтому stop переживает рестарт и fail closed при отсутствующей настройке. Migrations `001–005` и environment-gated suite проверены локально против чистого PostgreSQL 16; load, failover и production runtime ещё не проверены.

Telemetry не хранит raw user/chat IDs: они заменяются deployment-specific keyed HMAC. Live-профиль требует отдельный secret; локальный профиль без настройки создаёт process-ephemeral key, поэтому его события намеренно не linkable между рестартами.

Local API не является security boundary: переданные клиентом role, actor и entry point считаются тестовыми. Реализованный Telegram adapter выводит trusted context из update, проверяет явный entry point/reply и получает admin status через Bot API. Этот path проверен на mock Bot API; live token/group evidence отсутствует.
