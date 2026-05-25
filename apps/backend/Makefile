.PHONY: dev test migrate replay lint typecheck

dev:
	uv run python -m fh6.main

test:
	uv run pytest

migrate:
	uv run alembic -c src/fh6/infrastructure/db/migrations/alembic.ini upgrade head

replay:
	uv run python -m fh6.tools.replay_capture $(CAPTURE)

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy src/fh6
