# Gosha AI — рынок, монетизация и unit economics

> **Цены проверены:** 19 июля 2026 года
> **Статус:** desk research + benchmark assumptions; фактические usage, demand, price, revenue, CAC, LTV и ROI неизвестны
> **Правило:** внешний тариф — факт поставщика, сценарий — допущение, invoice/telemetry/payment — измерение Gosha

## 1. Рыночное решение

Gosha не позиционируется как новый task manager, LMS или «AI, который читает весь чат». Его wedge:

> Превратить конкретную договорённость из сообщения в проверенный общий объект, сохранить источник и вернуть результат в тот же рабочий поток. AI предлагает структуру, backend проверяет ограничения, человек подтверждает смысл.

Главный конкурент — связка `координатор + search/pin + LMS/calendar`, а не другой AI-бот.

## 2. AS IS и альтернативы

| Job | Альтернатива | Сильная сторона | Возможный разрыв | Что ещё проверить |
|---|---|---|---|---|
| найти срок | Telegram search/filter | бесплатно и уже доступно | нужно помнить автора/формулировку, версии могут конфликтовать | время и ошибки на последнем incident |
| сделать заметным | pin/topic | минимум действий | требует дисциплины и ручного обновления | достаточность в negative cases |
| поддерживать общий список | coordinator/digest/table | человек снимает неоднозначность | нагрузка и single point of failure | minutes/interventions |
| не забыть | calendar/task/reminder bot | надёжный личный контур | ручной перенос, нет общего подтверждённого состояния | switching/transfer cost |
| официальный учебный процесс | Moodle/Classroom/другая LMS | роли, задания, сроки, уведомления | чат и LMS могут расходиться | где находится source of truth |
| корпоративный workflow | messenger tasks/bots + tracker | уже оплаченная инфраструктура | verified capture может быть лишь узкой интеграцией | design-partner mapping |

### Официальные продуктовые источники

