# Gosha AI — общая память учебного Telegram-чата

Gosha AI превращает фразу о дедлайне или полезную ссылку прямо в учебном Telegram-чате в проверяемое превью, а после подтверждения — в актуальный общий объект для всей группы. В отличие от поиска, закрепов, LMS и календаря, Gosha соединяет ввод в привычном потоке, структурирование, исправление и последующее получение одной текущей версии; это пока продуктовая гипотеза, а не доказанное преимущество.

**Статус:** технический release candidate `1.2.0` · **143 passed, 1 PostgreSQL test skipped** в default-профиле, **144 passed** с PostgreSQL 16 · **85% branch coverage gate** · Docker build, migrations `001–005` и container health подтверждены локально · controlled live Telegram smoke и отдельные structured-output requests подтверждают только feasibility · систематическое live LLM quality evaluation и pilot не проведены.

Техническому reviewer: начните с [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) — там собраны AI-задача, архитектура, evaluation, quality gates и команды воспроизведения без продуктового submission-пакета.

## Содержание

- [Проблема и пользователь](#проблема-и-пользователь)
- [Технический маршрут](TECHNICAL_OVERVIEW.md)
- [Ключевые Telegram-сценарии](#ключевые-telegram-сценарии)
- [AI-технология и её граница](#ai-технология-и-её-граница)
- [Архитектура и стек](#архитектура-и-стек)
- [Проверенное evidence](#проверенное-evidence)
- [Структура репозитория](#структура-репозитория)
- [Быстрый старт](#быстрый-старт)
- [Переменные окружения](#переменные-окружения)
- [Тесты и evaluation](#тесты-и-evaluation)
- [Ограничения и roadmap](#ограничения-и-roadmap)

![MOCK-демонстрация Telegram-сценария](assets/demo.gif)

> GIF воспроизводит текущий локальный HTTP mock Bot API: дедлайн и URL-материал проходят preview → confirm → retrieval другим участником. Это не запись живого Telegram и не пользовательский пилот.

Проверяемая гипотеза LLM — сможет ли она сократить путь от свободной фразы до структурированного превью. Provider извлекает intent и смысловые поля, а backend нормализует явно написанные пользователем даты вроде «27 июля», «завтра», `27.07` или `YYYY-MM-DD` относительно timezone чата. Преимущество над командами ещё не измерено. LLM не управляет состоянием: identity, permissions, календарная проверка, URL/ID, запись, audit и delivery остаются под контролем backend и человека.

## Проблема и пользователь

В активном учебном чате срок или ссылка быстро теряются в потоке: координатор повторяет и исправляет информацию, участник ищет исходник и переспрашивает. Владелец боли и первый инициатор — координатор/admin; второй бенефициар — участник, который получает актуальное общее состояние.

Это **продуктовая гипотеза**. Problem interviews, formative usability и pilot для текущего release ещё не проводились; Telegram search, закрепы, LMS и календарь остаются сильными альтернативами.

## Ключевые Telegram-сценарии

- Дедлайн: `/deadline_add` → абсолютная дата, время, русский день недели и IANA timezone в preview → actor-bound confirm → общий объект.
- Получение: другой участник вызывает `/deadlines` и видит только активные объекты текущего `chat_id`.
- Исправление: admin может назвать существующий дедлайн естественной фразой; backend ищет только в текущем чате, автоматически продолжает лишь при одном совпадении и всегда требует preview → confirm.
- Материал: `/material_add URL | описание` → metadata-only preview → confirm → `/materials`; содержимое страницы не загружается, RAG отсутствует.
- Recovery: автор может отменить своё последнее создание в течение 10 минут; исправление/деактивация доступны только admin, повторно проверенному через Bot API.
- Reminders: backend рассчитывает T-24 и воскресный digest; outbox/worker различает retry, permanent failure и `delivery_unknown` без blind resend.
- Групповой вызов: явная свободная просьба вроде `@goshadrugbot собери всех сюда` → LLM intent → preview с числом известных участников → actor-bound confirm → одно сообщение с упоминаниями и строкой «Имя зовет всех в чат».
- Onboarding: после `/setup` бот публикует карточку `✅ Подключиться к Gosha`; callback даёт trusted Telegram ID, явно включает участника и обновляет счётчик подключившихся. Admin может повторить карточку командой `/gosha_invite`.
- Monthly CSAT: первого числа в 12:00 по timezone каждого чата durable worker отправляет шесть emoji-кнопок от негативной до позитивной; backend хранит баллы `1–6`, один изменяемый ответ пользователя на опрос и агрегирует все чаты. Только deployment owner видит среднее, медиану и число ответов через `/csat_stats`.
- Privacy boundary: текст обычной переписки и команды другому боту игнорируются до AI provider и не сохраняются; для группового вызова adapter хранит только Telegram ID, отображаемое имя, username, время наблюдения и opt-out известных участников.

Telegram Bot API не выдаёт боту полный список участников группы. Поэтому «все» означает известных боту активных участников: прежде всего нажавших onboarding-кнопку или выполнивших `/gosha_join`, а также тех, чьи сообщения или вступление бот увидел после запуска реестра. `/gosha_leave` исключает человека из будущих вызовов; ранее молчавшие участники могут отсутствовать.

## AI-технология и её граница

Доступны два сменных provider:

1. `offline-rules-v1` — детерминированный baseline и fallback;
2. OpenAI-compatible structured-output adapter — опциональный слой для `intent + candidate slots`.

AI получает только минимальный текст явного вызова. У неё нет SQL, write/send tools, `chat_id`, роли или права выбрать финальное действие. Для исправленной естественной даты, разговорного времени и названия изменяемого дедлайна structured output обязан вернуть дословный evidence-фрагмент исходного запроса. Backend проверяет evidence, ищет объект только в текущем чате, не выбирает между несколькими совпадениями, валидирует календарь, DST/timezone, URL/ID, права, pending ownership и idempotency. `cancel_last_creation` исключён из LLM-схемы. Значимое изменение записывается только после человеческого подтверждения.

```text
явный вызов
  → LLM/rules: намерение + кандидаты полей
  → backend: validation + pending preview
  → человек: review + confirm
  → backend: commit + audit + delivery outbox
```

При недоступности/невалидном ответе provider система fail closed и оставляет core-сценарии доступными через команды. Adapter извлекает из provider response token usage и измеряет latency без сохранения текста запроса; evaluator умеет агрегировать эти значения и считать стоимость по явно переданным dated rates. Фактический систематический live LLM-отчёт пока не получен, поэтому model quality, latency distribution и actual cost остаются неизвестными.

## Архитектура и стек

| Контур | Реализация | Назначение |
|---|---|---|
| Product surface | Telegram Bot API adapter, long polling, callbacks | Основной групповой UX; mock-tested, не live |
| Application | Python 3.11+, typed domain/service boundary | Preview/confirm/recovery и business invariants |
| AI | Rules baseline + OpenAI-compatible structured outputs | Intent/slots без права на side effects |
| Storage | SQLite local/test; PostgreSQL 16 target | Chat-scoped state, pending, audit, telemetry, outbox |
| Delivery | Durable worker/outbox | Retry/permanent/unknown states и conservative recovery |
| Operations | Operator CLI, persistent stops, HMAC + usage telemetry | Incident controls, token/latency counts без raw message text |
| Runtime | Dockerfile, Compose, GitHub Actions | Docker/PostgreSQL smoke воспроизведён локально; public remote CI ещё не запускался |

### Docker Compose — сервисы

| Сервис | Профиль | Назначение | Хранилище/порт |
|---|---|---|---|
| `postgres` | default | PostgreSQL 16 для live state | volume `postgres-data` |
| `config-check` | default | Миграции и проверка обязательной PostgreSQL-конфигурации | без порта |
| `bot` | `live` | Telegram long polling, LLM provider и reminder worker | volume `telegram-state` |
| `debug-web` | `debug` | Локальная вторичная debug-консоль | `127.0.0.1:8080` |

Контейнеры запускаются без root, с read-only filesystem, `no-new-privileges`, persistent volumes и restart policy. Healthcheck `bot` подтверждает runtime/DB configuration, но не является доказательством доступности Telegram или LLM.

Подробнее: [product discovery](docs/product-discovery.md), [ВКР → AI UX Gosha](docs/thesis-foundation.md), [стратегия развития](docs/product-development-strategy.md), [рынок и экономика](docs/market-and-business-model.md), [public evidence register](docs/evidence-register.md), [research package](docs/research/README.md), [архитектура](docs/architecture.md), [технический контракт](docs/technical-contract.md), [Telegram runtime](docs/telegram-runtime.md), [storage profiles](docs/storage-profiles.md).

## Проверенное evidence

| Claim | Статус | Ограничение |
|---|---|---|
| `143 passed, 1 PostgreSQL test skipped`; `144 passed` с PostgreSQL 16 | MEASURED local | Оба прогона локальные, не production load |
| Branch coverage 85% + Ruff | MEASURED local | Quality gate, не production reliability |
| Controlled rules smoke: n=26, accuracy/macro-F1 1.0/1.0 | MEASURED synthetic | Contract smoke, не LLM/user quality |
| Rules challenge: n=24, accuracy 0.4583, macro-F1 0.5467 | MEASURED synthetic | Показывает хрупкость baseline |
| Perturbation benchmark: n=300, accuracy 0.9333, macro-F1 0.9344 | MEASURED synthetic | 30 semantic seeds × 10 transforms, не 300 независимых кейсов; call-all slice = 1.0, safety slice = 0.0 |
| Telegram adapter/callbacks/worker | MOCK | Локальный HTTP mock Bot API, не живой Telegram |
| Structured LLM adapter | MOCK | Schema/refusal/transport contract, не live model evaluation |
| Wheel build + clean install | MEASURED local | Packaging smoke, не публикация в registry |
| Docker image + migrations `001–005` + `/health` | MEASURED local | Чистый локальный PostgreSQL/Compose smoke, не production readiness |
| Legacy SQLite upgrade + `gosha-server /health` | MEASURED local | Single-process debug profile |

Таблица выше задаёт границу публичных утверждений: MOCK и синтетические измерения не выдаются за live-проверку или пользовательский результат.

## Продуктовый discovery-контур

Публичный продуктовый пакет построен так, чтобы reviewer мог восстановить не только идею, но и логику решений:

1. [Product discovery](docs/product-discovery.md) — проблема, JTBD, альтернативы, scope по стадиям, AI-гипотеза, метрики, stage gates, экономика, GTM, roadmap и риски.
2. [Thesis foundation](docs/thesis-foundation.md) — доказательная роль ВКР, пять поведенческих и девять AI UX-паттернов, применение и границы переноса.
3. [Product development strategy](docs/product-development-strategy.md) — AS IS → transition → TO BE, problem-to-feature map, B2C/B2B и gates.
4. [Market and business model](docs/market-and-business-model.md) — dated alternatives, LLM/hosting/storage benchmark, unit economics, offers и TAM/SAM/SOM rule.
5. [Evidence register](docs/evidence-register.md) — граница между prior/desk/estimate/local/synthetic/mock/private-live/planned evidence.
6. [Research package](docs/research/README.md) — frozen design и операционный порядок кабинетного и полевого исследования.
7. [LLM-assisted analysis pipeline](docs/research/analysis-pipeline.md) — consent/redaction, JSON coding contract, human verification, clustering, saturation и audit trail.
8. [Decision memo](docs/research/decision-memo-template.md) — переход от raw evidence к продуктовому решению и обновлению внешних claims.

Эти документы являются протоколами, а не результатами. Контакты, consent records, raw Telegram-сообщения, приватные screenshots и provider request identifiers в публичный репозиторий не попадают.

## Структура репозитория

```text
Gosha-AI-public/
├── src/gosha/                 # domain, service, providers, storage, Telegram, CLI/API
│   └── static/                # вторичная local debug console
├── tests/                     # core, Telegram mock, operations, migrations
├── migrations/postgres/       # ordered PostgreSQL migrations 001–005
├── data/                      # synthetic controlled/challenge datasets
├── evaluation/                # reproducible rules reports
├── docs/                      # discovery, strategy, thesis, market/economics, architecture
│   └── research/              # desk/field/LLM-analysis protocols without PII
├── assets/demo.gif            # visibly labelled MOCK demo
├── scripts/                   # quality/LLM checks, GIF generation, privacy-scanned export
├── .github/workflows/ci.yml   # test + PostgreSQL service + container smoke
├── .dockerignore              # минимальный build context без local data/secrets
├── compose.yaml
├── Dockerfile
├── Makefile                    # короткие команды install/test/build/live
├── TECHNICAL_OVERVIEW.md       # reviewer-route по технической части
└── pyproject.toml
```

## Быстрый старт

### Docker: live Telegram-бот

```bash
cp .env.example .env
# Заполнить TELEGRAM_BOT_TOKEN, OPENAI_API_KEY,
# GOSHA_OPENAI_MODEL, GOSHA_PROVIDER=openai и GOSHA_TELEMETRY_HMAC_KEY.
make live
make logs
```

Перед natural-language проверкой администратор выполняет `/setup Europe/Moscow`, а Group Privacy бота должен быть отключён через BotFather. Остановка без удаления данных: `make down`.

### Docker: локальная debug-поверхность

```bash
cp .env.example .env
docker compose --profile debug up --build debug-web
curl http://127.0.0.1:8080/health
```

### Docker: PostgreSQL config check

```bash
docker compose up --build config-check
```

Команда поднимает PostgreSQL, применяет migrations и проверяет runtime configuration. Она не запускает Telegram-бота и не требует токен.

### Локальная разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
./scripts/run_all.sh
gosha-server --db gosha-demo.db --port 8080
curl http://127.0.0.1:8080/health
```

CLI fallback:

```bash
gosha --db demo.db setup-chat group-1 Europe/Moscow
gosha --db demo.db ask group-1 alen '/deadline_add Презентация | 2026-08-20 | 18:00'
gosha --db demo.db confirm group-1 alen <pending_id> request-001
gosha --db demo.db ask group-1 dasha '/deadlines'
```

Local web/CLI принимают client-supplied actor/role/chat и являются только симуляцией state machine, не authentication evidence.

## Переменные окружения

Скопируйте [.env.example](.env.example); реальные secrets не коммитятся.

| Переменная | Когда нужна | Правило |
|---|---|---|
| `DATABASE_URL` | PostgreSQL/live profile | Только `postgresql://`; silent fallback в SQLite запрещён |
| `TELEGRAM_BOT_TOKEN` | Live Telegram profile | Обязателен только для `--profile live` |
| `GOSHA_PROVIDER` | Выбор provider | `offline` по умолчанию; `openai` — явный opt-in |
| `OPENAI_API_KEY` | OpenAI-compatible provider | Не логируется и не хранится в БД |
| `GOSHA_OPENAI_MODEL` | OpenAI-compatible provider | Явный model ID; default намеренно отсутствует |
| `GOSHA_TELEMETRY_HMAC_KEY` | Live deployment | Deployment-specific secret не короче 32 bytes |
| `GOSHA_TELEGRAM_OFFSET_FILE` | Long polling | Durable cursor path, по умолчанию рядом с SQLite DB |
| `GOSHA_OWNER_USER_ID` | Общая CSAT-статистика | Единственный numeric Telegram user ID с доступом к `/csat_stats` |

Live Telegram profile запускается только с реальными secrets:

```bash
TELEGRAM_BOT_TOKEN='...' \
GOSHA_TELEMETRY_HMAC_KEY='<32+ byte secret>' \
docker compose --profile live up --build bot
```

## Тесты и evaluation

```bash
./scripts/run_all.sh
python -m gosha.cli evaluate data/synthetic-eval.jsonl
python -m gosha.cli evaluate data/synthetic-challenge.jsonl
python -m gosha.cli evaluate data/synthetic-benchmark-v1.jsonl
python scripts/generate_demo_gif.py
```

`run_all.sh` включает Ruff, тесты с branch coverage gate 85%, проверку воспроизводимости benchmark и три rules evaluation. Наборы полностью синтетические. Controlled set проверяет grammar/contract, challenge set фиксирует границы rules baseline. Benchmark содержит 300 строк, но построен из 30 semantic seeds с 10 детерминированными surface transforms и потому не является 300 независимыми кейсами. Эти наборы не доказывают LLM quality, impact или прохождение Bronze gate. Интерпретация: [docs/evaluation-report.md](docs/evaluation-report.md).

Live LLM evaluation запускается только явным model ID, API key и датированными тарифами; секрет не попадает в отчёт:

```bash
OPENAI_API_KEY='...' \
GOSHA_OPENAI_MODEL='<explicit-model-id>' \
GOSHA_LLM_INPUT_USD_PER_MILLION='<dated-rate>' \
GOSHA_LLM_OUTPUT_USD_PER_MILLION='<dated-rate>' \
./scripts/run_llm_evaluation.sh
```

До появления `evaluation/llm-controlled-report.json` и `evaluation/llm-challenge-report.json` live LLM metrics не заявляются.

CI использует PostgreSQL 16 service, запускает suite, собирает Docker image и проверяет `/health`. Файл workflow готов, но reviewer-accessible remote/CI run остаётся внешним gate до отдельной публикации.

## Операторские controls

Глобальные writes stop, LLM-off и scheduled-send stops хранятся в БД, переживают restart, требуют `actor + reason` и оставляют audit trail. При отсутствующей настройке path fail closed.

```bash
gosha-operator --database-url "$DATABASE_URL" writes-global --enabled off \
  --actor oncall --reason 'incident INC-42'
gosha-operator --database-url "$DATABASE_URL" llm-global --enabled off \
  --actor oncall --reason 'provider degradation INC-42'
gosha-operator --database-url "$DATABASE_URL" sends-global --enabled off \
  --actor oncall --reason 'delivery incident INC-42'
gosha-operator --database-url "$DATABASE_URL" delivery-unknown-list
```

Повторное включение — отдельное осознанное действие после review. Полный runbook: [docs/storage-profiles.md](docs/storage-profiles.md); privacy/incident boundary: [SECURITY.md](SECURITY.md).

## Ограничения и roadmap

Сейчас **не доказаны**:

- реальные problem/usability outcomes и экономия времени координатора;
- live scheduled reminder delivery, длительная эксплуатация и разные Telegram-группы;
- качество, стабильность, latency distribution, actual tokens/cost и incremental value live LLM относительно команд; instrumentation реализован, systematic report отсутствует;
- reviewer-accessible remote CI run и production-like deployment;
- willingness to pay, retention, production load и production readiness.

Controlled live smoke с двумя actor-account уже подтвердил feasibility deadline/material interaction в одной приватной группе. Следующие gates: problem research → concept comprehension → 5–7 Telegram usability sessions → live reminder delivery → frozen LLM vs commands comparison → privacy/legal review → limited pilot в 6 чатах. Если AI не снижает effort без роста critical errors, команды остаются primary UX; если другой участник не использует retrieval, scope сужается.

## JMLC, AI Product и личный вклад

Проект создан для JMLC 2026 в треке «Управление ИИ-продуктами» и поступления на программу AI Product AI Talent Hub ИТМО. Он продолжает диплом Алена Давтяна об AI UX: модель предлагает, система проверяет ограничения, человек отвечает за значимое решение.

Ранняя Gosha Box была командной концепцией пяти участников. Личный вклад Алена в эту JMLC-версию: re-scope до дедлайнов и metadata-only URL-материалов; product/AI UX contract; граница LLM/backend/human; метрики и evaluation/pilot design; постановка и приёмка AI-assisted разработки; audit/release responsibility. AI-agent output не считается пользовательским исследованием или внешней валидацией.

## Публичный export и лицензия

Для отдельного чистого reviewer repository запустите [scripts/export_public_repo.sh](scripts/export_public_repo.sh) в пустую внешнюю папку. Скрипт переносит только явно разрешённые Git-tracked файлы, проверяет экспорт на приватные данные и не создаёт remote или Git-историю.

Код распространяется по [MIT License](LICENSE). Публичный remote этим репозиторием не создаётся автоматически.
