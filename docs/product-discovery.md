# Gosha AI — product discovery для JMLC

> **Трек:** «Управление ИИ-продуктами»
> **Стадия:** working MVP + planned discovery with frozen public protocols
> **Обновлено:** 19 июля 2026
> **Evidence boundary:** problem–solution fit, usability, retention, AI lift и monetization ещё не подтверждены

Связанные канонические документы: [основание из ВКР](thesis-foundation.md), [problem-driven стратегия](product-development-strategy.md), [рынок и экономика](market-and-business-model.md), [research package](research/README.md), [evidence register](evidence-register.md).

## 1. Продуктовое решение

**Gosha AI — проверяемая общая память взрослой учебной Telegram-группы.** Явная фраза о дедлайне или URL-материале превращается в структурированное preview; объект сохраняется только после human confirm и затем доступен другим участникам текущего чата.

Первый продуктовый клин — не «AI для всего обучения», а один коллективный объект: актуальный дедлайн с provenance, recovery и безопасной доставкой напоминаний.

```text
explicit invocation
→ LLM/rules: intent + candidate slots
→ backend validation
→ preview
→ human confirm
→ commit + audit
→ retrieval вторым actor
→ recovery / reminder outbox
```

## 2. Гипотеза проблемы

В активных учебных Telegram-группах взрослых пользователей без устойчивого единого источника дедлайны и ссылки возникают в потоке сообщений. Координатор повторяет и исправляет информацию, участники ищут, переспрашивают и вручную переносят её в календарь, Saved Messages, таблицу или LMS.

Это гипотеза. Код, synthetic evaluation, controlled live smoke и AI-agent analysis не заменяют problem validation.

### Наблюдаемый problem incident

Сам факт появления дедлайна не является проблемой. Квалифицированный incident требует хотя бы одного признака:

- поиск или переспрос уже опубликованного срока;
- конфликт старой и новой версии;
- ручная повторная публикация или исправление координатором;
- перенос между Telegram, LMS, календарём или таблицей;
- пропуск, задержка или иное наблюдаемое последствие;
- зависимость от одного доступного координатора.

## 3. Сегмент, роли и JTBD

Первый сегмент — магистратуры, короткие курсы, интенсивы и проектные команды, где Telegram является основным оперативным каналом, сроки регулярно возникают или меняются, а LMS отсутствует либо обновляется непоследовательно.

| Роль | Работа и предполагаемая ценность | Статус |
|---|---|---|
| Координатор/admin | объявляет и обновляет сроки, отвечает на повторные вопросы, может установить бота | primary pain owner и initiator — гипотеза |
| Участник | получает актуальную версию без поиска и переспроса | primary beneficiary — гипотеза |
| Data steward/admin | разрешает конфликты, исправляет или деактивирует объект | trust role продукта |
| Куратор/L&D operator | ведёт несколько групп и потенциально оплачивает снижение ручной нагрузки | B2B buyer hypothesis |
| Platform owner | может встроить verified capture/write-back workflow | integration partner hypothesis |

### JTBD координатора

> Когда в учебном чате появляется или меняется важный срок, я хочу один раз превратить его в проверенную актуальную запись для всей группы, чтобы не поддерживать список вручную и не отвечать повторно.

### JTBD участника

> Когда мне нужен актуальный срок или ранее сохранённый материал, я хочу получить его в том же чате, чтобы не искать по истории и не переносить контекст в другой инструмент.

### Trust JTBD

> Когда AI разобрал сообщение и собирается изменить общую информацию, я хочу видеть точную интерпретацию и иметь путь отмены или исправления, чтобы убедительный, но неверный результат не стал источником истины.

### Единица ценности

Единица продукта — **eligible chat**, не отдельный аккаунт. Первая ценность возникает только когда один actor создаёт/изменяет объект, а другой actor получает актуальную версию.

### Negative segment

Gosha, вероятно, не нужен группе, если дисциплинированно обновляемая LMS/календарь уже является единым источником истины, сроки редко меняются, Telegram не используется для оперативной координации или участники не готовы добавить стороннего бота.

## 4. AS IS и switching trigger

