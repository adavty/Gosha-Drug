#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON:-python3}"
WHEEL_SMOKE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/gosha-wheel-smoke.XXXXXX")
cleanup() {
  rm -rf -- "$WHEEL_SMOKE_DIR"
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" -m pip wheel . --no-deps --wheel-dir "$WHEEL_SMOKE_DIR/dist"
"$PYTHON_BIN" -m venv "$WHEEL_SMOKE_DIR/venv"
"$WHEEL_SMOKE_DIR/venv/bin/python" -m pip install --no-deps "$WHEEL_SMOKE_DIR"/dist/*.whl
"$WHEEL_SMOKE_DIR/venv/bin/gosha-runtime-check"
"$WHEEL_SMOKE_DIR/venv/bin/gosha" --help >/dev/null

printf '%s\n' "Wheel clean-install smoke: PASS"
