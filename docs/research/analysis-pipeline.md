# Gosha AI — воспроизводимый LLM-assisted pipeline качественного исследования

> **Статус:** protocol ready, results absent
> **Методическая основа:** human-in-the-loop pipeline ВКР; codebook создан заново для Gosha

## 1. Корпус и разделение выборки

Для R-01:

- 12 координаторов из 12 независимых чатов: `6 main + 6 validation`;
- 12 обычных участников: `6 main + 6 validation`;
- 4 куратора/организатора — отдельный exploratory buyer corpus;
- минимум 4 заранее набранных negative cases;
- participant из того же чата используется для triangulation, а не как второй независимый problem case;
- только совершеннолетние участники.

Allocation table фиксируется до анализа и стратифицируется по роли, типу программы и negative-case status. Main corpus используется для открытого кодирования и первой типологии. Validation corpus проверяет устойчивость, вариации, контрпримеры и насыщение.

## 2. Consent, provenance и privacy

Согласия разделяются:

1. участие и исследовательские заметки;
2. запись/транскрипция;
3. использование редактированного артефакта;
4. публикация обезличенной дословной цитаты;
5. отдельный opt-in на включение обезличенной фразы в evaluation set.

Для каждой сессии создаётся pseudonymous `participant_id`; связь с `chat_cluster_key` хранится отдельно. Отказ от evaluation opt-in не аннулирует другие согласия.

## 3. Подготовка транскрипта

1. Зафиксировать `study_id`, protocol version, participant ID, роль, сегмент, date window, moderator и consent scopes.
2. Создать verbatim transcript с turn IDs `M001`, `P001`; не угадывать inaudible fragments.
3. Проверить транскрипт по записи человеком.
4. До LLM заменить имена, usernames, ссылки, организации, группы, преподавателей и иные identifiers токенами `[PERSON_1]`, `[GROUP_1]`, `[URL_1]`.
5. Сохранить redaction log только в restricted contour.
6. Рассчитать `transcript_hash` для canonical redacted text.

LLM получает только redacted transcript и минимальную metadata. Raw transcript автоматически не отправляется.

## 4. Codebook Gosha v1

| Category | Определение |
|---|---|
| `recent_incident` | конкретный retrieval/update incident в заданном окне |
| `object_type` | дедлайн, изменение срока, URL-материал |
| `origin` | где появилась первая версия |
| `update_path` | как изменение дошло до группы |
| `retrieval_path` | как участник искал актуальную версию |
| `manual_workaround` | pins, search, переспрос, calendar, table, Saved Messages, LMS |
| `coordinator_effort` | действия/время в конкретном эпизоде |
| `consequence` | пропуск, задержка, стресс или отсутствие последствий |
| `source_of_truth` | что считается актуальной версией |
| `responsibility` | кто фактически поддерживает актуальность |
| `trust_signal` | автор, источник, подтверждение, provenance |
| `notification_noise` | mute, игнорирование, жалобы |
| `lms_adequacy` | положительный или отрицательный кейс LMS |
| `bot_permission` | кто может разрешить установку |
| `privacy_concern` | возражение к чтению, хранению или provider |
| `payment_signal` | существующий бюджет, покупка, deposit/procurement |
| `counterexample` | проблемы нет или substitute достаточен |
| `ai_control_expectation` | где требуется preview/confirm/correction/fallback |
| `ux_fragmentation` | копирование контекста, смена инструмента, ручной возврат |

Codebook имеет version, inclusion/exclusion rules, positive/negative examples и change log. Код не равен теме.

## 5. Prompt contract

### System prompt

```text
Ты выполняешь только первичное структурированное кодирование обезличенного транскрипта исследования Gosha AI. Ты не являешься автономным исследователем и не принимаешь продуктовые решения.

1. Кодируй только evidence из реплик участника Pxxx; не кодируй предположения модератора.
2. quote_exact копируй дословно из указанных реплик. Не исправляй стиль и не склеивай фрагменты скрыто.
3. Не выводи скрытые мотивы, диагнозы, демографию, market prevalence, willingness to pay или причинный эффект.
4. Используй только переданный codebook. Непокрытый релевантный фрагмент верни в uncoded_relevant_fragments.
5. Counterexamples кодируй с той же полнотой, что поддерживающие сигналы.
6. Каждый код обязан иметь turn_ids и точную evidence link.
7. Не вычисляй частоты, насыщение, кластеры или темы.
8. При отсутствии evidence верни пустой codes.
9. Ответ — только JSON по schema_version.
```

### Input envelope

```json
{
  "schema_version": "gosha-coding-1.0",
  "prompt_version": "coding-prompt-1.0",
  "codebook_version": "gosha-codebook-1.0",
  "study_id": "R-01",
  "interview_id": "P-000",
  "role": "coordinator",
  "transcript_hash": "sha256:...",
  "transcript_redacted": "M001: ...\nP001: ..."
}
```

### Output schema