| Альтернатива | Сильная сторона | Возможный разрыв | Что проверяется |
|---|---|---|---|
| Telegram search | бесплатно, уже доступно | ищет сообщения, а не одну актуальную версию | время и успешность последнего поиска |
| Закреп | минимальное изменение поведения | требует ручного владельца и обновления | кто обновляет и как разрешаются версии |
| Координатор | понимает контекст | повторная нагрузка и single point of failure | частота и время ручных действий |
| LMS | официальный структурированный контур | может быть неполной/неактуальной для chat-born deadlines | где LMS уже полностью закрывает job |
| Личный календарь/task manager | надёжное персональное планирование | ручной перенос, нет общего состояния | доля реально переносимых сроков |
| Reminder/task bots | работают внутри Telegram | reminder сам по себе не гарантирует provenance/recovery | mystery shopping одинаковых сценариев |

Главный конкурент — связка `координатор + закреп + поиск + LMS/календарь`.

**Switching trigger:** недавний повторяемый retrieval/update incident, у которого есть ручной след или последствие, а текущий источник истины не решает конфликт с приемлемым effort. Наличие интереса к AI switching trigger не является.

## 5. Product contract и scope по стадиям

| Capability | Working JMLC release | Product role | Formative usability | Limited pilot | Claim boundary |
|---|---|---|---|---|---|
| Deadline lifecycle | реализован | primary wedge | primary denominator | core | feasibility, не value |
| URL-material metadata | реализован | secondary experiment | отдельный exploratory slice | off by default/feature flag | не RAG и не pilot core |
| Preview/confirm | реализован | trust contract | primary | required | measured by tests, usability unknown |
| Retrieval другим actor | реализован/mock + controlled smoke | multi-user value condition | primary | required | smoke не adoption |
| Undo/correct/deactivate | реализован | recovery/trust | role-applicable tasks | required | recovery logic, не perceived trust |
| T-24/Sunday digest | scheduler/worker реализован и mock-tested | outcome/noise hypothesis | comprehension only | live audit required | live delivery не доказана |
| LLM entry | adapter + один private live request | optional effort reducer | сравнивается отдельно | on/off by AI lift gate | compatibility, не quality |
| Commands/rules | реализованы | baseline и fail-safe fallback | mandatory fallback task | required | rules challenge показывает limits |
| Групповой вызов известных участников | реализован, mock-tested | secondary coordination experiment | comprehension/safety only | off by default до privacy review | не полный membership и не validated value |
| RAG, meetings, полный `/all`, Mini App, чтение текста переписки | не реализованы | out of scope | boundary comprehension | out | не обещать |

Working release реализует два объекта, чтобы показать переиспользуемость lifecycle. Limited pilot сознательно сужается до дедлайна, чтобы causal signal не смешивался с material experiment.

### Acceptance outcome

```text
actor A создаёт подтверждённый deadline
→ actor B получает его
→ ошибка обратимо исправляется
→ reminders используют только актуальную версию
→ чат повторяет multi-user outcome в следующем периоде
```

## 6. Роль AI и baseline без AI

LLM получает минимальный текст явного вызова и предлагает только `intent + candidate slots`. У неё нет SQL, write/send tools, роли, `chat_id` или права выбрать последствие.

Backend проверяет entry point, schema, literal evidence для указанной пользователем даты/времени/URL/ID, timezone/DST, permissions, pending ownership, expected version и idempotency. Если время не указано, backend применяет явно показанный deterministic default `09:00`; literal check времени действует только при наличии временной фразы в исходном вводе. Любое изменение требует actor-bound confirm. Название, описание и search query видны в preview до записи.

Текущий provider path принимает свободные формулировки и извлекает intent/slots; backend отдельно нормализует явно написанные даты (`27 июля`, `27.07`, `завтра`, ближайший день недели или `YYYY-MM-DD`) относительно timezone чата и показывает абсолютный результат до confirm. Выигрыш effort относительно команд ещё не измерен.

### AI-гипотеза

Natural-language entry остаётся primary только если по сравнению с deterministic commands на одном backend:

- повышает или сохраняет end-to-end task success;
- снижает время, действия или clarification burden;
- не создаёт critical errors;
- укладывается в frozen latency/cost/fallback caps.

Если lift не подтверждён, commands становятся primary, а LLM — optional/off. Это продуктовое решение, а не технический провал.

## 7. Стратегический выбор

