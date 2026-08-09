# OKF Pipeline

Local-only ingestion, indexing, and MCP-serving tool for the [OKF](../WIKI_SPEC.md)
vault at `../vault`. It turns unprocessed notes and documents dropped into
`vault/raw/` into conformant OKF concepts, indexes them for semantic search,
and serves the result to Claude (or any MCP client) over MCP.

Everything runs locally — [Ollama](https://ollama.com) for LLM inference and
embeddings, [ChromaDB](https://www.trychroma.com/) for vector search, SQLite
for structured metadata, plain markdown for the vault itself. No cloud
service, no external API key, in the loop.

## Quickstart

```bash
uv sync
ollama pull llama3.1:8b nomic-embed-text llava

# put something in the capture inbox, then run it through the pipeline
echo "Cold brew steeps 12-24 hours in cold water, coarser grind than drip." \
  > ../vault/raw/cold-brew.md
uv run pipeline scan
uv run pipeline ingest
uv run pipeline index

uv run pipeline search "cold brew steep time"
```

Serve the vault to Claude over MCP:

```bash
uv run pipeline mcp-serve --port 8000   # stateless Streamable HTTP at /mcp
```

Run the tests and linter:

```bash
uv run pytest -q
uv run ruff check .
```

See [`docs/getting-started.md`](docs/getting-started.md) for the full
walkthrough, including binary source documents (PDF/PPTX/DOCX/XLSX), running
in Docker, and troubleshooting.

## Architecture, in one line

Hexagonal architecture: `domain/` is pure and dependency-free,
`application/` orchestrates against `ports/` (`Protocol` interfaces),
`adapters/` implement those ports against real local technology (Ollama,
ChromaDB, SQLite, Docling, the filesystem), and `cli/main.py`'s `Container`
is the single composition root that wires them together. `mcp/server.py`
reuses that same `Container` to serve the vault over MCP. Full detail in
[`docs/architecture/overview.md`](docs/architecture/overview.md).

## Documentation

The `docs/` directory is a full [MkDocs](https://www.mkdocs.org/) site (with
the [Material](https://squidfunk.github.io/mkdocs-material/) theme):

```bash
pip install mkdocs mkdocs-material
mkdocs serve   # http://127.0.0.1:8000 — live-reloading docs site
```

| Section | Covers |
|---|---|
| [Getting Started](docs/getting-started.md) | Install, models, first end-to-end run, MCP server, troubleshooting |
| [Developer Onboarding](docs/onboarding.md) | Repo map, conventions, "how do I add a...", where the OKF spec fits in |
| [Architecture](docs/architecture/overview.md) | Layer-by-layer design, the full domain model, port↔adapter table, an annotated data-flow trace of `ingest` |
| [Reference](docs/reference/cli.md) | CLI commands, MCP server tools/resources, env-var configuration, every use case's contract, testing conventions |

## Project layout

```
pipeline/
├── src/pipeline/
│   ├── domain/         # pure OKF concept model + deterministic logic
│   ├── application/    # ports (Protocol interfaces) + use cases
│   ├── adapters/       # Ollama, ChromaDB, SQLite, Docling, filesystem
│   ├── mcp/            # MCP server (Streamable HTTP, stateless, health + auth)
│   ├── cli/main.py     # composition root + Typer commands
│   ├── config.py       # env-var settings (+ pipeline/.env support)
│   └── logging_config.py  # the one place logging is configured
├── schemas/            # JSON Schema per concept `type`
├── evals/              # quality-eval rubrics per domain
├── tests/              # mirrors src/pipeline/{domain,application,adapters}
├── docs/               # this MkDocs site
├── .env.example        # every setting, commented out with its default
├── Dockerfile          # runs `pipeline mcp-serve`
└── mkdocs.yml
```

## Production-readiness notes

- **Logging**: `LOG_LEVEL=DEBUG uv run pipeline ingest` shows per-draft
  domain/disambiguation/eval decisions; every entry point configures logging
  once via `logging_config.configure_logging()`.
- **Resilience**: `ingest`/`parse-sources` isolate per-item failures (one bad
  item is marked `error` and retryable via `pipeline retry <id>`, the rest of
  the batch still runs); Ollama calls retry transient failures with backoff.
- **MCP server**: thread-safe under the SDK's worker-thread-pool tool
  execution (see `adapters/sqlite/_thread_local_connection.py`), a `/health`
  readiness endpoint, concept ids validated against path traversal, and
  optional bearer-token auth (`MCP_AUTH_TOKEN`) — see
  [Reference → MCP server](docs/reference/mcp-server.md).
- **CI**: `.github/workflows/ci.yml` runs `ruff check` + `pytest` on every
  push/PR touching `pipeline/`.
