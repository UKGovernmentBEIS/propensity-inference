.PHONY: check check-all check-ci test test-all test-ci typecheck lint fix lint-fix format format-check install tag tag-patch tag-minor tag-major

check-fix: check fix
check: typecheck lint format-check test
check-all: typecheck lint format-check test-all
check-ci: typecheck lint format-check test-ci
fix: format lint-fix
install:
	uv sync

test:
	uv run pytest . -n auto --durations 10 -m "not slow and not manual and not skip_ci"

test-all:
	uv run pytest . -n auto --durations 10 -m "not manual"

# In practice -n auto seems to mean 1 worker on CI. But more workers didn't
# seem faster when I (Ben, 2025-12-18) tried it.
test-ci:
	uv run pytest . -n auto --durations 10 -m "not skip_ci and not slow and not manual"

typecheck:
	uv run pyright .

lint:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

format:
	uv run ruff format

format-check:
	uv run ruff format --check

# Release tagging targets
tag: tag-patch

tag-patch:
	uv run scripts/tag_release.py patch

tag-minor:
	uv run scripts/tag_release.py minor

tag-major:
	uv run scripts/tag_release.py major