| Решение | Почему выбрано | Текущее evidence | Что опровергнет | Следующий шаг |
|---|---|---|---|---|
| Deadline-first | один понятный коллективный объект и цена ошибки | working lifecycle | problem incidents редки или LMS достаточно | problem interviews |
| Chat-level value | объект общий, а не персональный | multi-actor flow реализован | retrieval/повтор выполняет только coordinator | 6-chat pilot / coordinator pivot |
| Coordinator-led adoption | у координатора предполагаемая боль и admin ability | role logic, не user evidence | координатор не видит effort или не может установить | distinct-chat research |
| Materials secondary | lifecycle уже переиспользован | working metadata flow | отдельной ценности/поведения нет | exploratory usability slice |
| Commands fallback | core не должен зависеть от вероятностного provider | rules/commands реализованы | deterministic flow непригоден пользователю | usability comparison |
| B2B только как write-back | не строить новый messenger/task manager | platform APIs — desk hypothesis | нет design partner/API-fit/workflow cost | buyer/platform discovery |

## 8. Текущая доказательная база

| Evidence | Status | Что доказывает | Что не доказывает |
|---|---|---|---|
| 143 tests passed, 1 PostgreSQL skipped at default; 144 passed with PostgreSQL 16; 85% branch coverage gate | MEASURED LOCAL | service/safety invariants, migrations `001–005` и quality floor текущего build | production reliability и user value |
| Rules controlled `n=26`, accuracy/F1 `1.0/1.0` | MEASURED SYNTHETIC | поддерживаемая grammar/contract | real language/LLM quality |
| Rules challenge `n=24`, accuracy `0.4583`, macro-F1 `0.5467` | MEASURED SYNTHETIC | хрупкость baseline и необходимость comparison | что LLM решит проблему |
| Telegram adapter/worker tests | MOCK | API path, callbacks, retry/unknown behavior | live reliability |
| Private group, two actor-account smoke | CONTROLLED LIVE PRIVATE | deadline/material interaction feasibility | два независимых пользователя, usability, pilot |
| One provider request | CONTROLLED LIVE PRIVATE | единичная compatibility/availability | model quality, SLA, cost, AI lift |

Полный claim ledger: [evidence-register.md](evidence-register.md). Private raw evidence не публикуется; его отсутствие у reviewer явно отмечено как limitation.

## 9. Реестр гипотез

| ID | Контур | Гипотеза | Current status | Опровергающий тест | Решение при failure |
|---|---|---|---|---|---|
| `H-P01` | Desirability | у qualified chats есть повторяемый retrieval/update incident | NOT MEASURED | 12 distinct coordinators + counterexamples | stop/resegment |
| `H-P02` | Adoption | coordinator инициирует установку и поддерживает source of truth | NOT MEASURED | behavior/permission research | другой initiator или stop |
| `H-P03` | Multi-user | второй actor получает и повторяет value | FEASIBILITY ONLY | usability + limited pilot | coordinator tool pivot |
| `H-P04` | Material | URL metadata создаёт отдельную пользу | FEASIBILITY ONLY | separate slice/feature flag | выключить material |
| `H-A01` | AI lift | LLM снижает effort против commands | NOT MEASURED | counterbalanced comparison | commands primary |
| `H-T01` | Trust | preview/recovery понятны и предотвращают unsafe action | LOGIC TESTED | 5–7 usability sessions | redesign before pilot |
| `H-O01` | Operations | reminders доставляются без critical noise/duplicates | MOCK ONLY | live scheduled delivery + audit | pause cadence |
| `H-R01` | Retention | чат повторяет useful multi-user outcome в W4 | NOT MEASURED | 6-chat pilot | iterate/stop |
| `H-V01` | Viability | retained value выдерживает AI/support cost | NOT MEASURED | cost per successful action | simplify/offline/provider change |
| `H-M01` | Monetization | buyer принимает конкретный paid continuation | NOT MEASURED | deposit/payment/paid pilot | reframe buyer/offer |

## 10. Контракт метрик

### Problem research

- `Recent incident rate = distinct qualified coordinator chats with incident / 12 distinct coordinator chats`.
- `Manual trace rate = coordinators with concrete workaround/manual trace / 12`.
- `Participant corroboration = participants reconstructing concrete retrieval/update episode / 12`.
- Negative cases: минимум 4 внутри primary coordinator/participant corpora.

Proposed problem gate: incident `>=8/12`, manual trace `>=6/12`, participant corroboration `>=6/12`. Это pre-registered threshold, не результат.

