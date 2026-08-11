.PHONY: help install lint lint-fix test test-integration test-all \
	scan parse ingest index audit prune log pipeline mcp-serve

help:
	@echo "Setup:"
	@echo "  install          uv sync (install/update dependencies)"
	@echo ""
	@echo "Lint:"
	@echo "  lint             ruff check ."
	@echo "  lint-fix         ruff check . --fix"
	@echo ""
	@echo "Tests:"
	@echo "  test             fast tests only (default) -- no live Ollama, no Docling model loads"
	@echo "  test-integration slow tests only -- needs Ollama running locally; loads Docling's ML models"
	@echo "  test-all         the full suite (fast + integration)"
	@echo ""
	@echo "Pipeline commands (each a thin wrapper over 'uv run pipeline <cmd>'):"
	@echo "  scan             discover new/changed files in vault/raw/"
	@echo "  parse            parse binary source documents into ingestible chunks"
	@echo "  ingest           run KnowledgeAgent over everything unprocessed"
	@echo "  index            rebuild the vector + metadata index from the vault"
	@echo "  audit            flag concepts that don't stand alone as useful"
	@echo "  prune            delete stale intake rows"
	@echo "  log              show the ingest audit trail"
	@echo "  pipeline         full run: scan -> parse -> ingest -> index"
	@echo "  mcp-serve        serve the vault over MCP"

install:
	uv sync

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

# Excludes the `integration` marker (see tests/conftest.py): tests that need
# a real local Ollama or that load Docling's ML models on first use, both of
# which dominate the suite's runtime. This is what you want in the normal
# edit/test loop.
test:
	uv run pytest -q -m "not integration"

# Only the slow ones -- run before pushing, or when touching an Ollama
# adapter/prompt or the Docling parser specifically.
test-integration:
	uv run pytest -q -m integration

test-all:
	uv run pytest -q

scan:
	uv run pipeline scan

parse:
	uv run pipeline parse-sources

ingest:
	uv run pipeline ingest

index:
	uv run pipeline index

audit:
	uv run pipeline audit

prune:
	uv run pipeline prune

log:
	uv run pipeline log

pipeline: scan parse ingest index

mcp-serve:
	uv run pipeline mcp-serve
