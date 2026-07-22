# AI-assisted development

Gosha AI подготовлен Аленом Давтяном как самостоятельное развитие ранней командной концепции Gosha Box. При работе над JMLC-версией использовались AI-агенты в ролях продуктового исследователя, архитектора, разработчика, редактора конкурсной заявки и независимых аудиторов.

Ален задал цель, ограничения limited-pilot scope и критерии качества; принимал продуктовые решения; сверял результат с опытом, дипломом, программой AI Product и требованиями JMLC; запускал воспроизводимые проверки и отвечает за все утверждения заявки. Агентные материалы не считаются пользовательским исследованием, измеренным продуктовым эффектом или внешней экспертизой жюри.

Граница доказательств:

- код и документация проверяются автоматическими тестами и воспроизводимыми командами;
- evaluation использует только явно маркированные синтетические данные;
- ранняя концепция пяти авторов не выдаётся за индивидуальную реализацию;
- реальные пользователи, LLM-качество и pilot outcomes не симулируются.

## Product discovery agent audit, 18 июля 2026

Текущий публичный discovery-контур был независимо проверен тремя ролями Discovery Kit:

| Роль агента | Проверяемый контур | Ключевой результат |
|---|---|---|
| AI Product Manager | JTBD, scope, hypotheses, metrics, stage gates | выявлен разрыв между глубокой технической частью и кратким product narrative |
| Product/UX Research Synthesizer | research reproducibility, denominators, privacy, decision loop | добавлены public pre-registration и execution templates без PII |
| Discovery Economics Analyst | viability, economics, GTM и JMLC evidence | добавлены unknowns, cost formulas, channel experiments и reviewer evidence map |

Primary AI-agent сопоставил findings с README, техническим контрактом, tests и evaluation reports; принятые предложения перенесены в `docs/product-discovery.md`, `docs/evidence-register.md` и `docs/research/`.

Это **agent-assisted рабочая сборка**. Персональное owner review Алена перед внешним использованием новых формулировок должно быть зафиксировано отдельно. До owner review нельзя утверждать, что Ален лично подтвердил каждое добавленное решение.

Agent output не считается research evidence. Реальный claim может измениться только после пользовательского/технического evidence, human review и decision memo.

## Discovery Kit gap-closure, 19 июля 2026

Три профильных агента Discovery Kit независимо закрывали разные контуры:

| Роль | Вклад |
|---|---|
| AI Product Manager | problem → AS IS → solution → metric → gate, B2C/B2B и problem-driven roadmap |
| Product Research Synthesizer + AI UX | перенос human-in-the-loop метода ВКР в protocol Gosha, codebook/prompt/schema, negative cases и audit trail |
| Discovery Economics Analyst | token/cost benchmark provider payload, infrastructure benchmarks, B2C/B2B models, pricing experiments и TAM/SAM/SOM boundary |

Агенты не создавали респондентов и не генерировали результаты интервью. Их output остаётся analysis/design work; статус validation появляется только после реальных сессий, human QA и decision memo. Owner review Алена остаётся обязательным перед внешней подачей.
