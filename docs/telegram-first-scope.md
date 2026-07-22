# Gosha AI — Telegram-first scope для JMLC

Статус: канонический acceptance contract после повторной сверки с `Gosha Presa.pdf` и `идея гоши.docx` 17 июля 2026 года.

## Продукт и поверхность

Gosha — бот, добавляемый в групповой учебный Telegram-чат. Основной пользовательский опыт, конкурсное демо и критерий готовности относятся к Telegram. Локальный web-интерфейс остаётся только debug-консолью для воспроизводимой проверки backend state machine и не может подменять бота.

Целевая цепочка:

```text
Telegram group → trusted Bot API update → backend → intent/slots provider
→ deterministic validation/business rules → persistent store/outbox
→ Telegram response or scheduled delivery
```

LLM понимает язык и возвращает структурированные intent/slots. У неё нет права записи, выбора `chat_id`, назначения ролей, расчёта времени или самостоятельной отправки. Backend берёт `chat_id`, `user_id`, reply provenance и роль только из Telegram update/Bot API.

## Обязательный runnable MVP

### Telegram adapter

- long polling с offset recovery; webhook остаётся production alternative;
- токен только из `TELEGRAM_BOT_TOKEN`, без логирования;
- групповые команды, явное упоминание бота и reply на сообщение самого бота;
- для natural-language mention Group Privacy отключается; transport может доставлять обычную переписку, но adapter игнорирует её до provider;
- inline keyboard для `Подтвердить` / `Отменить`; callback всегда получает `answerCallbackQuery`;
- callback привязан к actor, chat, pending action и сроку жизни;
- реальные `chat_id`/`from.id`; роль для привилегированного действия проверяется через `getChatMember`, а не берётся из текста или UI;
- Telegram errors классифицируются на retryable/permanent; delivery идемпотентна и восстанавливается после рестарта.

### Дедлайны и доставка

- добавить дедлайн с обязательной датой и опциональным временем; default `09:00` явно виден в preview;
- общий список текущего чата, grounded-вопросы и reply к сообщению конкретного дедлайна;
- correction/deactivation с before/after preview и audit;
- реальная отправка due reminders в Telegram через durable outbox;
- cadence исходного документа:
  - общий digest в воскресенье 19:00 перед неделей дедлайна;
- точный T-24 всегда;
- IANA timezone на чат, UTC storage, DST validation и пересчёт jobs после correction/deactivation.

### Материалы

- сохранить ссылку с описанием в пространстве текущего чата;
- показать/найти материалы без доступа к данным другого чата;
- бот не открывает URL, не читает содержимое страницы и не использует RAG;
- ограниченный групповой вызов известных участников входит как отдельный experimental flow: LLM intent → preview → confirm → durable send, максимум 30 адресатов и cooldown 10 минут;
- полный исторический `/all`, FAQ и inline mode не входят в JMLC release: Bot API не позволяет перечислить всех молчавших участников.

Официальные основания поверхности: [Telegram Bot API](https://core.telegram.org/bots/api), [Bots FAQ / privacy mode](https://core.telegram.org/bots/faq).

## Данные и среды

- production target — PostgreSQL;
- SQLite допустим только как local/test profile;
- schema/migrations и repository interface должны сохранять chat isolation, audit, pending actions, outbox и idempotency в обеих средах;
- никаких реальных учебных сообщений, токенов или персональных чатов в репозитории.

## Что не требуется для конкурсного MVP

Широкая Gosha Box из презентации остаётся vision: собственная чат-платформа, course-aware RAG по полному курсу, календарная интеграция всех участников, автоматический подбор встреч, викторины и AI-поиск по любым вложениям. Они не должны появляться в текущих claims или интерфейсах как реализованные функции.

## Evidence gate перед формулировкой «работающий Telegram-бот»

Обязательно:

1. adapter contract и весь domain проходят автоматические тесты;
2. воспроизводимая Bot API MOCK-симуляция проверяет update → callback → commit → send path;
3. scheduler/outbox test доказывает фактический вызов `sendMessage`, retry и отсутствие дубля;
4. если доступен тестовый токен — smoke в отдельной тестовой группе с redacted transcript;
5. controlled live claim ограничен фактическим scope: «deadline/material interaction прошёл smoke в одной приватной группе»; это не два независимых пользователя, pilot, live reminder delivery или production reliability.

Нельзя выдавать mock, local web, рассчитанный job или synthetic evaluation за живую доставку, Telegram authentication, пользовательский пилот либо качество LLM.
