.PHONY: help install lint lint-fix typecheck test test-integration test-all coverage check-boundary

help:
	@echo "Setup:"
	@echo "  install          uv sync (install/update dependencies)"
	@echo ""
	@echo "Lint:"
	@echo "  lint             ruff check ."
	@echo "  lint-fix         ruff check . --fix"
	@echo "  typecheck        mypy src/tutor"
	@echo "  check-boundary   fail if anything in tutor/ imports pipeline"
	@echo ""
	@echo "Tests:"
	@echo "  test             fast tests only (default) -- no live Ollama, no MCP server"
	@echo "  test-integration slow tests only -- needs Ollama and pipeline's MCP server"
	@echo "  test-all         the full suite (fast + integration)"
	@echo "  coverage         fast tests with a coverage report (NFR7's 85% bar)"

install:
	uv sync

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

typecheck:
	uv run mypy src/tutor

# PRD v3 §2 rule 1: tutor reaches pipeline solely over MCP. This is the one
# architectural rule a stray import can break silently, so it is checkable
# rather than only documented.
check-boundary:
	@! grep -rnE '^\s*(from|import)\s+pipeline\b' src tests \
		|| (echo "tutor must not import pipeline -- it reaches the vault over MCP only (PRD v3 §2)"; exit 1)
	@echo "boundary ok: nothing imports pipeline"

test:
	uv run pytest -q -m "not integration"

test-integration:
	uv run pytest -q -m integration

test-all:
	uv run pytest -q

# NFR7 asks for >= 85% on domain and application, reported per-file rather than
# gated on the total — the adapter and CLI modules in the same tree would drag
# any meaningful bar for those two layers down.
coverage:
	uv run pytest -q -m "not integration" --cov --cov-report=term-missing
