#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m ruff check src tests scripts
"$PYTHON_BIN" -m coverage erase
"$PYTHON_BIN" -m coverage run -m pytest -q
"$PYTHON_BIN" -m coverage report
