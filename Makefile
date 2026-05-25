# fh-racer — top-level orchestration.
# Sub-app Makefiles still work; this just composes them.
# `make help` lists targets.

SHELL := /bin/bash

.PHONY: help \
        dev dev.backend dev.web \
        test test.backend test.backend.cov test.web test.web.cov cov \
        lint lint.backend lint.web \
        typecheck typecheck.backend typecheck.web \
        build build.web \
        ci codegen codegen.check \
        e2e e2e.install \
        db.up db.down db.migrate db.shell db.test.setup db.test.drop \
        install install.backend install.web \
        pre-commit.install pre-commit.run

# ---- composite targets ----

dev: ## Run backend + web dev servers in parallel
	$(MAKE) -j2 dev.backend dev.web

test: ## Run backend pytest + web vitest
	$(MAKE) -j2 test.backend test.web

lint: ## Run all linters
	$(MAKE) -j2 lint.backend lint.web

typecheck: ## Run all type checkers
	$(MAKE) typecheck.backend typecheck.web

build: build.web ## Build production artefacts

cov: ## Run backend + web tests with coverage gates (80% / 70%)
	$(MAKE) test.backend.cov
	$(MAKE) test.web.cov

ci: lint typecheck cov build ## Local equivalent of CI (gated coverage)

# ---- backend ----

dev.backend:
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; uv run python -m fh6.main

test.backend:
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; uv run pytest

test.backend.cov: ## pytest with coverage gate (--cov-fail-under=80)
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; \
		uv run pytest --cov --cov-report=term --cov-fail-under=80

lint.backend:
	cd apps/backend && uv run ruff check src tests
	cd apps/backend && uv run ruff format --check src tests

typecheck.backend:
	cd apps/backend && uv run mypy src/fh6

install.backend:
	cd apps/backend && uv sync

# ---- web ----

dev.web:
	pnpm --filter fh6-racer-client dev

test.web:
	pnpm --filter fh6-racer-client test:run

test.web.cov: ## vitest with coverage gate (70%) — currently red until web tests are backfilled
	pnpm --filter fh6-racer-client exec vitest run --coverage

lint.web:
	pnpm --filter fh6-racer-client lint

build.web:
	pnpm --filter fh6-racer-client build

typecheck.web:
	pnpm --filter fh6-racer-client typecheck

install.web:
	pnpm install

install: install.backend install.web ## Install all deps

# ---- infra ----

db.up: ## Start postgres + redis via compose
	docker compose -f infra/compose/docker-compose.yml up -d postgres redis

db.down:
	docker compose -f infra/compose/docker-compose.yml down

db.migrate:
	cd apps/backend && uv run alembic -c src/fh6/infrastructure/db/migrations/alembic.ini upgrade head

db.shell:
	docker compose -f infra/compose/docker-compose.yml exec postgres psql -U fh6 fh6

db.test.setup: ## One-time: create fh6_test DB + install timescaledb extension (needs postgres superuser)
	sudo -u postgres psql -c "CREATE DATABASE fh6_test OWNER fh6;" || true
	sudo -u postgres psql -d fh6_test -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
	$(MAKE) db.test.migrate

db.test.migrate: ## alembic upgrade head against fh6_test (idempotent)
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; \
		FH6_DB_DSN="$${FH6_TEST_DB_DSN:-$${FH6_DB_DSN%/fh6}/fh6_test}" \
		uv run alembic -c src/fh6/infrastructure/db/migrations/alembic.ini upgrade head

db.test.drop: ## Drop the fh6_test database (needs postgres superuser)
	sudo -u postgres psql -c "DROP DATABASE IF EXISTS fh6_test;"

# ---- pre-commit ----

pre-commit.install: ## Install pre-commit git hook (opt-in)
	uv run --project apps/backend pre-commit install

pre-commit.run: ## Run all pre-commit hooks against all files
	uv run --project apps/backend pre-commit run --all-files

# ---- contract codegen (Phase 3) ----
#
# `codegen` regenerates the two JSON artefacts that pin the contract
# (packages/contract/openapi.json + packages/contract/ws.schema.json)
# and then rebuilds the TS package on top of them. `codegen.check`
# regenerates the JSON artefacts into a tmp dir and `diff`s against the
# committed copies — the source of truth is the backend Pydantic + route
# definitions, and CI fails on drift.

CONTRACT_DIR := packages/contract

codegen: ## Regenerate packages/contract from the live backend
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; \
		uv run python -m fh6.tools.openapi_dump > ../../$(CONTRACT_DIR)/openapi.json
	cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; \
		uv run python -m fh6.tools.ws_schema_dump > ../../$(CONTRACT_DIR)/ws.schema.json
	pnpm --filter @fh-racer/contract build

codegen.check: ## Fail if regenerated artefacts differ from committed copies
	@tmp=$$(mktemp -d) && trap "rm -rf $$tmp" EXIT && \
		cd apps/backend && set -a && [ -f .env ] && . ./.env; set +a; \
		uv run python -m fh6.tools.openapi_dump > $$tmp/openapi.json && \
		uv run python -m fh6.tools.ws_schema_dump > $$tmp/ws.schema.json && \
		cd ../.. && \
		diff -u $(CONTRACT_DIR)/openapi.json $$tmp/openapi.json && \
		diff -u $(CONTRACT_DIR)/ws.schema.json $$tmp/ws.schema.json && \
		echo "codegen.check: OK"

# ---- e2e (Phase 12, optional) ----
#
# Playwright drives Chromium against `make dev` (backend + vite). A
# helper script pumps synthetic Forza UDP packets at 30 Hz so the
# live-frame smoke can observe the dashboard reach DRIVING. One-time
# setup: `make e2e.install` to download the Chromium binary + apt deps.

e2e: ## Run Playwright e2e smokes (needs `make e2e.install` once)
	pnpm --filter fh6-racer-client exec playwright test \
		--config=../e2e/playwright.config.ts

e2e.install: ## One-time: download Chromium + apt deps (~150 MB, needs sudo)
	pnpm --filter fh6-racer-client exec playwright install --with-deps chromium

# ---- help ----

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_.]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help
