# Gosha AI — problem-driven стратегия развития

> **Статус:** стратегия и gates, не обещание roadmap и не результат валидации
> **Принцип:** функция появляется только после evidence проблемы и более дешёвого теста

## 1. Продуктовая логика

Gosha проверяется не как «AI-бот для учёбы», а как управляемый workflow общей памяти. Техническая работоспособность необходима, но не доказывает наличие проблемы, изменение поведения или экономическую ценность.

| Проверяемая проблема | AS IS | Решение/эксперимент Gosha | Метрика | Gate / решение |
|---|---|---|---|---|
| Дедлайн теряется или существует в нескольких версиях | search, pin, переспрос, LMS | chat-scoped deadline с provenance и current status | distinct chats с incident; manual trace; participant corroboration | R-01: `>=8/12`, `>=6/12`, `>=6/12`; иначе resegment/reframe/stop |
| Координатор повторно поддерживает актуальность | повторные публикации, ответы, ручные reminders | один подтверждённый объект, retrieval и recovery | manual intervention rate, coordinator minutes | сравнить baseline и pilot; не выдавать diagnostic outcome за activation |
| Структурированный ввод требует лишних действий | slash-команда/форма | LLM candidate slots + deterministic validation + confirm | task success, time/actions, clarification, abandonment, cost | frozen LLM-vs-commands gate; no lift → commands primary |
| Пользователь не доверяет распознанному сроку | перепроверка автора/исходника | preview, source, timezone, confirm, correction/undo | comprehension, correction/cancel, critical errors | usability `>=80%`, critical `0`; иначе fix before pilot |
| Ценность остаётся только у координатора | личный список одного человека | retrieval и действие второго actor | activation 72h, WAUC, W4 retention | multi-user pilot gate; иначе coordinator-tool pivot |
| Reminder может быть пропущен/продублирован | ручные reminders | durable outbox, current-version jobs, stop controls | scheduled/attempted/delivered/late/duplicate/unknown | live audit без silent missed/duplicate; иначе reminders paused |
| URL-материал теряется | search links, Saved Messages, список | metadata-only URL preview/retrieval | retrieval другим actor, repeat use, URL errors | отдельный exploratory denominator; не смешивать с deadline core |
| Источник истины уже находится в LMS/calendar | ручной перенос из чата | verified capture + write-back | transfer steps/time/errors, API-fit | design-partner workflow evidence; иначе не строить connector |
| Repeat value не покрывает стоимость | бесплатные substitutes | ограниченный group workflow | cost/action, support/chat, payment signal | monetization только после retained value |

## 2. Канонические определения

- **Activated Chat 72h:** в течение 72 часов один участник создаёт подтверждённый дедлайн, другой уникальный участник получает его из общего состояния.
- **Core useful action:** подтверждённое создание, непустой retrieval или подтверждённое исправление/деактивация дедлайна.
- **WAUC:** чат, где за неделю минимум два уникальных участника совершили минимум три core useful actions, включая создание/изменение и retrieval.
- Preview, retry, FAQ, автоматическая доставка и material experiment не являются core useful action deadline core.

## 3. AS IS → transition → TO BE

### Координатор

```text
AS IS: публикует срок → закрепляет/повторяет → отвечает на переспросы → вручную исправляет версию
Transition: reply/mention/command → проверяет preview → confirm
TO BE hypothesis: один current object → retrieval участниками → correction/recovery → reminder по актуальной версии
```

### Участник

```text
AS IS: вспоминает формулировку/автора → search → сверяет несколько сообщений → спрашивает координатора
Transition: вызывает список в том же чате
TO BE hypothesis: получает current deadline с источником и не переносит контекст вручную
```

### Куратор / L&D

```text
AS IS: переносит договорённость между чатом и LMS/calendar/tracker
Transition experiment: подтверждает candidate и concierge write-back
TO BE hypothesis: verified capture автоматически записывает объект в существующий source of truth и возвращает audit card
```

## 4. B2C strategy

