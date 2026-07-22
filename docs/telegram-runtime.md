# Telegram runtime

Основная продуктовая поверхность Gosha — групповой Telegram-чат. `server.py` и web-интерфейс остаются debug-инструментами для локального просмотра state machine.

## Запуск

1. Создать бота через BotFather и добавить его в отдельную тестовую группу.
2. Для главного сценария `@username свободная фраза` отключить Group Privacy через BotFather (`/setprivacy` → Disable). При включённой Group Privacy Telegram может не доставлять такие сообщения боту; тогда гарантированно доступны только slash-команды. После отключения transport доставляет сообщения группы, но adapter приложения пропускает к AI только команды этому боту, явное `@username` и reply на сообщение самого бота; обычная переписка отбрасывается до provider.
3. Установить проект и передать токен только через окружение:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
TELEGRAM_BOT_TOKEN='...' gosha-telegram --db gosha.db
```

Experimental OpenAI adapter требует отдельного явного opt-in; mock contract не доказывает live-работоспособность:

```bash
TELEGRAM_BOT_TOKEN='...' OPENAI_API_KEY='...' \
  GOSHA_OPENAI_MODEL='<explicit-model-id>' gosha-telegram --db gosha.db --provider openai
```

Natural-language path понимает, например, `@goshadrugbot добавь дедлайн тест 27 июля в шесть вечера`. LLM извлекает intent/title, нормализованные кандидаты даты/времени и их дословные evidence-фрагменты. Backend проверяет evidence относительно исходного запроса, нормализует календарь в timezone чата, а абсолютная дата записывается только после preview и confirm.

Токены не сохраняются в SQLite и не логируются. При первом запуске администратор группы выполняет `/setup Europe/Moscow` или указывает другую IANA timezone.

Production-профиль выбирается только явным `DATABASE_URL` и не делает silent fallback в SQLite:

```bash
pip install -e '.[postgres]'
DATABASE_URL='postgresql://...' TELEGRAM_BOT_TOKEN='...' \
  GOSHA_TELEMETRY_HMAC_KEY='<secret-at-least-32-bytes>' \
  GOSHA_TELEGRAM_OFFSET_FILE='/data/update.offset' gosha-telegram
```

## Реализованный Telegram flow

- реальные `chat.id` и `from.id` берутся только из Bot API update;
- username бота определяется через `getMe`;
- команды с суффиксом `@bot_username`, явное упоминание и reply-to-bot нормализуются adapter;
- correction/deactivation и их callback-confirm доступны только Telegram admin и повторно получают роль через `getChatMember`; CLI/web steward остаётся недоверенной debug-симуляцией;
- correction поддерживает ссылку на существующий дедлайн по естественному названию: один уверенный кандидат текущего чата ведёт в preview, несколько кандидатов требуют явного ID, отсутствие совпадений ничего не меняет;
- свободная просьба позвать/собрать/отметить всех классифицируется как `call_all_participants`, показывает число известных адресатов и требует подтверждения;
- вызов отправляется через durable outbox, ограничен 30 адресатами и cooldown 10 минут на чат;
- реестр известных участников обновляется по сообщениям, callback и service update `new_chat_members`, но текст обычных сообщений не сохраняется и не передаётся provider;
- успешный `/setup` автоматически публикует onboarding-карточку с кнопкой `✅ Подключиться к Gosha`; admin может повторить её через `/gosha_invite`, а счётчик явных подключений обновляется после callback;
- первого числа каждого месяца в 12:00 по timezone чата scheduler создаёт один CSAT-опрос; интерфейс показывает только шесть emoji-кнопок, а numeric score `1–6` хранится в backend;
- `/csat_stats`, `/csat_stats YYYY-MM` и `/csat_stats all` агрегируют все чаты, но доступны только Telegram ID из `GOSHA_OWNER_USER_ID`;
- deadline и URL material write проходят preview и inline `Подтвердить` / `Отменить`;
- callback привязан к `chat_id`, actor и TTL pending action; каждый callback получает `answerCallbackQuery`;
- long polling сохраняет следующий update offset атомарно после обработанного update;
- due job перед отправкой переводится `claimed → sending`, затем в `delivered`, `retry_wait`, `failed_permanent` или `delivery_unknown`;
- потеря HTTP-ответа на `sendMessage` не вызывает blind retry: оператор должен разрешить ambiguous delivery вручную.

Команды MVP:

```text
/setup Europe/Moscow
/deadline_add Название | YYYY-MM-DD | HH:MM
/deadlines
/deadline_correct ID | YYYY-MM-DD | HH:MM
/deadline_deactivate ID
/cancel_deadline ID
/material_add https://example.org/file | Описание
/materials [поисковый запрос]
/material_correct ID | URL | описание
/material_deactivate ID
/cancel_material ID
/call_all
/gosha_invite
/gosha_join
/gosha_leave
/csat_stats [YYYY-MM|all] — только владелец deployment
```

CSAT-шкала в UI: `😡 😞 🙁 😐 🙂 🤩`; цифры пользователю не показываются. Один пользователь даёт один ответ на месячный опрос и может заменить его повторным нажатием. Агрегация возвращает среднюю оценку, медиану и количество ответов; по умолчанию используется последний месяц с ответами, `all` считает всё время. Реальные CSAT-ответы ещё не собраны и не являются доказанным пользовательским результатом.

Нажатие onboarding-кнопки и `/gosha_join` явно включают пользователя в будущие групповые вызовы, `/gosha_leave` исключает. Callback особенно полезен участникам без публичного username: Telegram передаёт их trusted `user.id` и фиксирует прямое взаимодействие с ботом. Telegram Bot API не предоставляет полный перечень участников: вызов охватывает только известных активных пользователей, а не гарантированно всю историческую группу. Username упоминается как `@username`; при его отсутствии используется поддерживаемая Telegram ссылка `tg://user?id=...`. Боты и сам инициатор исключаются.