### Product metrics

**Activated Chat 72h:** eligible chat, где в первые 72 часа один actor подтвердил валидный deadline, а другой уникальный actor получил его через list/get flow.

**Core useful action:** подтверждённое создание, непустой retrieval, подтверждённое исправление или деактивация deadline. Preview, clarification, FAQ, retry, auto-reminder, material и operator action не считаются core useful action limited pilot.

**WAUC:** eligible chat с минимум двумя уникальными участниками и минимум тремя core useful actions за chat-relative 7-day window, включая create/change и retrieval.

**W4 retained chat:** активированный чат, снова выполнивший WAUC в четвёртую полную pilot week.

**Manual deadline intervention rate:** число ручных повторных публикаций/уточнений/исправлений из-за retrieval/update friction, делённое на число активных deadlines chat-week. Outcome показывается с raw counts и baseline, отдельно от primary adoption gates.

### AI/product experience

- end-to-end task success;
- time/actions/clarifications to valid preview;
- result comprehension;
- wrong date/time/URL and false write;
- intent accuracy/macro-F1, required-slot recall и normalized date/time accuracy;
- p50/p95 latency, tokens, calls/retries, fallback rate;
- direct cost per successful task.

### Critical guardrails

- cross-chat disclosure/change: `0`;
- write without valid actor-bound confirm: `0`;
- false success/false reminder from ambiguous input: `0`;
- uncontrolled mass action: `0`;
- critical privacy/security incident: `0`;
- silent missed or duplicate mandatory delivery: `0` for limited-pilot Expand.

Техническая спецификация измерений: [research/pre-registration.md](research/pre-registration.md).

## 11. Эксперименты и stage gates

| Gate | Метод | Frozen sample/unit | Primary decision | GO | ITERATE / STOP |
|---|---|---|---|---|---|
| A Problem | incident interviews + artifacts/counterexamples | 12 coordinator chats, 12 participants, 4 curators | существует ли qualified problem | proposed thresholds §10 | слабый signal → segment/reframe/stop |
| B Comprehension | concept stimulus | 8 adults | понятны scope, memory и recovery | `>=80%` correct | revise concept |
| C Usability/trust | mobile Telegram | 5–7 new adults | core tasks без help, zero critical | completion/comprehension `>=80%`, critical `0` | fix UX before new sample |
| D Live delivery | controlled scheduled run | frozen jobs/windows | delivery/recovery observable | all required records, no silent/duplicate | pause reminders |
| E AI lift | counterbalanced LLM vs commands | same backend/tasks | нужен ли LLM в primary | practical effort lift + same safety/caps | commands primary/off |
| F Limited pilot | 2 baseline + 4 pilot weeks | exactly 6 eligible chats | есть ли repeat multi-user value | `>=4/6` activation; `>=3/6` WAUC in two weeks incl. W4; 3 retained; guardrails pass | 3/6 or 2 WAUC → iterate; 0–2/6 → stop/reframe |
| G Viability | usage/cost/support workbook | retained chat-period | контролируема ли экономика | caps frozen before pilot | simplify/provider/scope |
| H Payment/GTM | concrete offer | eligible retained/buyer cases | есть ли transactional signal | payment/deposit/paid continuation | reframe offer/buyer |

Публичные шаблоны проведения находятся в [research/session-operations.md](research/session-operations.md). Результат появляется только после decision memo.

## 12. Экономическая логика

```text
problem incident
→ меньше ручного retrieval/update effort
→ больше successful shared actions и repeat use
→ измеримый buyer/user outcome
→ сравнение outcome с AI, delivery, support и infrastructure cost
→ решение о цене/масштабировании
```

### B2C: chat-period

```text
AI_cost_chat = AI_calls_chat × cost_call
Direct_cost_successful_action =
  (AI + message + storage variable cost) / successful shared actions
Fully_loaded_cost_chat = direct cost + attributable support + allocated infra
Net_revenue_chat = gross receipts − payment fees − refunds
Contribution_retained_paying_chat =
  net revenue − variable cost − attributable support
```

### B2B: contract

```text
Initial_net_investment = implementation_cost − upfront_onboarding_revenue
Monthly_operating_contribution = recurring_revenue − service_cost
Payback_months = initial_net_investment / monthly_operating_contribution
```

### Реестр неизвестных

