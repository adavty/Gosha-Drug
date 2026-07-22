# Gosha AI — public evidence register

> **Обновлено:** 22 июля 2026
> **Назначение:** единая граница между воспроизводимым evidence, private observation и будущим исследованием

## Статусы

- `MEASURED_LOCAL` — воспроизводимый локальный запуск.
- `MEASURED_SYNTHETIC` — измерение на явно синтетическом наборе.
- `DOCUMENTED_PRIOR` — ранее выполненное исследование как основание метода/дизайна, но не validation Gosha.
- `DESK_RESEARCH` — датированный внешний факт из первичного источника и отделённая интерпретация.
- `ENGINEERING_ESTIMATE` — расчёт/benchmark без authoritative provider usage или invoice.
- `MOCK` — тест внешнего контракта на mock runtime.
- `CONTROLLED_LIVE_PRIVATE` — ограниченное внешнее наблюдение; raw evidence не публикуется из-за privacy.
- `PLANNED` — протокол/threshold без результата.
- `RESEARCH_OBSERVATION` — обезличенное исследовательское evidence после QA.
- `MEASURED_USER_RESULT` — агрегированный результат с numerator/denominator и decision memo.
- `DECISION` — продуктовое решение, не пользовательский факт.

## Реестр

| ID | Claim | Status | Source/method | n/denominator | Limitation | Allowed wording | Prohibited inference |
|---|---|---|---|---|---|---|---|
| `THESIS-01` | ВКР дала human-reviewed method и AI UX principles | DOCUMENTED_PRIOR | `docs/thesis-foundation.md`; ВКР | 12 thesis interviews | другой problem/domain; не Gosha sample | «research/design foundation» | Gosha problem validated |
| `MARKET-01` | Telegram/LMS/calendar/task tools и corporate platforms — функциональные substitutes | DESK_RESEARCH | `docs/market-and-business-model.md`, official sources checked 2026-07-19 | source register, not users | feature presence ≠ behavior/demand | «dated alternatives map» | Gosha superior/market demand |
| `ECON-01` | текущий provider payload имеет оценимый token/cost range | ENGINEERING_ESTIMATE | `docs/market-and-business-model.md`; 50 synthetic payloads + published rates | 50 synthetic cases | adapter usage/invoice absent; model unset | «engineering cost benchmark» | actual live cost/profitability |
| `ENG-01` | default suite: 132 passed, 1 PostgreSQL test skipped; PostgreSQL suite: 133 passed | MEASURED_LOCAL | `make quality` + Docker PostgreSQL 16, 2026-07-20 | 132/133 default; 133/133 PostgreSQL | local runs only; no load/failover | «132 passed, 1 skipped by default; 133 passed with PostgreSQL» | production ready |
| `ENG-02` | branch coverage gate and critical lint pass | MEASURED_LOCAL | `make quality`, 2026-07-20 | 85% branch coverage; 86% with PostgreSQL; Ruff E9/F | threshold is a quality floor, not reliability evidence | «85% branch coverage gate; Ruff pass» | full static correctness/security proof |
| `ENG-03` | wheel clean-install, Docker build, migrations `001–003` and container health pass | MEASURED_LOCAL | wheel smoke + Compose/PostgreSQL + `gosha-ai:1.1.1`, 2026-07-20 | 1 clean wheel install; 1 local container smoke | no registry, remote CI or production deployment | «local package/container/PostgreSQL smoke passed» | production deployment validated |
| `ENG-04` | release candidate `1.2.0` passes default/PostgreSQL suites, migrations `001–005`, Docker build and container health | MEASURED_LOCAL | full checks + clean PostgreSQL 16 + Compose + `gosha-ai:1.2.0`, 2026-07-22 | 143/144 default; 144/144 PostgreSQL; 1 local container smoke | local only; no remote CI, load, failover or production deployment | «current local quality, migration and container gates pass» | production ready |
| `LLM-OBS-01` | adapter/evaluator collect token counts, latency and explicit-rate cost | MEASURED_LOCAL | provider/evaluator contract tests, 2026-07-20 | 2 focused tests inside full suite | live key/model absent; no systematic provider report | «usage/cost instrumentation implemented and tested» | actual live LLM cost or quality |
| `EVAL-01` | controlled rules accuracy/F1 1.0/1.0 | MEASURED_SYNTHETIC | `evaluation/controlled-report.json` | 26 | supported grammar set | «contract smoke» | LLM/user quality |
| `EVAL-02` | challenge accuracy 0.4583, macro-F1 0.5467 | MEASURED_SYNTHETIC | `evaluation/challenge-report.json` | 24 | synthetic challenge | «rules baseline brittle» | LLM will be better |
| `EVAL-03` | perturbation benchmark accuracy 0.9333, macro-F1 0.9344; call-all accuracy 1.0; safety accuracy 0.0 | MEASURED_SYNTHETIC | `evaluation/synthetic-benchmark-v1-report.json` | 300 rows from 30 semantic seeds × 10 transforms | correlated transforms; not independent/user cases/canonical gate | «frozen perturbation robustness benchmark; call-all rules slice passes, safety gap exposed» | 300 independent cases or model safety validated |
| `TG-01` | adapter/callback/worker contract works against mock Bot API | MOCK | `tests/test_telegram.py` | test suite | no external Telegram reliability | «mock-tested adapter» | live delivery/pilot |
| `SAFE-01` | actor/chat-bound confirm, isolation, idempotency and recovery invariants tested | MEASURED_LOCAL | tests + technical contract | test cases | current build only | «tested local invariants» | absolute safety |
| `TG-LIVE-01` | deadline/material interaction completed in one private group with two actor-account | CONTROLLED_LIVE_PRIVATE | owner-run controlled smoke | 1 group / 2 accounts | raw screenshots withheld; accounts not independent users | «controlled feasibility smoke» | usability/adoption/pilot |
| `LLM-LIVE-01` | one configured provider request returned compatible structured output | CONTROLLED_LIVE_PRIVATE | owner-run request | 1 | raw request/model details withheld; no usage record | «single compatibility observation» | quality/SLA/cost |
| `PROBLEM-01` | qualified chats experience repeat retrieval/update incidents | PLANNED | R-01 | planned 12 chats | no observations yet | «problem hypothesis» | validated demand |
| `UX-01` | users understand scope/preview/recovery | PLANNED | concept + usability | planned 8 + 5–7 | no sessions yet | «protocol prepared» | usability proven |
| `AI-LIFT-01` | LLM lowers effort against commands | PLANNED | counterbalanced comparison | TBD/frozen before test | no comparison yet | «AI lift hypothesis» | LLM required |
| `PILOT-01` | chats repeat multi-user value | PLANNED | 6-chat limited pilot | 6 chats | baseline/pilot absent | «pilot designed» | retention/impact |
| `PAY-01` | coordinator/buyer accepts paid continuation | PLANNED | concrete offer | TBD | no offer/payment | «monetization hypothesis» | WTP/revenue |

## Private evidence manifest rule

`CONTROLLED_LIVE_PRIVATE` сохраняет только безопасный manifest:

- evidence ID;
- date window без обратимо идентифицируемого контекста;
- build/commit;
- сценарии и pass/fail;
- число test groups/actor accounts;
- ограничения claim;
- owner attestation.

В public repo не попадают tokens, secrets, usernames, chat/user IDs, request IDs, private screenshots, raw messages или обратимо идентифицируемые даты/контексты.

## Update rule

Новый user/business result добавляется только после:

```text
private raw data
→ consent/redaction QA
→ aggregate with raw numerator/denominator
→ decision memo
→ evidence-register update
→ product-discovery/README claim sync
```

До подписанного memo статус остаётся `PLANNED` или `COLLECTED_NOT_SYNTHESIZED`.