- Telegram: [search](https://core.telegram.org/api/search), [topics](https://telegram.org/blog/topics-in-groups-collectible-usernames), [Bots FAQ/privacy mode](https://core.telegram.org/bots/faq), [Bot API](https://core.telegram.org/bots/api).
- Reminder/community channel analogues: [Skeddy](https://skeddy.me/), [Combot](https://combot.org/).
- Education: [Moodle LMS](https://moodle.com/solutions/lms/), [Google Classroom](https://edu.google.com/workspace-for-education/products/classroom/).
- Structured task alternatives: [Google Calendar](https://support.google.com/calendar/answer/72143), [Todoist](https://www.todoist.com/project-management), [Trello Automation](https://trello.com/en/butler-automation).
- Corporate context: [Time](https://time-messenger.ru/), [Time education](https://time-messenger.ru/education/), [Time integrations](https://time-messenger.ru/documentation/integrations/).

Функция на официальном сайте не доказывает, что пользователь выбрал её или что Gosha лучше. Такое сравнение становится evidence только после incident reconstruction или controlled task comparison.

## 3. Сегменты и market boundary

### B2C / group SaaS hypothesis

- взрослые учебные группы, интенсивы и проектные команды;
- Telegram — оперативный канал;
- сроки повторяются или меняются;
- внешний source of truth отсутствует либо обновляется непоследовательно;
- coordinator может установить бота;
- value unit — retained active chat.

### B2B / cohort operations hypothesis

- корпоративные академии, bootcamp/L&D и операторы образовательных программ;
- coordinator переносит подтверждённые договорённости между мессенджером и LMS/calendar/tracker;
- Gosha — verified capture/write-back layer;
- value/billing unit проверяется как active cohort, workspace или contract.

## 4. TAM/SAM/SOM

Числовой TAM/SAM/SOM сейчас `N/A`. Число пользователей Telegram не является количеством квалифицированных взрослых учебных чатов, а цена корпоративного мессенджера не является WTP за Gosha.

```text
B2C TAM = qualified adult-learning chats with repeated job × observed annual ARPA_chat
B2C SAM = qualified chats in supported geography/channel/legal scope × observed ARPA_chat
B2C SOM_12m = min(reachable qualified chats, onboarding/support capacity)
                × observed paid conversion × observed annualized ARPA_chat

B2B TAM = organizations with repeated cohort workflow × observed ACV
B2B SAM = organizations on supported platform/region/data regime × observed ACV
B2B SOM_12m = min(qualified named-account pipeline, implementation capacity)
                × observed win rate × observed ACV
```

До транзакций публикуются counts named qualified chats/leads, concrete offers и delivery capacity, но не денежный размер рынка. Первый защищаемый SOM требует named pipeline, offer denominator и paid signal.

## 5. Что код позволяет посчитать сейчас

Факты реализации:

- `GOSHA_OPENAI_MODEL` обязателен для live provider; default model отсутствует;
- используется Responses API, strict JSON schema, `reasoning.effort=none`, `store=false`;
- deterministic commands не вызывают LLM;
- обычный свободный AI-entry выполняет один remote call;
- при provider error service переключается на offline fallback без автоматического remote retry;
- adapter пока не сохраняет `usage`, token split, latency или direct cost.

Следовательно, стоимость единственного `LLM-LIVE-01` — `UNKNOWN`, а расчёт ниже является benchmark, не invoice.

## 6. Token estimate текущего provider payload

Economics Agent Discovery Kit сериализовал фактический payload `provider.py` для 50 синтетических cases репозитория и оценил токены `o200k_base`. Расчёт зафиксирован как `ENGINEERING_ESTIMATE`, а не как воспроизводимое provider usage измерение.

| Показатель | Min | Median | p95 | Max |
|---|---:|---:|---:|---:|
| Full request JSON, tokens | 659 | 707 | 771 | 789 |
| Expected strict output JSON, tokens | 53 | 55 | 64 | 69 |

Это engineering estimate. Авторитетный источник billing — `Response.usage`. Payload обычно ниже порога prompt caching в 1024 tokens, поэтому cached input не входит в base до фактического `cached_tokens` evidence. См. [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

## 7. Стоимость LLM

Standard API rates на дату проверки, USD за 1M tokens: [официальный OpenAI pricing](https://developers.openai.com/api/docs/pricing).

| Model benchmark | Input | Cached input | Output |
|---|---:|---:|---:|
| `gpt-5.4-nano` | $0.20 | $0.02 | $1.25 |
| `gpt-5.4-mini` | $0.75 | $0.075 | $4.50 |
| `gpt-5.4` | $2.50 | $0.25 | $15.00 |

```text
C_call = (T_input × P_input + T_output × P_output) / 1,000,000
```

| Scenario | Tokens/calls assumption | Nano | Mini | GPT-5.4 |
|---|---|---:|---:|---:|
| optimistic technical | 659 input / 53 output / 1 call | $0.000198 | $0.000733 | $0.002443 |
| base benchmark | 707 / 55 / 1 call | $0.000210 | $0.000778 | $0.002593 |
| stress successful action | 789 / 69 / 2 billed attempts | $0.000488 | $0.001805 | $0.006015 |

Stress — user resubmission/clarification assumption, а не скрытый retry текущего adapter. Выбор модели определяется frozen quality/effort/cost gate; нельзя выбрать nano только по цене.

### Обязательное измерение

```text
C_LLM_period = Σ[(input - cached) × P_in
                 + cached × P_cached
                 + output × P_out] / 1,000,000

C_LLM_success = C_LLM_period / successful AI-assisted shared actions
C_LLM_chat = C_LLM_period / active chats
```

Для каждого request нужно сохранить: explicit model/snapshot, prompt/schema versions, input/output/reasoning/cached tokens, latency, result category, fallback, action ID и downstream success. Failed/incomplete billed calls входят в стоимость. Remote calls/attempt и attempts/success считаются отдельно.

## 8. Инфраструктура, хранение и backup

Telegram Bot API не имеет отдельной платы для обычного bot flow; paid broadcast не используется. Cash benchmark ниже показывает порядок затрат и не выбирает hosting vendor.

Официальные ориентиры DigitalOcean на дату проверки:

- Basic VM 1 GiB/1 vCPU/25 GiB — `$6/month`; 2 GiB/1 vCPU/50 GiB — `$12/month`: [Droplets pricing](https://www.digitalocean.com/pricing/droplets).
- Managed PostgreSQL 1 GiB/1 vCPU, 10–30 GiB — от `$15.15/month`, storage `$0.215/GiB/month`: [Managed databases pricing](https://www.digitalocean.com/pricing/managed-databases).
- Weekly Droplet backups benchmark — 20% VM cost; daily — 30%: [DigitalOcean pricing](https://www.digitalocean.com/pricing).

| Stack benchmark | Monthly cash | Что не доказано |
|---|---:|---|
| local/portfolio | $0 external cash | live reliability, backup, operations |
| lean pilot VM | $6 VM + $1.20 weekly backup = **$7.20** | capacity/security/restore fit |
| separated managed DB | $6 VM + $15.15 PostgreSQL = **$21.15** before extras | capacity, support and compliance fit |

```text
Infra_per_chat = (compute + managed DB + backup + monitoring + egress) / active chats
Storage_variable_chat = avg_incremental_GiB_per_chat × rate_GiB
Support_chat = (onboarding + support + incident + privacy/delete minutes)
               / 60 × loaded_hourly_rate
```

Хранение на включённом SSD имеет нулевой дополнительный invoice лишь до исчерпания capacity; это не нулевая экономическая стоимость. Нужно измерять bytes по таблицам/объектам, индексы, audit/outbox growth, retention, backup copies и restore drills. Support нельзя ставить равным нулю до наблюдения: сценарии строятся по p25/median/p95 фактических минут.

## 9. B2C unit economics

```text
AI_chat = useful_actions_chat × AI_share × remote_calls_AI_action × C_call
VC_chat = AI_chat + message + storage + backup + payment_fee + variable_support
Fully_loaded_chat = VC_chat + allocated compute/DB/monitoring/fixed operations
Net_revenue_chat = gross receipts - refunds - provider/payment fees - applicable indirect taxes
Contribution_chat = Net_revenue_chat - VC_paying_chat
CM% = Contribution_chat / Net_revenue_chat
Break_even_paid_chats = Fixed_monthly_cost / Contribution_chat
Cost_successful_action = all direct period cost / successful multi-user actions
```

Break-even считается только при положительном contribution. CAC, LTV и churn не рассчитываются до платного измеряемого канала и зрелых когорт.

## 10. B2B unit economics

```text
Implementation_cost = sales_hours × rate_sales
                    + security_hours × rate
                    + integration_hours × rate_impl
                    + onboarding_hours × rate_impl
Initial_net_investment = Implementation_cost - upfront_fee
Service_cost = cohorts × VC_cohort + support + customer_success
             + partner/platform fees + dedicated infrastructure
Monthly_operating_contribution = recurring_revenue - Service_cost
Payback_months = Initial_net_investment / Monthly_operating_contribution
```

Buyer benefit считается только из verified time/incident saving минус внутренние change/operations costs. Пересекающиеся эффекты не складываются.

## 11. Три сценария после данных

| Scenario | Usage/cost | Demand/retention | Support/integration |
|---|---|---|---|
| pessimistic/stress | p95 tokens/calls | lower observed retained/payment outcome | p95 support, one-off integration |
| base | actual median tokens/calls/actions + invoice | mature observed cohort | median support, measured setup |
| optimistic | observed p25 direct cost | upper observed retained outcome | reusable connector/p25 support |

Для всех сценариев используются одна cohort/window и source column `FACT`/`ASSUMPTION`. Сначала проверяется чувствительность по одной переменной, затем combined stress. Aspirational conversion и выдуманный ARPA не подставляются.

## 12. Монетизация

### B2C offers

| Model | Paid value hypothesis | Risk | Gate |
|---|---|---|---|
| free limited pilot | весь trusted core в лимите | не проверяет оплату | нужен для value evidence |
| cohort-period pass | использование на срок курса/интенсива | сезонность/разовая покупка | concrete continuation offer |
| Group Pro | quotas, extended reminders, history, multiple groups, templates/export | paid features могут быть неважны | retained job + transaction |
| coordinator subscription | снижение ручной нагрузки | buyer платит за value всей группы | buyer evidence |

Preview/confirm, correction/recovery, delete/export и privacy controls не становятся платными trust gates.

Price corridor:

```text
Cost floor = (VC_chat + support + allocated fixed share) / (1 - target CM assumption)
Value ceiling = pre-frozen share × verified buyer benefit
```

Эксперимент: frozen package/price/duration/refund → eligible offer denominator → pre-fixed price ladder → отдельно opinion, LOI, deposit, payment и paid continuation. Для digital goods внутри Telegram применяются актуальные правила [Telegram Stars](https://core.telegram.org/bots/payments-stars); налоги, чеки, комиссии и refunds требуют отдельной legal/payment проверки.

### B2B offers

1. fixed-scope paid design pilot;
2. onboarding/integration fee + recurring per active cohort;
3. annual workspace/platform license после repeatable workflow;
4. on-prem/white-label только после явного data-residency/procurement evidence.

Официальный рыночный anchor, не цена Gosha: Time публикует тариф `20 ₽/user/month` для лицензированных университетов и `350 ₽/user/month` для других организаций: [Time education](https://time-messenger.ru/education/). Это подтверждает альтернативу и procurement context, но не WTP за Gosha.

## 13. Economics gates

| Gate | Продолжаем, если | Pivot/stop |
|---|---|---|
| Product value | есть repeat multi-user outcome | no repeat → no monetization |
| AI lift | LLM улучшает effort при safety/cost caps | commands primary/off |
| B2C payment | payment/deposit/paid continuation | change buyer/package |
| B2B productization | repeatable workflow + paid design partner | no generic connector |
| Scale | observed retention, contribution and support load | no paid acquisition |

Сильный текущий claim: **экономика инструментирована и имеет проверяемую модель**. Нельзя пока утверждать прибыльность, положительный contribution, WTP или размер рынка.
