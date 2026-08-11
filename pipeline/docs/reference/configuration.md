# Configuration

All configuration is env-var driven, resolved once via
`config.Settings.from_env()` and never read directly from `os.environ`
anywhere else in the codebase — if you need a new setting, add it here, not
as a scattered `os.environ.get()` in some adapter.

`Settings.from_env()` also loads a `pipeline/.env` file, if one exists, via
[`python-dotenv`](https://pypi.org/project/python-dotenv/) — copy
`.env.example` to `.env` and uncomment what you want to override. **Real
process env vars always win over `.env`** (`load_dotenv(..., override=False)`
in `config.py`), so `.env` only fills in what isn't already set by your
shell, a container, or a CI secret.

| Env var | Default | Meaning |
|---|---|---|
| `VAULT_PATH` | `../vault` (resolved relative to the `pipeline/` package, i.e. the sibling `vault/` directory at the repo root) | Root of the OKF bundle this pipeline reads and writes. |
| `OLLAMA_HOST` | `http://localhost:11434` | Base URL for the local Ollama API. |
| `OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Model used for every text-based skill except relatedness judgment: extraction, entity disambiguation, type classification, domain classification, quality eval. |
| `OLLAMA_RELATEDNESS_MODEL` | same as `OLLAMA_CHAT_MODEL` | Model used for `RelatednessSkillPort.judge` — deciding which existing concepts a new draft should link to. Configurable separately so it can point at a smaller/cheaper local model, keeping ingest latency in check as the vault (and the number of neighbor candidates judged per draft) grows. |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Model used for `EmbeddingPort.embed` — both indexing and search queries. |
| `OLLAMA_VISION_MODEL` | `llava` | Model used for image captioning during `parse-sources`. Only needed if you're ingesting documents with images. |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | Per-request timeout passed to `httpx` for every Ollama call. |
| `OLLAMA_MAX_PREDICT_TOKENS` | `2048` | Caps `num_predict` on every generate call, so a model stuck repeating can't hang a run indefinitely. |
| `OLLAMA_MAX_RETRIES` | `3` | Retries on connection errors, timeouts, and 5xx responses, with exponential backoff. A 4xx is never retried. See [`OllamaClient._post`](../architecture/ports-and-adapters.md#skill-ports-applicationportsskills). |
| `OLLAMA_RETRY_BACKOFF_SECONDS` | `1.0` | Base backoff; attempt *n* waits `backoff * 2^(n-1)` seconds. |
| `CHROMA_DIR` | `<pipeline>/.data/chroma` | Where the persistent ChromaDB collection lives. |
| `SQLITE_PATH` | `<pipeline>/.data/metadata.db` | SQLite file backing the intake tracker, the metadata repository, and the bundle audit log (three logically separate stores, one physical file — see `adapters/sqlite/schema.sql`). |
| `SCHEMAS_DIR` | `<pipeline>/schemas` | Where `JsonFileSchemaRegistry` looks for `<Type>.schema.json` files. |
| `EVALS_DIR` | `<pipeline>/evals` | Where `JsonFileEvalRubricsRepository` looks for `<domain-id>.json` rubric files. |
| `PARSED_IMAGES_DIR` | `<pipeline>/.data/parsed-images` | Where `DoclingDocumentParser` writes images it extracts from source documents, before captioning. |
| `CHUNK_MAX_CHARS` | `4000` | Passed to `chunk_markdown()` when splitting a parsed source document. |
| `DISAMBIGUATION_CONFIDENCE_THRESHOLD` | `0.75` | `KnowledgeAgent`'s merge-vs-create cutoff — see [Data flow](../architecture/data-flow.md#4-knowledgeagentrunraw-the-judgment-pipeline). |
| `EVAL_THRESHOLD` | `0.7` | `KnowledgeAgent`'s quality-eval pass/fail cutoff (`domain/eval.py::aggregate_scores`). |
| `RELATEDNESS_MIN_SCORE` | `0.5` | Minimum vector-search similarity score a candidate must clear before `RelatednessSkillPort.judge` ever sees it — keeps a sparsely-populated vault from offering weak/unrelated matches for the model to rationalize a link for. |
| `CATEGORY_CONFIDENCE_THRESHOLD` | `0.6` | Minimum confidence `CategoryClassificationSkillPort` must clear before `KnowledgeAgent`/`CategorizeConcepts` assigns a draft to any Category (existing or newly proposed). |
| `SEARCH_POOL_K` | `20` | How many candidates `SearchConcepts`' semantic and lexical legs each pull before stage-1 fusion — independent of the caller's requested result count. See [Data flow → Search](../architecture/data-flow.md#search). |
| `SEARCH_GRAPH_SEED_K` | `5` | How many of stage 1's top fused hits seed stage-2 graph expansion. |
| `SEARCH_GRAPH_MAX_HOPS` | `2` | Maximum hop distance `expand_neighbors` walks from a seed. |
| `SEARCH_GRAPH_DECAY` | `0.5` | Per-hop score multiplier through an ordinary (non-`Category`) link. |
| `SEARCH_GRAPH_CATEGORY_DECAY` | `0.85` | Per-hop score multiplier through a step leaving a `type: Category` concept — higher than `SEARCH_GRAPH_DECAY` since a shared category is a stronger topical signal than an arbitrary body link. |
| `SEARCH_RRF_K` | `60` | Reciprocal rank fusion constant (the standard RRF-literature default). |
| `SEARCH_STRUCTURED_MIN_RESULTS` | `3` | Stage-0 structured prefilter: minimum matches a `--type`/`--since`/`--until` query needs before it's returned directly, skipping the hybrid pipeline. |
| `LOG_LEVEL` | `INFO` | Passed to `logging_config.configure_logging()` — see [Logging](#logging). |
| `MCP_HOST` | `127.0.0.1` | Default bind address for `pipeline mcp-serve` (overridable with `--host`). |
| `MCP_PORT` | `8000` | Default bind port (overridable with `--port`). |
| `MCP_STATELESS` | `true` | Default Streamable HTTP mode (overridable with `--stateless`/`--stateful`). |
| `MCP_AUTH_TOKEN` | unset | When set, every `/mcp` request must carry `Authorization: Bearer <token>`. Unset means no auth — fine bound to `127.0.0.1`, not fine on `0.0.0.0`. See [MCP server → Auth](mcp-server.md#auth). |

`.data/` is git-ignored (see `pipeline/.gitignore`). Most of it is derived,
rebuildable state (the vector index, the intake DB, the metadata index,
extracted images) that `pipeline index` can always regenerate from the vault
— none of it needs committing or backing up separately from the vault
itself. The one exception is the `bundle_log` table in `metadata.db`: it's
the source-of-truth ingest audit trail (create/merge/reject decisions), not
derived from anything in the vault, so `pipeline index` cannot reconstruct
it — back it up separately if that history matters to you. `.env` is
git-ignored too — commit `.env.example` when you add a setting, never `.env`
itself.

## Logging

`logging_config.configure_logging(level)` calls `logging.basicConfig` once
per process, with a timestamped `%(asctime)s %(levelname)-8s %(name)s:
%(message)s` format — called from every entry point (`cli/main.py::_container()`,
the `mcp-serve` command, and `mcp/server.py` at import time) before anything
else runs. Every module gets its logger the normal way
(`logging.getLogger(__name__)`) and logs through it — nothing else should
call `basicConfig` or add handlers.

This is deliberately separate from CLI output: `typer.echo` in `cli/main.py`
is the user-facing *result* of a command; the log is the operational trace of
what the pipeline did while producing that result (skill calls, per-item
failures, retries) — the MCP server relies on it entirely, since it has no
`typer.echo` equivalent. Set `LOG_LEVEL=DEBUG` to see
`KnowledgeAgent`'s per-draft domain/disambiguation/eval decisions.

## Changing a setting

```bash
export OLLAMA_CHAT_MODEL=qwen2.5:14b
export VAULT_PATH=/path/to/another/vault
uv run pipeline ingest
```

or, via `pipeline/.env`:

```bash
cp .env.example .env
echo "OLLAMA_CHAT_MODEL=qwen2.5:14b" >> .env
uv run pipeline ingest
```

Every CLI command and the MCP server both call `Settings.from_env()` fresh at
startup, so env vars (or `.env`) set before invocation are all that's
needed — there's no separate config file format to learn.

## Adding a new setting

1. Add a field to the `Settings` dataclass in `config.py`.
2. Add its `os.environ.get("YOUR_VAR", <default>)` resolution (or
   `_bool_env`/`_int_env`/`_float_env` for non-string types) in
   `Settings.from_env()`.
3. Update the table on this page and add a commented-out line to `.env.example`.

## Why not a `ConfigManager`?

`Settings` stays one flat, frozen dataclass rather than a manager/registry
with named profiles or per-context overrides, on purpose: there is currently
exactly one runtime shape — a single local process (a CLI command or the MCP
server) that resolves its configuration once at startup from the environment
it was launched in. The CLI and the MCP server already get different values
for the same settings just by being launched with different env vars (or a
different `.env`) — that *is* per-context configuration, with no extra
machinery needed. A `ConfigManager` would earn its keep the moment a genuinely
different usage pattern shows up — e.g. one long-running process serving
multiple tenants/vaults with different config *at the same time*, or config
that needs to change without a restart. Until then, building one is
solving a problem this codebase doesn't have yet.