Дата может быть задана как `YYYY-MM-DD`, `27 июля`, `27.07`, `завтра`, `послезавтра` или ближайший день недели. Год без явного указания выбирается как ближайшая не прошедшая календарная дата в timezone чата. Время опционально; `09:00` по умолчанию явно показывается в preview. Preview всегда содержит абсолютную дату, время, русский день недели и IANA timezone; до подтверждения записи нет. При исправлении поля `до` и `после` показываются симметрично. Напоминания: агрегированный воскресный дайджест и точный T-24 по времени чата.

## Recovery и безопасная доставка

Long-poll cursor хранится по умолчанию в `<db>.telegram-offset`; путь можно задать через `GOSHA_TELEGRAM_OFFSET_FILE`. После рестарта незапущенный expired claim возвращается в retry. Если процесс остановился после перехода в `sending`, job становится `delivery_unknown`, потому что Telegram мог принять сообщение до потери ответа.

`429` и подтверждённые server-side ошибки используют bounded exponential retry. `400/403` считаются permanent. Один `job_key` не отправляется повторно после `delivered`.

Операторские controls меняются отдельной CLI с обязательными actor/reason и audit trail:

```bash
gosha-operator writes-global --enabled off --actor oncall --reason incident-123
gosha-operator llm-global --enabled off --actor oncall --reason provider-degradation
gosha-operator sends-global --enabled off --actor oncall --reason delivery-incident
```

Повторное включение использует те же команды с `--enabled on` только после проверки причины. Safe reads остаются доступны при writes stop; LLM-off переключает core на детерминированный fallback.

## Честная граница доказательств

Adapter и полный update → preview → callback → commit → Bot API response flow проверены локальным HTTP mock server. Outbox отдельно проверяет фактический `sendMessage`, отсутствие повтора после success и `delivery_unknown` при потере transport response.

Без реального `TELEGRAM_BOT_TOKEN` это называется «реализованный Telegram Bot API adapter, проверенный на mock server». Текущий release отдельно прошёл controlled smoke одной приватной группы с двумя actor-account; это не usability, pilot, live reminder delivery или production reliability.

OpenAI path следует официальным контрактам [Models](https://platform.openai.com/docs/models) и [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs). Контракт response/refusal/schema проверен mock-тестами; отдельные controlled live requests подтверждают feasibility, но не заменяют frozen quality/latency/cost evaluation. `GOSHA_OPENAI_MODEL` обязателен.

Остальные функции исходной широкой Gosha Box концепции остаются vision и не входят в этот release.