| Variable | Status | Future source |
|---|---|---|
| Calls/tokens/cost per successful task | UNKNOWN | frozen AI lift run |
| Support minutes/chat-week | UNKNOWN | support log |
| Coordinator time delta | UNKNOWN | baseline/pilot diary |
| Retained chat rate | UNKNOWN | mature cohort |
| Price/payment conversion | UNKNOWN | concrete offer ledger |
| Buyer implementation cost | UNKNOWN | design-partner scoping |
| LTV/ROI | N/A | только после paid retained cohorts |

Не пересекать time saving, repeated-question saving и incident-risk saving в одной сумме без доказательства независимости.

## 13. GTM как эксперименты

| Motion | ICP/qualifier | Offer/action | Denominator | Evidence | Stop rule |
|---|---|---|---|---|---|
| B2C coordinator-led | retained coordinator с новым comparable chat | добавить Gosha после observed useful outcome | eligible coordinators receiving ask | invited chat activation + retention | installs без multi-user value |
| B2C paid cohort | retained chat/organizer | frozen Group Pro/cohort-period offer | eligible concrete offers | payment/deposit | declarations only |
| B2B discovery | L&D/course operator с repeated workflow | workflow mapping/concierge write-back | qualified organizations | owner, cost trace, API/procurement | AI-interest без process evidence |
| B2B design pilot | design partner, one platform/workflow | fixed-scope paid pilot | eligible proposals | signed paid scope/payment | custom build без repeatability |

```text
K_retained = invites_per_chat
             × CR_install
             × CR_multi_user_activation
             × CR_retention
```

До платежей считать `acquisition cost per retained activated chat`, а не CAC. LOI, депозит, платёж и paid continuation — разные уровни evidence.

## 14. Roadmap по доказательствам

Problem-driven связь между текущими обходными механиками, функциями, метриками и gates вынесена в [product development strategy](product-development-strategy.md). Roadmap ниже задаёт порядок инвестиций, а не обещание всех функций.

1. **Problem:** провести R-01 и сохранить counterexamples.
2. **Trust/usability:** concept 8 + 5–7 новых Telegram sessions.
3. **AI value:** frozen 300-case evaluation и LLM-vs-commands product comparison.
4. **Operations:** live scheduled reminder delivery, recovery и event completeness.
5. **Limited pilot:** exactly 6 chats, 2 baseline + 4 pilot weeks.
6. **Viability:** cost/action, support load и retained outcome.
7. **GTM:** B2C concrete offers и B2B design-partner discovery.
8. **Scale:** только после retention, contribution и support evidence.

Новые objects, RAG, Mini App и multi-platform architecture не являются текущим roadmap milestone без пройденного предыдущего gate.

## 15. Risk register

| Risk | Trigger | Mitigation | Kill/pivot rule |
|---|---|---|---|
| Закреп/LMS достаточны | negative cases без retrieval/update friction | qualify segment, keep baseline | stop/resegment |
| Coordinator-only use | нет retrieval/WAUC вторым actor | measure chat-level activation | pivot coordinator tool |
| LLM no-lift | same/worse effort, quality or cost | commands baseline/fallback | LLM optional/off |
| False deadline/reminder | confirmed wrong state/delivery | preview, literal fields, recovery, stops | immediate pause |
| Notification noise | remove/mute/complaint | fixed cadence, kill switch | stop cadence |
| Cross-chat/privacy | disclosure/change or consent breach | chat filtering, HMAC, access/data review | immediate stop |
| Telegram dependency | API/policy/permissions block value | adapter/domain separation | integration only after value |
| Seasonal retention | course ending/holidays | comparable windows/cohorts | no PMF claim |
| Support/compliance cost | caps exceeded | simplify scope/onboarding | no scale |
| B2B custom trap | one-off integrations differ | one workflow + repeatability gate | do not productize |

### Risk validation protocol

Наличие mitigation не означает, что риск валидирован. Для каждого риска хранится status, current evidence, future test и decision rule:

