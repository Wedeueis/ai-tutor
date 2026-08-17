# Getting Started

This walks through everything needed to go from a clean checkout to a
searchable vault and a running MCP server. All commands below assume you're
in the `pipeline/` directory unless noted.

## 1. Prerequisites

| Requirement | Why | Check |
|---|---|---|
| Python 3.12+ | pinned in `.python-version` / `pyproject.toml` | `python3 --version` |
| [`uv`](https://docs.astral.sh/uv/) | dependency management + running the project | `uv --version` |
| [Ollama](https://ollama.com) running locally | every LLM call and every embedding is local | `curl localhost:11434/api/tags` |

Everything else (ChromaDB, SQLite, Docling, the MCP SDK) is installed as a
regular Python dependency — there's nothing else to stand up.

## 2. Install dependencies

```bash
cd pipeline
uv sync
```

This creates `.venv/` and installs everything pinned in `uv.lock`, including
the dev group (`pytest`, `fpdf2`, used only by tests).

## 3. Pull the local models

The pipeline assumes three Ollama models by default (see
[Configuration](reference/configuration.md) to change any of them):

```bash
ollama pull llama3.1:8b       # chat model — extraction, classification, quality eval
ollama pull qwen3-embedding:0.6b  # embedding model — vector search
ollama pull llava             # vision model — image captioning (only used when parsing PDFs/decks with images)
```

Confirm Ollama is reachable before doing anything else:

```bash
curl -s http://localhost:11434/api/tags | head
```

If this fails, every pipeline command that calls a skill (`ingest`,
`parse-sources`) or embeds text (`index`, `search`) will fail too — the CLI
doesn't fall back to anything else.

## 4. Point it at a vault

By default the pipeline looks for a sibling `../vault` directory (i.e.
`llm_wiki_with_okf/vault`, next to `pipeline/`) — that's already the layout of
this repo, so no configuration is needed to use the checked-in vault. To point
at a different vault, set `VAULT_PATH`:

```bash
export VAULT_PATH=/path/to/some/other/vault
```

Or, for anything you'll want to keep set across sessions, copy `.env.example`
to `.env` and uncomment the lines you need — every setting in
[Configuration](reference/configuration.md) can be set there instead of
exporting it every time. `.env` is git-ignored.

## 5. Run the pipeline, end to end

Drop something into the capture inbox — a plain note is the simplest case:

```bash
cat > ../vault/raw/my-first-note.md <<'EOF'
Cold brew coffee steeps for 12-24 hours in cold or room-temperature water,
using a coarser grind than drip coffee to avoid over-extraction. The result
is a concentrate, typically diluted 1:1 with water or milk before drinking.
EOF
```

Then walk it through the pipeline stages, in order:

```bash
uv run pipeline scan            # register new/changed files under vault/raw/
uv run pipeline parse-sources   # (skip for plain .md/.txt notes — this stage is for PDFs/PPTX/DOCX/XLSX/images)
uv run pipeline ingest          # run the KnowledgeAgent: extract, classify, dedupe, eval, create/merge
uv run pipeline index           # (re)build the vector + metadata index from every concept in the vault
```

`ingest` prints what it did:

```
created domains/coffee/cold-brew-coffee  (from raw/<hash>)
```

Now search it:

```bash
uv run pipeline search "how long should cold brew steep" -k 3
```

```
0.812  domains/coffee/cold-brew-coffee
0.391  domains/coffee/ideal-espresso-ratio
...
```

And check overall pipeline status at any point:

```bash
uv run pipeline status
```

See [Reference → CLI](reference/cli.md) for every command and flag, and
[Architecture → Data flow](architecture/data-flow.md) for what actually
happens inside `ingest`.

!!! note "Binary source documents"
    A `.pdf`/`.pptx`/`.docx`/`.xlsx`/image dropped into `vault/raw/` needs the
    extra `parse-sources` step first — it uses Docling to turn the document
    into markdown chunks (captioning any images along the way), which then
    become ordinary intake items that `ingest` consumes exactly like a raw
    note. Plain `.md`/`.txt` notes skip straight from `scan` to `ingest`.

## 6. Serve the vault to Claude over MCP

```bash
uv run pipeline mcp-serve --host 127.0.0.1 --port 8000
```

This starts a stateless Streamable HTTP MCP server at `http://127.0.0.1:8000/mcp`
exposing `search_wiki`, `get_concept`, `list_concepts`, and `list_types` as
tools. See [Reference → MCP server](reference/mcp-server.md) for the full tool
list and how to add it as an MCP server in Claude Code / Claude Desktop.

## 7. Run the test suite

```bash
uv run pytest -q
```

Tests that need a real Ollama instance are marked `@pytest.mark.integration`
and auto-skip if Ollama isn't reachable — see
[Reference → Testing](reference/testing.md).

## 8. Run it in Docker (optional)

```bash
docker build -t okf-pipeline .
docker run --rm -p 8000:8000 \
  -v /path/to/llm_wiki_with_okf/vault:/vault -e VAULT_PATH=/vault \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  okf-pipeline
```

The image runs `pipeline mcp-serve` by default (`MCP_HOST=0.0.0.0` is baked
in so it's reachable from outside the container) and ships a `HEALTHCHECK`
against `/health`. It does **not** bundle the vault or Ollama — mount the
vault and point `OLLAMA_HOST` at wherever Ollama actually runs (the Docker
Desktop `host.docker.internal` alias reaches the host machine from inside
the container; on Linux, use the host's LAN/bridge IP instead, or run
Ollama in the same Docker network). See
[Reference → MCP server → Auth](reference/mcp-server.md#auth) before
exposing this beyond `127.0.0.1` — set `MCP_AUTH_TOKEN`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `OllamaError: ... request failed` | Ollama isn't running, or the model named in `OLLAMA_CHAT_MODEL`/`OLLAMA_EMBED_MODEL`/`OLLAMA_VISION_MODEL` hasn't been pulled. Transient failures (connection errors, timeouts, 5xx) already retry a few times with backoff (`OLLAMA_MAX_RETRIES`) before raising this — if you see it, Ollama was down for the whole retry window, or returned a 4xx that's never retried. |
| `pipeline search` returns nothing | The index is empty or stale — run `pipeline index` to rebuild it from the vault |
| `ingest` creates nothing and logs nothing | `pipeline scan` (and `parse-sources`, for binary documents) hasn't been run first — `ingest` only consumes items already discovered in the intake DB |
| `ingest`/`parse-sources` prints `error ...` for an item | That one item failed unexpectedly and was isolated — the rest of the batch still ran. Fix the underlying cause (check the log output for the exception, `LOG_LEVEL=DEBUG` for more detail) and run `pipeline retry <item-id>` |
| A concept keeps failing `validate` | Check the `type`-specific schema under `pipeline/schemas/` (falls back to `_base.schema.json`) — see [Configuration](reference/configuration.md) |
