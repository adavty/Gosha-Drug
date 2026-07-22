# Gosha AI — research session operations

> Public execution templates only. All examples are `SYNTHETIC EXAMPLE — NOT RESEARCH`.

## 1. Screener and quota tracker

| Candidate code | Role | Segment | Chat cluster | Main/validation | Eligible | Negative quota | Prior exposure | Session status |
|---|---|---|---|---|---|---|---|---|

Contacts and consent records are stored separately outside the repository.

## 2. Problem interview guide

1. Подтвердить возраст 18+, consent scope и возможность остановить session.
2. Попросить восстановить последний deadline/update episode, не показывая Gosha.
3. Где появилась первая версия?
4. Как изменение дошло до группы?
5. Как участник искал актуальную версию?
6. Кто разрешил конфликт?
7. Что координатор повторил, исправил или перенёс?
8. Какое было последствие — включая отсутствие последствия?
9. Почему текущая механика сохранена?
10. Кто может разрешить/запретить бота и почему?

Не спрашивать: «нужен ли бот», «будете ли пользоваться», «сколько готовы платить».

### Incident reconstruction

| Origin | Update path | Retrieval path | Resolution | Manual trace | Consequence | Current alternative | Evidence/limitation |
|---|---|---|---|---|---|---|---|

### Debrief

| Facts/observations | Quotes with permission | Interpretation | Alternative explanation | New/repeated code | Counterexample | Bias note |
|---|---|---|---|---|---|---|

## 3. Concept comprehension

Frozen stimulus:

```text
explicit invocation → AI candidate → backend validation → preview
→ human confirm → current-chat object → recovery
```

Answer key:

- ordinary chat ignored;
- preview is not commit;
- scope is current chat;
- LLM proposes, backend validates, human confirms;
- undo/correct/deactivate exist by role;
- URL contents are not read;
- `/all` and passive reading are unavailable.

| Participant | Invocation | Commit | Chat scope | AI role | Recovery | URL boundary | `/all` boundary | Correct n/N |
|---|---|---|---|---|---|---|---|---|

## 4. Usability task matrix

| Task | Primary | Applicable role | Success state | Critical failure |
|---|---|---|---|---|
| Unambiguous deadline | yes | all | valid preview | wrong date/time |
| Missing time/default | yes | all | visible default in preview | hidden assumption |
| Ambiguous date | yes | all | clarification/no write | false normalization |
| Preview cancel | yes | all | no commit | false success |
| Confirm | yes | all | one commit | duplicate/write bypass |
| Retrieval second actor | yes | all | correct current-chat object | cross-chat/wrong version |
| Undo | yes | author | cancelled state | stale active reminder |
| Correct/deactivate | role-specific | admin/steward | versioned change | unauthorized write |
| Ordinary message/privacy | yes | all | ignored + correct explanation | passive processing |
| LLM outage fallback | yes | all | command completes core | blocked core |
| URL-material | secondary | all | metadata-only lifecycle | content/RAG misconception |

### Outcome rubric

- `SUCCESS`: completed without instructional help and understood result.
- `PARTIAL`: completed after neutral repeat or incomplete understanding.
- `FAIL`: needed interface instruction, wrong state or abandoned.
- `CRITICAL`: unsafe side effect, cross-chat exposure, false write/success or critical privacy misunderstanding.

### Intervention taxonomy

- `I0` none;
- `I1` repeat original task;
- `I2` ask to verbalize expectation;
- `I3` point to interface area;
- `I4` provide command/next action;
- `STOP` stop unsafe path.

`I3/I4/STOP` are not success.

### Per-task log

| Session | Task | Applicable | Start | Valid preview | End | Outcome | Intervention | Actions | Clarifications | Comprehension | Error | Evidence ID |
|---|---|---|---|---|---|---|---|---:|---:|---|---|---|

Second test account is part of the task and not a second respondent.

## 5. Analysis workspace

### Row-level coding

| Code row | Evidence ID | Session | Source type | Fact/observation | Permitted quote | Code | Interpretation | Alternative | Hypothesis | Human review |
|---|---|---|---|---|---|---|---|---|---|---|

AI may suggest candidate codes, but a human reviewer checks every code against source evidence. Agent output is not evidence.

Версии prompt/codebook/schema, exact-quote validation, human review, clustering, saturation и audit trail определены в [analysis pipeline](analysis-pipeline.md). Эта краткая таблица не заменяет pipeline contract.

### Triangulation

| Chat cluster | Coordinator signal | Participant signal | Artifact signal | Agreement/conflict | Resolution/unknown |
|---|---|---|---|---|---|

### Counterexamples and saturation

| Session order | New primary pattern | Variation | Repeated pattern | Negative case | Decision note |
|---:|---|---|---|---|---|

## 6. Pilot collection

### Weekly coordinator diary

| Chat-week | Active deadlines | Manual interventions | Unclear/missed incidents | Coordinator minutes | Evidence note | Missing data |
|---|---:|---:|---:|---:|---|---|

### Operational audit

- scheduled/attempted/delivered/late/retry/permanent/unknown;
- duplicate and silent missed;
- correction/deactivation and recovery SLA;
- mute/remove/complaint with defined denominator;
- event completeness;
- AI/API/support cost per chat-week and successful action.

## 7. Safety stop form

| Incident ID | Time | Build | Scenario | Severity | Side effect | Stop executed | Data affected | Recovery | Owner | Re-entry decision |
|---|---|---|---|---|---|---|---|---|---|---|

Any cross-chat disclosure/change, write without confirm, false success/reminder or uncontrolled mass action pauses the affected path immediately.