```json
{
  "schema_version": "gosha-coding-1.0",
  "interview_id": "P-000",
  "codes": [
    {
      "candidate_code_id": "CAND-001",
      "category": "recent_incident",
      "code_label": "переспрос после изменения срока",
      "evidence_type": "self_report",
      "turn_ids": ["P014", "P015"],
      "quote_exact": "...",
      "context_summary": "Буквальный контекст без нового факта",
      "analytic_memo": "Осторожная интерпретация",
      "hypothesis_ids": ["H-P01"],
      "counterexample": false,
      "uncertainty": "low"
    }
  ],
  "uncoded_relevant_fragments": [],
  "warnings": []
}
```

Allowed `evidence_type`: `observed_behavior`, `artifact`, `self_report`, `direct_quote`, `counterexample`. `uncertainty`: `low`, `medium`, `high`. Validator проверяет, что `quote_exact` присутствует в redacted transcript. Model-generated counts запрещены.

## 6. Reproducibility record

Для каждого LLM-run фиксируются:

- `coding_run_id`, UTC timestamp;
- hashes и versions transcript/prompt/codebook/schema;
- provider и точный model ID, доступные параметры;
- raw response hash, parse/validation status, retry count;
- latency, input/output tokens и direct cost;
- schema violations;
- human reviewer key и final artifact version.

Secrets, API keys, raw provider payload с PII и private request IDs не коммитятся.

## 7. Human verification

Каждый candidate code получает решение `accepted`, `edited` или `rejected` и поля:

| Поле | Содержание |
|---|---|
| `quote_verified` | yes/no после проверки контекста |
| `category_final` | итоговая категория |
| `code_label_final` | итоговая формулировка |
| `evidence_type_final` | итоговый evidence type |
| `reason` | duplicate, unsupported inference, wrong category, quote mismatch, PII, other |
| `reviewer_key` | роль/псевдоним проверяющего |
| `reviewed_at` | timestamp |

Исследователь открывает контекст каждой цитаты и проверяет speaker, точность, смысл, альтернативное объяснение и redaction. Bulk acceptance без просмотра запрещён. Если ресурс доступен, второй исследователь проверяет минимум 20% кодов или интервью; disagreements публикуются вместе со способом разрешения. Agreement — диагностика, а не замена смыслового review.

## 8. Clustering, themes и negative cases

1. В clustering входят только `accepted/edited` коды main group.
2. LLM может предложить grouping, но каждый cluster содержит final code IDs.
3. `n_interviews` считается детерминированно по distinct IDs.
4. Исследователь фиксирует merge/split rationale, alternative grouping и rejected merges.
5. Одиночный сигнал остаётся `single signal`, а не темой.
6. Validation group проверяет темы: `confirmed`, `partially confirmed`, `not confirmed`.
7. Negative-case table обязательна: substitute, почему достаточен, условия отсутствия боли и ограничиваемый claim.
8. Новый theme из validation допускается минимум по двум независимым источникам, если он не сводится к существующему и меняет product interpretation.

## 9. Saturation

После каждой сессии обновляется таблица:

| Order | Interview | Role | Group | New codes | New clusters | Changed theme | Counterexample | Memo |
|---:|---|---|---|---:|---:|---|---|---|

Насыщение оценивается отдельно по ролям. Три последовательных интервью без нового основного паттерна — directional signal и не позволяет задним числом уменьшить quota. Тема получает saturation `yes`, только если validation group подтверждает её без существенного изменения; `partial` — при новых условиях; `no` — если она не повторилась или изменилась принципиально.

## 10. Findings и evidence bank

Каждый finding содержит status, segment/situation, observation, evidence IDs, `X/N` независимых источников, main/validation split, counterexamples, interpretation, product implication, limitations и hypothesis IDs.

Минимальная evidence card:

```yaml
evidence_id: E-000
status: research_observation | measured_result | counterexample
study: R-01
protocol_version: 1.0
source_type: interview | artifact | usability | telemetry | external
participant_or_chat_key: P-000 | CHAT-000 | AGGREGATE
role_segment: coordinator
observed_at_window: YYYY-MM
quote_public: null
observation: "Минимальное обезличенное описание"
measure:
  numerator: null
  denominator: null
  window: null
hypothesis_ids: [H-P01]
alternative_explanations: []
consent_scope: aggregate_only | redacted_quote_allowed
raw_reference: restricted://...
limitations: []
owner_role: Research Lead
```

## 11. Audit trail

```text
consent scope
→ restricted raw recording/transcript
→ human-verified transcript
→ redacted transcript + hash
→ LLM candidate codes + run record
→ human-reviewed final codes
→ clusters/themes + rationale
→ validation/saturation/negative cases
→ evidence cards/findings
→ decision memo
→ public claim update
```

Любое изменение создаёт новую version с parent hash, actor role, timestamp, reason и affected findings/claims.

## 12. Claim update rule

До подписанного decision memo карточка остаётся `PLANNED` или `COLLECTED_NOT_SYNTHESIZED`.

- Interview поддерживает qualitative pattern только в исследованном сегменте.
- Usability поддерживает task performance/comprehension только для данного build/sample.
- Comparative test поддерживает разницу entry flows в данном task set.
- Pilot поддерживает chat-level behavior в шести pilot chats.
- Ни один уровень автоматически не равен market prevalence, causal effect at scale или PMF.

Synthetic data, agent output, ВКР, mock и controlled smoke не включаются в числители Gosha problem validation.
