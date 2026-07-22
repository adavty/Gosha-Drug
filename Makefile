.PHONY: help install test quality audit evaluate check wheel-smoke build debug live logs down

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:
	@printf '%s\n' \
	  'make install   Install development dependencies' \
	  'make test      Run the test suite' \
	  'make quality   Run lint and branch coverage gate' \
	  'make audit     Scan installed dependencies for known vulnerabilities' \
	  'make evaluate  Run synthetic rules evaluations' \
	  'make check     Run tests, evaluations and README link checks' \
	  'make wheel-smoke  Build and install the wheel in a clean environment' \
	  'make build     Build the Docker image' \
	  'make debug     Start the local debug web profile' \
	  'make live      Start PostgreSQL and the Telegram bot (requires .env)' \
	  'make logs      Follow Telegram bot logs' \
	  'make down      Stop Compose services without deleting volumes'

install:
	$(PYTHON) -m pip install -e '.[dev,postgres]'

test:
	$(PYTHON) -m pytest -q

quality:
	PYTHON=$(PYTHON) ./scripts/run_quality.sh

audit:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip_audit --local --skip-editable

evaluate:
	$(PYTHON) -m gosha.cli evaluate data/synthetic-eval.jsonl --output evaluation/controlled-report.json
	$(PYTHON) -m gosha.cli evaluate data/synthetic-challenge.jsonl --output evaluation/challenge-report.json
	$(PYTHON) -m gosha.cli evaluate data/synthetic-benchmark-v1.jsonl --output evaluation/synthetic-benchmark-v1-report.json

check:
	PYTHON=$(PYTHON) ./scripts/run_all.sh

wheel-smoke:
	PYTHON=$(PYTHON) ./scripts/check_wheel_install.sh

build:
	docker build -t gosha-ai:1.2.0 .

debug:
	docker compose --profile debug up --build debug-web

live:
	docker compose --profile live up --build -d bot

logs:
	docker compose --profile live logs -f bot

down:
	docker compose --profile live --profile debug down
