# Gosha AI — research pre-registration

> **Версия:** 1.0
> **Статус:** public protocol; real dates, owners, consent versions and private data locations must be frozen before recruiting

## 1. Change control

До первого observation фиксируются: hypothesis ID, sample, eligibility/exclusion, independent unit, task texts, denominator, threshold, build/provider/protocol versions, analysis rule и allowed decision.

Изменение после observation создаёт новую protocol version и новую cohort label. Старые denominators и thresholds не переписываются.

| Change ID | Date | Before/after observation | Field | Reason | Cohort impact | Decision owner |
|---|---|---|---|---|---|---|
| `CHG-...` | | | | | | |

## 2. R-01 Problem research

| Field | Frozen rule |
|---|---|
| Question | есть ли qualified retrieval/update problem и ручной trace? |
| Independent unit | distinct coordinator chat |
| Sample | 12 coordinators/12 distinct chats; 12 participants; 4 curators |
| Split | coordinator and participant: 6 main + 6 validation |
| Negative quota | минимум 2 coordinator + 2 participant cases |
| Eligibility | 18+, 10+ active chat members, deadline/new update in last 30 days, reconstructable episode |
| Exclusion | team/test user, AI-interest recruitment, duplicate chat as independent case |
| Primary codes | incident, origin, update path, retrieval path, workaround, effort, consequence, source of truth, counterexample |
| Proposed gate | incident `>=8/12`; manual trace `>=6/12`; participant corroboration `>=6/12` |
| Decision | GO to solution research / resegment / stop |

`chat_cluster_key` links paired coordinator/participant evidence. A paired participant triangulates the same case and is not a second independent chat.

## 3. R-02 Concept comprehension

| Field | Frozen rule |
|---|---|
| Sample | 8 adults; coordinator and participant roles; new/recontact shown separately |
| Stimulus | same product flow, privacy boundary, preview/confirm, recovery, metadata-only URL and `/all` boundary |
| Correct | participant explains invocation, chat scope, AI role, confirm and recovery without hint |
| Denominator | eligible completed participants |
| Gate | correct comprehension `>=80%`; raw n/N |
| Stop | critical privacy/scope misunderstanding → revise before usability |

## 4. R-03 Formative usability

| Field | Frozen rule |
|---|---|
| Sample | 5–7 new adults, mobile-first Telegram |
| Unit | assigned applicable task |
| Primary tasks | deadline create, ambiguity, preview/cancel, confirm, second-actor retrieval, recovery, privacy, fallback |
| Secondary | metadata-only material; separate denominator |
| Success | goal state reached without instructional help + correct result comprehension |
| Partial | goal reached with neutral task repeat or incomplete comprehension |
| Fail | instruction/interface hint, wrong state, abandonment |
| Gate | success `>=80%`; comprehension `>=80%`; median clarifications `<=1`; critical errors `0` |
| Decision | GO / revise and new sample / STOP unsafe path |

```text
Task_completion = primary_successes / assigned_applicable_primary_tasks
```

## 5. R-04 LLM vs commands

- within-subject, counterbalanced `AB/BA`;
- same backend, preview, confirm and task families;
- participant and task denominators frozen before run;
- metrics: task success, time to valid preview, actions, clarifications, wrong date/time/URL, result comprehension, p50/p95 latency, tokens, direct cost/successful task and fallback;
- critical errors: `0`.

LLM primary requires no material degradation in success/comprehension, at least one pre-frozen practical effort improvement and passing latency/cost caps. Otherwise commands primary/LLM optional or off.

## 6. R-05 Limited pilot

| Field | Frozen rule |
|---|---|
| Sample | exactly 6 eligible independent chats |
| Window | 2 full baseline + 4 full pilot weeks |
| Core | deadline only; materials off by default |
| Activation | create by actor A + retrieval by actor B in first 72h |
| WAUC | 2 actors + 3 core actions incl. create/change and retrieval in chat-relative week |
| Retention | WAUC again in W4 |
| Diagnostics | manual intervention rate, coordinator minutes, unclear/missed incidents |
| Operations | delivery audit, event completeness, noise, recovery, direct cost |

### Absolute decision rules

**Expand** only if all pass:

- activation `>=4/6`;
- WAUC in at least two weeks including W4 for `>=3/6` chats;
- at least 3 retained chats;
- multi-user W4 inside retained chats;
- critical incidents `0`;
- complete mandatory delivery/recovery/event evidence.

**Iterate:** activation `3/6`, or WAUC/W4 signal in exactly 2 chats, or non-critical operational gate fails.

**Stop/reframe:** activation `0–2/6`, W4 signal `0–1` chat, coordinator-only use in most chats, repeated Iterate cohort or any unresolved critical incident.

Diagnostic outcome does not silently replace these primary rules after results are seen.

## 7. Data/publication boundary

Public repo stores only protocols, synthetic examples, aggregate n/N, redacted permitted quotes and decision memos.

Private only: contacts, consent records, usernames, chat/user IDs, raw notes/messages, recordings, screenshots, exact private-group context and provider request IDs.
