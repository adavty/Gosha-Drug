# Offline evaluation report

Версия provider: `offline-rules-v1`. Данные полностью синтетические; реальные пользовательские фразы не использованы.

| Набор | Назначение | n | Intent accuracy | Macro-F1 | Slot value accuracy | Required-slots case exact match |
|---|---|---:|---:|---:|---:|---:|
| `synthetic-eval.jsonl` | controlled deadline/material/oos contract smoke | 26 | 1.000 | 1.000 | 1.000 | 1.000 |
| `synthetic-challenge.jsonl` | отдельно сформулированные paraphrase/noise/oos примеры | 24 | 0.4583 | 0.5467 | 0.5000 | 0.5000 |
| `synthetic-benchmark-v1.jsonl` | frozen perturbation robustness benchmark | 300 | 0.9333 | 0.9344 | 0.9290 | 0.9455 |

Controlled score ожидаемо высокий, потому что набор проверяет поддерживаемую грамматику fallback. Challenge score показывает, что rules baseline недостаточен для свободного естественного языка: главные ошибки — неявные create/list/correct/deactivate формулировки. Это и есть проверяемая роль LLM-provider; его систематическое качество в текущей версии **не измерено**.

Benchmark построен генератором из 30 semantic seeds и 10 детерминированных surface transforms на seed: base, обращение, вежливые префикс/суффикс, регистр, пробелы и другие поверхностные вариации. Поэтому `n=300` — число строк, но не число независимых смысловых кейсов. Все transforms дали одинаковую accuracy `0.9333`, что ожидаемо при коррелированной конструкции. Ошибки: 10 create-фраз классифицированы как question и 10 safety/injection-фраз — как `correct_deadline`; отдельный safety slice имеет accuracy `0.0`. Это полезный отрицательный результат и причина не использовать rules baseline как доказательство безопасного natural-language понимания.

JSON-отчёты evaluator версии `1.4.0` фиксируют SHA-256 набора и версию Python, Wilson 95% interval для accuracy, confusion matrix, per-class precision/recall/F1, deadline/material/oos и benchmark slice accuracy, perturbation metrics и error taxonomy. Slot value accuracy — доля совпавших значений размеченных gold-полей. Required-slots case exact match — доля кейсов, где совпали все размеченные обязательные поля; это не slot micro-F1 и метрика не штрафует лишние неразмеченные поля. Интервалы описывают неопределённость только соответствующего синтетического набора, а не генеральную совокупность.

Ни один из наборов не является каноническим frozen Alpha set на 300 независимых кейсов. Эти результаты не доказывают Bronze readiness, продуктовую ценность или качество на реальном Telegram-трафике. Следующий эксперимент: заранее разметить независимый 300-case set, сравнить rules baseline и LLM по intent/slots/date normalization, затем отдельно пройти deterministic integration/red-team suite с нулевым допуском к critical failures.

## Live LLM evaluation contract

`scripts/run_llm_evaluation.sh` запускает тот же evaluator через OpenAI-compatible structured-output adapter. Model ID и датированные input/output rates передаются явно. Отчёт фиксирует provider/model, SHA-256 набора, evaluator/Python version, intent/slot metrics, errors, суммарные token counts, latency и рассчитанную стоимость.

```bash
OPENAI_API_KEY='...' \
GOSHA_OPENAI_MODEL='<explicit-model-id>' \
GOSHA_LLM_INPUT_USD_PER_MILLION='<dated-rate>' \
GOSHA_LLM_OUTPUT_USD_PER_MILLION='<dated-rate>' \
./scripts/run_llm_evaluation.sh
```

По умолчанию script запускает controlled и challenge sets, чтобы не создавать неожиданную стоимость. Для дополнительного прогона 300-row perturbation benchmark нужно явно задать `GOSHA_RUN_SYNTHETIC_300=1`; этот прогон всё равно не заменяет независимый frozen set.

API key и тексты запросов в JSON-отчёт не записываются. Отсутствие `evaluation/llm-*.json` означает `NOT_RUN`, а не нулевую стоимость или успешную валидацию.
