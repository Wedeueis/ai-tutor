# CLI Reference

Entry point: `pipeline` (installed via `[project.scripts]` in
`pyproject.toml`, pointing at `pipeline.cli.main:app`). Run it via
`uv run pipeline <command>` or, inside an activated `.venv`, just
`pipeline <command>`. All commands read configuration from
`Settings.from_env()` — see [Configuration](configuration.md).

Every command builds a fresh `Container` (`cli/main.py::_container()`) — the
composition root that wires every concrete adapter to the use case it drives.

## `scan`

```bash
pipeline scan
```

Discovers new or changed files under `vault/raw/` and registers them in the
intake tracker (`ScanIntake`). Prints one line per newly discovered item:

```
discovered a1b2c3d4e5f6  raw_note  /path/to/vault/raw/my-note.md
```

Unchanged files (same content hash as already tracked) are silently skipped.
Run this before `parse-sources` or `ingest` — they only act on items already
discovered.

## `status`

```bash
pipeline status
```

Shows intake item counts grouped by `(state, kind)`, then lists every item
currently in `rejected` or `error` state with its path and error message —
the quickest way to see what needs attention.

## `retry <item-id>`

```bash
pipeline retry a1b2c3d4e5f6
```

Resets one intake item back to `discovered` (clearing any `error_message`),
so it re-enters the next `ingest`/`parse-sources` run. Use after fixing
whatever caused an `error` state (e.g. Ollama was down, a malformed file).

## `parse-sources`

```bash
pipeline parse-sources
```

Runs `scan` first, then `ParseSourceDocuments`: turns every discovered
`SOURCE_DOCUMENT` (PDF/PPTX/DOCX/XLSX/image) into markdown, captions any
extracted images, and splits the result into chunks — each becoming its own
intake item ready for `ingest`. Prints:

```
parsed a1b2c3d4e5f6  -> 4 chunk(s)
```

No-op (with a message) if there are no source documents to parse. A document
that fails unexpectedly (a Docling error, an unreachable captioning model)
doesn't stop the rest of the batch — it's marked `error` and reported
separately, retryable via `pipeline retry <item-id>` (above) once fixed:

```
error parsing 9f8e7d6c5b4a  — <exception message>
```

## `ingest`

```bash
pipeline ingest
```

Runs `scan` first, then `IngestRawMaterial`: drives every unprocessed raw
note or chunk through the `KnowledgeAgent`, applies its create/merge
decisions to the vault, indexes whatever changed, and appends to `log.md`.
Prints one line per outcome:

```
created domains/coffee/cold-brew-coffee  (from raw/a1b2c3d4)
merged into domains/coffee/espresso-basics  (from raw/f00dbeef)
rejected raw/deadbeef01  — quality eval below threshold
```

Like `parse-sources`, an item that fails unexpectedly (Ollama unreachable, an
unparsable skill response) doesn't abort the batch — it's isolated, marked
`error`, and every other item still gets processed:

```
error raw/c0ffee01  — Ollama request to /api/generate failed after 4 attempt(s): ...
```

Set `LOG_LEVEL=DEBUG` (see [Configuration](configuration.md)) to see each
draft's domain classification, disambiguation confidence, and eval score as
`ingest` runs. See [Architecture → Data flow](../architecture/data-flow.md)
for exactly what happens inside this command.

## `validate <path>`

```bash
pipeline validate domains/coffee/cold-brew-coffee.md
pipeline validate domains/coffee/cold-brew-coffee   # .md suffix optional
```

Runs `ValidateConcept`: structural conformance (OKF §11) plus JSON Schema
validation against `pipeline/schemas/<Type>.schema.json` (or
`_base.schema.json` if no type-specific schema is registered). Exits `1` and
prints each issue if invalid:

```
domains/coffee/cold-brew-coffee: NOT conformant
  [status] unrecognized status 'archived' (expected draft|stable|deprecated, §5.4)
```

## `index`

```bash
pipeline index
```

Runs `RebuildIndex`: walks **every** concept in the vault and re-indexes it
(embeds + upserts into both the vector store and the metadata store). Use
after bulk manual edits to the vault, or to recover from a stale/corrupted
ChromaDB or SQLite metadata store — both are fully derivable from the vault's
markdown files. Prints the count:

```
indexed 12 concept(s)
```

## `new-domain <slug> --title ... --description ...`

```bash
pipeline new-domain observability \
  --title "Observability" \
  --description "Logging, metrics, and tracing practices."
```

Scaffolds a new `type: Domain` concept at `domains/<slug>.md`, appends a
creation entry to `log.md`, and creates a placeholder eval-rubric file at
`pipeline/evals/domains/<slug>.json` (a single `"placeholder"` rubric you're
expected to replace with real, domain-specific quality criteria — see
[Onboarding → Add or change a domain's quality bar](../onboarding.md#add-or-change-a-domains-quality-bar)).
Fails with exit code `1` if the domain already exists. Doesn't link the new
domain from `MOC.md` — that's a manual, curatorial step by design.

## `search <query> [-k N]`

```bash
pipeline search "how long should cold brew steep" -k 3
```

Runs `SearchConcepts`: embeds the query and returns the `k` closest concepts
(default `5`) by cosine similarity, most relevant first:

```
0.812  domains/coffee/cold-brew-coffee
0.391  domains/coffee/ideal-espresso-ratio
0.203  domains/coffee/pourover-guide
```

## `mcp-serve [--host] [--port] [--stateless/--stateful]`

```bash
pipeline mcp-serve --host 127.0.0.1 --port 8000
```

Starts the MCP server (`pipeline.mcp.server`) over Streamable HTTP, plus a
`GET /health` readiness endpoint. See
[Reference → MCP server](mcp-server.md) for the tools/resources it exposes,
the health check, and optional auth.

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `$MCP_HOST` (`127.0.0.1`) | Bind address |
| `--port` | `$MCP_PORT` (`8000`) | Bind port |
| `--stateless` / `--stateful` | `$MCP_STATELESS` (stateless) | Whether the Streamable HTTP transport keeps no session state between requests (recommended for multi-replica deployments) or maintains a session per client |

Every flag falls back to its `Settings` value (see
[Configuration](configuration.md)) when omitted, so a deployment can be fully
configured via env vars / `.env` with no CLI flags at all. Auth
(`MCP_AUTH_TOKEN`) has no CLI flag — it's secret-shaped, so it's env-var-only
by design.
