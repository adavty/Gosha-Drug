# Gosha AI — технический маршрут для reviewer

Этот документ ведёт только по реализованной технической части JMLC-проекта. Product discovery, CV, мотивационное письмо и презентация не являются частью этого маршрута.

## 1. Техническая задача

Gosha превращает явный запрос в учебном Telegram-чате в общий дедлайн или metadata-only URL-материал. Свободный язык должен помогать заполнить preview, но не должен получать право самостоятельно изменить состояние чата.

Основной технический риск — не только ошибочная классификация intent. Ошибочный slot, роль, дата, повторный callback или неопределённый результат сетевой отправки способны создать неверное общее состояние. Поэтому проект разделяет probabilistic understanding и deterministic side effects.

## 2. Где применяется AI

Два взаимозаменяемых provider реализуют один контракт:

- `offline-rules-v1` — детерминированный baseline и fallback;
- OpenAI-compatible structured-output provider — `intent + candidate slots`.

LLM не получает SQL, write/send tools, `chat_id` или роль. Для нормализованной даты и времени она обязана вернуть дословный evidence-фрагмент запроса; backend проверяет evidence, календарь, timezone, URL/ID и права. Любая запись проходит preview и явное подтверждение.

```text
Telegram update
  -> entry-point / identity adapter
  -> LLM or rules: intent + candidate slots
  -> deterministic validation
  -> actor-bound pending preview
  -> explicit confirmation
  -> transaction + audit + delivery outbox
```

Код: [`provider.py`](src/gosha/provider.py), [`service.py`](src/gosha/service.py), [`telegram.py`](src/gosha/telegram.py).

## 3. Архитектура и данные

| Контур | Реализация | Граница |
|---|---|---|
| Runtime UX | Telegram Bot API, long polling, callbacks | основной интерфейс |
| Application | Python domain/service state machine | validation и side effects |
| Storage | SQLite local/test; PostgreSQL 16 live target | chat-scoped state и migrations |
| Delivery | durable database outbox/worker | retry/permanent/unknown outcomes |
| Operations | persistent stops, operator CLI, audit | incident response |
| Telemetry | keyed-HMAC identifiers; token/latency counts | без raw message text |

Основные инварианты, migration strategy и recovery описаны в [`docs/technical-contract.md`](docs/technical-contract.md), [`docs/architecture.md`](docs/architecture.md) и [`docs/storage-profiles.md`](docs/storage-profiles.md).

## 4. Evaluation

Репозиторий различает три уровня доказательств:

1. unit/integration tests — корректность state machine, Telegram adapter, storage и delivery;
2. synthetic rules evaluation — воспроизводимый baseline, а не качество LLM;
3. live LLM evaluation — отдельный explicit-opt-in прогон с model ID, dataset hash, метриками, latency, token usage и ценовыми предпосылками.

```bash
make check

OPENAI_API_KEY='...' \
GOSHA_OPENAI_MODEL='<explicit-model-id>' \
GOSHA_LLM_INPUT_USD_PER_MILLION='<dated-rate>' \
GOSHA_LLM_OUTPUT_USD_PER_MILLION='<dated-rate>' \
./scripts/run_llm_evaluation.sh
```

До появления `evaluation/llm-*.json` нельзя утверждать, что LLM прошла сравнительную валидацию. Текущий 300-row benchmark — это 30 semantic seeds × 10 детерминированных surface transforms, а не пользовательские данные, 300 независимых кейсов или канонический Bronze gate. Он нужен для воспроизводимой проверки robustness и явно показывает провал rules baseline на safety slice.

## 5. Воспроизводимость и quality gates

`make check` выполняет:

- Ruff critical-error lint;
- branch coverage с порогом 85%;
- все unit/integration tests;
- controlled, challenge и 300-row perturbation rules evaluation;
- проверку воспроизводимости frozen synthetic benchmark;
- проверку локальных ссылок README.

GitHub Actions дополнительно проверяет Compose, собирает и устанавливает wheel в чистое окружение, поднимает PostgreSQL 16, собирает Docker image и проверяет container health. Dependency audit запускается отдельно командой `make audit`, поскольку база уязвимостей требует сетевого доступа.

## 6. Что доказано и что нет

Локально 22 июля 2026 подтверждены: `143 passed, 1 PostgreSQL test skipped` в default-профиле, `144 passed` с PostgreSQL 16, 85% branch coverage и Ruff; wheel build/clean install; Docker image `gosha-ai:1.2.0`; атомарное применение migrations `001–005`; ответ container `/health` с версией `1.2.0`; три synthetic rules reports. Reviewer-accessible remote CI всё ещё должен быть подтверждён ссылкой на конкретный успешный run.

Не доказаны текущим репозиторием: качество live LLM, преимущество над командами, production load, длительная Telegram-эксплуатация, пользовательский эффект и pilot outcomes.

## 7. Быстрая проверка

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
make check
docker compose config --quiet
docker compose up --build config-check
```

`config-check` требует работающий Docker daemon, но не требует Telegram/OpenAI secrets. Live bot запускается только явным профилем и с deployment secrets; см. [`docs/telegram-runtime.md`](docs/telegram-runtime.md).