- Первый ICP: взрослый учебный Telegram-чат с повторяющимися сроками и непоследовательным внешним source of truth.
- User: участник; pain owner/initiator: coordinator/admin; data steward: доверенный участник; buyer пока неизвестен.
- Единица value/economics: retained active chat, не зарегистрированный пользователь.
- Acquisition hypothesis: coordinator/participant retained chat приглашает Gosha в другой независимый чат после observed useful outcome.
- Growth считается только по `invite → install → multi-user activation → retention`; установка не является ростом ценности.
- Payment test начинается после repeat use: concrete cohort offer, deposit/payment/paid continuation; мнение о WTP не проходит gate.

## 5. B2B strategy

B2B-направление — не новый мессенджер и не параллельный task manager:

```text
сообщение → AI candidate → deterministic validation → human confirmation
→ write-back в LMS/calendar/tracker → audit card в исходном канале
```

- User: coordinator/curator.
- Buyer hypothesis: education operations, L&D или владелец cohort workflow.
- Stakeholders: platform owner, IT/security, procurement, data/privacy.
- Billing unit hypothesis: cohort/workspace/contract, не seat по умолчанию.
- Обязательные evidence: повторяемый workflow, manual cost trace, API-fit, roles/audit, data residency, procurement и support.
- Build connector разрешён только после design partner и concierge/fake-door test. Telegram value не подтверждает B2B demand.

## 6. Горизонты и gates

| Horizon | Неопределённость | Минимальный шаг | Gate | При непрохождении |
|---|---|---|---|---|
| 0. JMLC evidence | что реализовано и измерено | reproducible release + claim/evidence register | у claim есть source, denominator, limitation | ослабить/удалить claim |
| 1. Problem | существует ли повторяемая боль | R-01 incident interviews + artifacts/negatives | pre-registered problem thresholds | resegment/coordinator pivot/stop |
| 2. Trust/usability | понятны ли preview, scope, recovery | concept 8 + usability 5–7 | comprehension/completion `>=80%`, critical `0` | исправить UX; no pilot |
| 3. AI lift | нужен ли LLM | frozen counterbalanced comparison | practical effort lift, non-inferior success, critical `0`, cost cap | commands primary; LLM optional/off |
| 4. Operations | безопасна ли доставка | scheduled live test + stops/privacy review | complete audit, no silent/duplicate | hold and fix |
| 5. Limited pilot | есть ли repeat multi-user value | 2 baseline + 4 pilot weeks, 6 chats | activation/WAUC/W4/safety gates | iterate/pivot/stop |
| 6. B2C viability | кто платит за repeat value | concrete retained-chat offer | payment/deposit/paid continuation | change buyer/package |
| 7. B2B discovery | повторяется ли organizational workflow | mapping + concierge + security/procurement | multiple cases + design partner | no universal connector |

## 7. Functional expansion map

| Problem cluster | Возможная capability | Evidence before build | Out/stop condition |
|---|---|---|---|
| версии дедлайна конфликтуют | conflict resolution/current version | repeated update incidents + recovery usability | LMS already sufficient |
| участники не замечают изменения | configurable digest/reminders | delivery reliability + useful-reminder signal | mute/complaint/no action |
| источник истины внешний | LMS/calendar export/write-back | observed transfer cost + design partner | custom one-off only |
| вопросы повторяются | deadline-focused digest/retrieval | repeated questions tied to stored objects | general chat summarization demand only |
| несколько потоков/когорт | coordinator multi-chat view | retained coordinator with multiple eligible chats | single-chat value absent |
| материалы теряются отдельно | metadata URL registry | independent retrieval/repeat-use signal | no value beyond Telegram link search |
| нужен общий task management | **не строить автоматически** | evidence that capture, not existing tracker depth, is wedge | use/integrate existing tracker |
| нужен RAG/полное чтение чата | **out of scope** | separate consent/privacy/value study | passive surveillance risk |

## 8. Invalid experiment vs product failure

- `INVALID/HOLD`: broken instrumentation, violated allocation, missing denominator, immature observation window, delivery outage unrelated to hypothesis.
- `FAIL/STOP/PIVOT`: valid study прошёл по протоколу и не достиг frozen gate.

Нельзя объявлять продуктовую гипотезу опровергнутой из-за невалидного эксперимента; нельзя повторять валидный отрицательный тест до получения удобного результата без новой версии гипотезы.
