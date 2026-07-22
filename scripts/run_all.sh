#!/usr/bin/env sh
set -eu
PYTHON_BIN="${PYTHON:-python3}"
PYTHON="$PYTHON_BIN" ./scripts/run_quality.sh
"$PYTHON_BIN" scripts/generate_synthetic_benchmark.py --check
"$PYTHON_BIN" -m gosha.cli evaluate data/synthetic-eval.jsonl --output evaluation/controlled-report.json
"$PYTHON_BIN" -m gosha.cli evaluate data/synthetic-challenge.jsonl --output evaluation/challenge-report.json
"$PYTHON_BIN" -m gosha.cli evaluate data/synthetic-benchmark-v1.jsonl --output evaluation/synthetic-benchmark-v1-report.json
"$PYTHON_BIN" scripts/check_readme_links.py
"$PYTHON_BIN" scripts/check_public_export.py --self-test
echo "All checks passed"
