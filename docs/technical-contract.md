# Gosha AI — технический контракт JMLC MVP

Статус: release contract воспроизводимого портфельного vertical slice. Он демонстрирует критический deadline flow, но не является полным build канонического limited pilot и не означает, что пилот или Bronze gate пройдены.

## Core job и границы

Пользователь учебного Telegram-чата может создать общий дедлайн, другой участник — получить его, а доверенный участник — исправить или деактивировать. Напоминания рассчитываются backend, данные изолированы по `chat_id`.

В MVP входят: deadline и URL-material create → preview → confirm, list/search, retrieval другим участником, correct/deactivate → preview → confirm, 10-minute author undo, opt-in/observed participant registry, подтверждаемый групповой вызов, monthly emoji CSAT и owner-only aggregate, audit, idempotency, IANA timezone, T-24/Sunday digest, persistent scheduled-send/writes/LLM controls, deterministic fallback, Telegram adapter и delivery worker. Telegram path и worker проверены на mock Bot API; deadline/material interaction дополнительно прошёл controlled live smoke в одной приватной группе с двумя actor-account. Local web/API/CLI — вторичная debug-поверхность.

В релиз входят два типа общей памяти: дедлайны и URL-материалы с описанием, а также ограниченный групповой вызов известных участников. Не входят: чтение/парсинг содержимого ссылок и файлов, RAG, FAQ, встречи, неограниченный `/all`, inline-каталог, Mini App, произвольные напоминания и чтение текста обычной переписки. Идеи из концептуальной презентации не расширяют scope без новой записи решения.

`call_all_participants` — отдельный intent без свободных side effects. Backend берёт инициатора и чат только из Telegram update, строит preview, привязывает confirm к actor/chat, исключает инициатора и opted-out пользователей, допускает не более 30 известных адресатов и не чаще одного подтверждённого вызова за 10 минут. Получатели фиксируются во временном outbox payload; после успешной доставки payload очищается. Telegram не предоставляет полную выгрузку состава группы, поэтому семантика команды — «позвать всех известных активных участников», а не гарантировать полный исторический membership.

Participant onboarding публикуется после успешного admin `/setup` и повторяется admin-командой `/gosha_invite`. Inline callback `g:join` получает `chat_id` и `user_id` только из Bot API update, явно активирует/возвращает участника, не дублирует запись и обновляет публичный счётчик явных подключений. Callback не вызывает LLM. `/gosha_leave` сохраняет opt-out, который обычное наблюдение не отменяет.

Monthly CSAT создаёт уникальный survey/outbox job на `chat_id + local YYYY-MM` и доставляет его первого числа в 12:00 timezone чата. Emoji callback содержит backend score `1–6`, но UI и acknowledgement не показывают цифру. Уникальность `(survey_id,user_id)` предотвращает двойной учёт и разрешает заменить ответ. Cross-chat callback отклоняется. Общая статистика вычисляет average, median и count по последнему периоду, указанному `YYYY-MM` или всему времени; `/csat_stats` проверяет exact `GOSHA_OWNER_USER_ID`, а не роль admin конкретного чата.

## Граница AI и backend

LLM или offline provider возвращает только `intent` и кандидаты slots. Для model-normalized даты/времени и названия цели correction обязательны дословные evidence-фрагменты исходного запроса; backend сверяет их до календарной нормализации и object resolution. Поиск цели ограничен активными дедлайнами текущего `chat_id`; единственный уверенный кандидат допускается к preview, несколько требуют ID. Провайдер не получает инструментов записи и не может выбрать немедленную отмену. Backend применяет allowlist, проверяет entry point, чат, роль, timezone, дату, обязательные поля, pending action, duplicate business key и idempotency key. Любое изменение состояния требует явного подтверждения. При отказе AI allowlisted команды разбираются детерминированно без сетевого вызова.

В local web/API/CLI actor, роль, `chat_id` и entry point задаются самим demo-клиентом. Это симуляция доверенного adapter context, а не authentication/authorization boundary. Telegram adapter выводит identity/chat/entry point из update и проверяет admin через Bot API. Путь проверен на mock Bot API и одним controlled live smoke; production reliability, масштаб и длительная эксплуатация не проверены.

## Данные и инварианты

- SQLite — local/test profile; PostgreSQL с migrations `001–005` — production target. SQL-запросы всегда фильтруются по `chat_id`.
- Дедлайн хранит локальное время, IANA zone и UTC instant.
- Успех возвращается только после commit.
- Pending action привязан к chat, actor и сроку жизни.
- Pending action атомарно потребляется один раз; correction/deactivation preview содержит expected object version.
- Idempotency key привязан к fingerprint запроса; повтор другого запроса с тем же ключом отклоняется.
- Reminder jobs пересчитываются при подтверждённой правке и отменяются при деактивации.
- Audit event хранит actor, действие, before/after и correlation id.
- Global writes stop и LLM-off хранятся в БД, переживают рестарт, по умолчанию fail closed при отсутствующей настройке и повторно проверяются в транзакции до side effect.
- В product telemetry нет сырого текста или raw user/chat IDs: идентификаторы псевдонимизируются deployment-keyed HMAC; demo использует только синтетические данные.

## Reminder cadence

Vertical slice рассчитывает Pilot Cadence A: один агрегированный Sunday digest job на `chat_id + local week` и отдельный T-24 job на дедлайн. Если дедлайн создан менее чем за 24 часа, T-24 не создаётся. Изменение состояния пересобирает будущие digest jobs из активных дедлайнов. Delivery worker реализован и mock-tested; живая доставка не проверена.

## Release gates для портфельного MVP

1. Unit/integration tests проходят из чистого окружения.
2. Cross-chat read/change, write without confirmation, duplicate confirmation и mass action не создают side effects.
3. Offline evaluation публикует состав синтетического набора, evaluator version, per-intent метрики, slot value accuracy и required-slots case exact match. Case-exact метрика проверяет все размеченные обязательные поля, но не штрафует лишние неразмеченные поля; она не называется slot micro-F1 или строгим full-set exact match. Результат не называется LLM quality и не заменяет Bronze set на 300 кейсов.
4. Реальные Telegram-чаты остаются NO-GO до legal/privacy review, frozen 300-case evaluation и полного checklist канонических протоколов 13–15.