| Risk ID | Риск | Current evidence | Validation | Decision |
|---|---|---|---|---|
| `R-P01` | проблема редкая / AS IS достаточен | PLANNED | R-01 incidents + artifact/negative cases + same-task retrieval comparison | resegment/stop |
| `R-U01` | coordinator-only value | PLANNED | actor-B retrieval в usability и multi-user pilot metrics | coordinator-tool pivot |
| `R-AI01` | LLM не даёт lift | rules baseline measured; live quality unknown | frozen LLM-vs-commands + token/cost telemetry | commands primary/off |
| `R-T01` | неверный deadline становится общим | local invariants measured; perceived safety unknown | adversarial eval + usability + pilot audit | immediate path stop |
| `R-O01` | reminder missed/duplicate/stale | worker mock/local only | controlled scheduled delivery + pilot delivery ledger | reminders paused |
| `R-N01` | notification fatigue | PLANNED | delivered→useful-action, mute/remove/complaint denominators | cadence off/change |
| `R-D01` | privacy/cross-chat breach | isolation tests measured; user/legal review absent | red-team, comprehension, access/data review, incident drill | immediate stop |
| `R-E01` | variable/support cost выше value | engineering estimate only | provider usage + invoice + support time per retained chat | simplify/provider/scope |
| `R-G01` | нет buyer/payment | PLANNED | concrete offer ledger, deposit/payment/continuation | change buyer/package |
| `R-B01` | B2B превращается в custom work | desk hypothesis | multiple workflow maps + concierge + paid design partner | no connector productization |

Outcome получает статус `PASS/FAIL` только при валидном protocol run. Broken instrumentation, violated cohort/allocation или неполное окно дают `INVALID/HOLD`, а не подтверждение или опровержение риска.

## 16. JMLC reviewer evidence map

| Reviewer question | Current claim | Evidence | Limitation | Next evidence |
|---|---|---|---|---|
| Какую проблему решает? | qualified problem hypothesis | этот документ | user research absent | R-01 |
| Кто пользователь? | coordinator initiator + participant beneficiary | roles/JTBD | segments unvalidated | distinct-chat sample |
| Почему не поиск/LMS? | switching hypothesis against free AS IS | alternatives table | comparison not observed | incident reconstruction |
| Есть ли MVP? | runnable deadline/material vertical slice | [technical contract](technical-contract.md), tests | not pilot | usability/live delivery |
| Зачем AI? | optional natural-language entry | [evaluation report](evaluation-report.md) | LLM quality/lift unknown | frozen comparison |
| Как управляете ошибками? | backend + human control | technical contract, SECURITY, tests | perceived trust unknown | usability/red-team |
| Какие результаты? | local/synthetic/mock/private smoke only | [evidence register](evidence-register.md) | no user/business outcome | signed decision memos |
| Как считаете impact? | chat metrics + diagnostic outcome + economics formulas | §§10–12 | values unknown | baseline/pilot |
| Как будете расти? | coordinator referral + design partner | §13 | channels untested | concrete offers |
| Как применялись агенты? | product/engineering/audit assistance under owner responsibility | [AI-assisted development](../AI_ASSISTED_DEVELOPMENT.md) | not user evidence | reviewed provenance log |
| Каков личный вклад? | re-scope, product/AI UX contract, metrics/evaluation, acceptance/release | README | early concept was team work | defend exact decisions |

## 17. Claim policy и stop rules

### Можно утверждать

- working MVP реализует deadline и metadata-only material lifecycle;
- backend отделяет probabilistic interpretation от deterministic side effects;
- automated tests и synthetic rules evaluation воспроизводимы;
- controlled private Telegram/provider smoke подтверждает только ограниченную feasibility;
- продуктовые исследования и pilot заранее спроектированы, но не проведены.

### Нельзя утверждать

- что пользователи подтвердили проблему или ценность;
- что live smoke является usability/pilot/adoption;
- что rules metrics являются LLM quality;
- что reminder jobs равны live reliable delivery;
- что retention, impact, buyer, price, WTP, LTV или ROI известны;
- что agent-generated analysis является CustDev;
- что ранняя командная Gosha Box целиком является личной работой Алена.

### Product stop/pivot rules

- AS IS достаточно хорош → stop/resegment;
- retrieval вторым actor не возникает → coordinator tool pivot;
- material не даёт отдельного сигнала → feature off;
- LLM не даёт incremental value → commands primary;
- critical safety/privacy/delivery failure → immediate pause;
- нет retained value → не тестировать scale/paid acquisition;
- B2B без design partner/API-fit/workflow cost → не строить integration.

Любой новый внешний claim сначала получает evidence ID, denominator, limitation и signed decision memo по [research/decision-memo-template.md](research/decision-memo-template.md).
