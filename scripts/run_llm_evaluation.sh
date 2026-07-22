#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"
: "${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
: "${GOSHA_OPENAI_MODEL:?GOSHA_OPENAI_MODEL is required}"
: "${GOSHA_LLM_INPUT_USD_PER_MILLION:?Set the dated input-token price}"
: "${GOSHA_LLM_OUTPUT_USD_PER_MILLION:?Set the dated output-token price}"

"$PYTHON_BIN" -m gosha.cli --provider openai evaluate \
  data/synthetic-eval.jsonl \
  --output evaluation/llm-controlled-report.json \
  --input-usd-per-million "$GOSHA_LLM_INPUT_USD_PER_MILLION" \
  --output-usd-per-million "$GOSHA_LLM_OUTPUT_USD_PER_MILLION"

if [ "${GOSHA_RUN_SYNTHETIC_300:-0}" = "1" ]; then
  "$PYTHON_BIN" scripts/generate_synthetic_benchmark.py --check
  "$PYTHON_BIN" -m gosha.cli --provider openai evaluate \
    data/synthetic-benchmark-v1.jsonl \
    --output evaluation/llm-synthetic-benchmark-v1-report.json \
    --input-usd-per-million "$GOSHA_LLM_INPUT_USD_PER_MILLION" \
    --output-usd-per-million "$GOSHA_LLM_OUTPUT_USD_PER_MILLION"
fi

"$PYTHON_BIN" -m gosha.cli --provider openai evaluate \
  data/synthetic-challenge.jsonl \
  --output evaluation/llm-challenge-report.json \
  --input-usd-per-million "$GOSHA_LLM_INPUT_USD_PER_MILLION" \
  --output-usd-per-million "$GOSHA_LLM_OUTPUT_USD_PER_MILLION"

printf '%s\n' "LLM evaluation completed for explicit model: $GOSHA_OPENAI_MODEL"
