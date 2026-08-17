# MCP Server

`src/pipeline/mcp/server.py` exposes the vault to any [Model Context
Protocol](https://modelcontextprotocol.io) client — Claude Code, Claude
Desktop, or anything else that speaks MCP — over **Streamable HTTP**, running
**stateless** by default.

It builds one `Container` (the same composition root `cli/main.py` uses) at
module load and calls straight through to it from each tool — so the MCP
server and the CLI are always backed by the same vault, vector index, and
local models. See
[Architecture → Ports & adapters](../architecture/ports-and-adapters.md#mcp-server-reuses-the-same-wiring).

## Running it

```bash
uv run pipeline mcp-serve --host 127.0.0.1 --port 8000
```

or directly:

```bash
uv run python -m pipeline.cli.main mcp-serve
```

This serves the MCP endpoint at `http://<host>:<port>/mcp`.

## Why stateless

The server is built with `MCPServer("okf-wiki", ...)` from the `mcp` SDK
(`mcp>=2.0.0` — note `FastMCP` was renamed to `MCPServer` in that release).
Rather than call the SDK's `mcp.run(...)` directly, `server.py` builds the
underlying Starlette app itself (`mcp.streamable_http_app(stateless_http=...)`)
so it can layer the health check and optional auth middleware below on top,
then serves it with `uvicorn.run(...)`:

```python
app = mcp.streamable_http_app(stateless_http=stateless, host=host)
# + optional auth middleware, see below
uvicorn.run(app, host=host, port=port)
```

`stateless_http=True` (the default) means every request is handled
independently — no session store, no long-lived SSE stream pinned to one
worker process. That lets the server run behind an ordinary load balancer
with multiple replicas instead of needing sticky sessions, which is the
deployment shape the MCP spec's Streamable HTTP transport recommends for
stateless services. Pass `--stateful` to `pipeline mcp-serve` if you need
session affinity instead (e.g. for a single long-lived local client
connection).

**A concurrency consequence of this SDK, worth knowing before you add a
tool:** the `mcp` SDK runs synchronous tool functions on an `anyio`
worker-thread pool — a different thread per call, not necessarily the thread
that built `_container`. Every adapter `Container` wires up has to tolerate
being called from a thread other than the one that constructed it. The
SQLite adapters handle this via `ThreadLocalSqliteConnection` (one
connection per thread, opened lazily — see
`adapters/sqlite/_thread_local_connection.py`); ChromaDB's client and
`httpx`'s module-level functions (used by the Ollama adapter) are safe
across threads without any special handling. If you add a tool that touches
new shared state, make sure that state is thread-safe too.

## Tools

| Tool | Signature | Backed by | Notes |
|---|---|---|---|
| `search_wiki` | `(query: str, k: int = 5, concept_type: str \| None = None, since: str \| None = None, until: str \| None = None) -> list[dict]` | `SearchConcepts` use case | Hybrid search: vector + lexical (FTS5) results fused via reciprocal rank fusion, then expanded/reranked through the link graph. Pass `concept_type` (optionally with `since`/`until`, ISO dates) to try a deterministic structured match first. Returns `[{"concept_id": ..., "score": ...}, ...]`, most relevant first — same semantics as `pipeline search`. `score` is a fused rank-based number (or `1.0` for a structural match), not a raw 0–1 cosine similarity (see [Architecture → Data flow](../architecture/data-flow.md#search)). |
| `get_concept` | `(concept_id: str) -> str` | `ConceptRepositoryPort.load` + `frontmatter_codec.render` | Returns the concept's full markdown — YAML frontmatter block plus body — exactly as it's stored in the vault. `concept_id` is the bundle-relative path without `.md` (e.g. `domains/coffee/cold-brew-coffee`). `ConceptId` rejects `..`/absolute/backslash-containing ids (and `MarkdownConceptRepository` re-checks containment after resolving symlinks) — a remote client can't use this to read files outside the vault. |
| `list_concepts` | `(concept_type: str \| None = None) -> list[str]` | `MetadataRepositoryPort.find_ids_by_type` or `ConceptRepositoryPort.list` | Pass a `type` (e.g. `"Domain"`) to filter; omit it to list every concept id in the vault. |
| `list_types` | `(domain: str \| None = None) -> list[str]` | `MetadataRepositoryPort.list_distinct_types` | Every distinct frontmatter `type` in use, optionally scoped to one domain id. |
| `related_concepts` | `(concept_id: str) -> dict` | `MetadataRepositoryPort.find_links` | Returns `{"outgoing": [...], "incoming": [...]}` — the cluster of related concepts around one concept, independent of `tags`. Same semantics as `pipeline links`. Category links (`## Categories`) are ordinary §6 links, so a concept's Category shows up here too, alongside its other related concepts. |
| `find_relations` | `(concept_id: str, relation_type: str \| None = None) -> dict` | `MetadataRepositoryPort.find_relations` | Typed relations for one concept — a Dataview-style `relation_type:: [[target]]` line, distinct from `related_concepts`' plain untyped links. Optionally filter to one `relation_type` (e.g. `"supersedes"`). |
| `trace_lineage` | `(concept_id: str, relation_type: str \| None = None, direction: str = "both", max_hops: int = 3) -> list[list[dict]]` | `TraceLineage` use case | Every typed-relation path up to `max_hops` away — the full chain, not just reachability (e.g. decision → superseded_by → decision). Same semantics as `pipeline lineage`. |
| `get_source` | `(concept_id: str) -> list[dict]` | `ConceptRepositoryPort` (resolves `frontmatter.sources[].resource`) | Resolves a concept's §5.1 `sources[]` straight to the referenced `vault/references/` document's full content — grounding an answer in the original source without a manual second `get_concept` call. |
| `recall_passage` | `(concept_id: str, source_id: str \| None = None, context: int = 1, limit: int = 3) -> list[dict]` | `RecallPassages` use case over `PassageReaderPort` | The **original text** a concept was distilled from, in its surrounding context — for checking a concept against its source, or showing how the author actually put it. `source_id` is one of the concept's `sources[].id` values (the same string a `[^footnote]` marker in its body carries), so you can ask for the passage behind one specific claim; omit it for the first few passages that fed the concept. `context` (0–3) adds neighbouring passages of the same document either side, truncated inside-out to `PASSAGE_CONTEXT_CHARS`. Adjacency is by ordinal, so a gap left by a dropped garbled chunk is **not** bridged. Distinct from `get_source`, which returns whole `references/` documents: passages are source material, not concepts — they have no page in the vault and never appear in search results. Backed by the intake store today, so recall returns nothing after `pipeline clear --reset-intake`. |
| `find_entity` | `(name: str, entity_type: str \| None = None) -> list[dict]` | `SearchConcepts` (structured-prefiltered) | Thin convenience over `search_wiki` scoped to `entity_type` (e.g. `"Person"`), for "who is X" style lookups. |

Each tool's docstring is what the MCP client sees as its description — keep
them in sync with this table if you change one. `find_relations`/`trace_lineage`/`get_source`/`recall_passage`/`find_entity`
are, like every tool above, read-only.

## Resources

Static, read-only text resources for the vault's own navigation surfaces:

| URI | Content |
|---|---|
| `okf://moc` | `vault/Home.md` — the curated, thematic entry point |
| `okf://index` | `vault/index.md` — the mechanical directory listing (OKF §8) |
| `okf://log` | The pipeline's SQLite ingest audit trail (create/merge/reject decisions), newest first — not `vault/log.md`; this bundle doesn't populate the OKF §9 file, see [CLAUDE.md → The vault](../../CLAUDE.md) |

## Health check

`GET /health` — a plain, unauthenticated readiness probe (not part of the
MCP protocol itself; registered via the SDK's `@mcp.custom_route`, which
exists for exactly this — see its docstring). Checks that the vault
directory exists and that Ollama answers `/api/tags`:

```bash
curl http://127.0.0.1:8000/health
```

```json
{"status": "ok", "checks": {"vault": "ok", "ollama": "ok"}}
```

Returns HTTP `200` when every check passes, `503` with `"status": "degraded"`
otherwise — point a load balancer's or orchestrator's readiness probe at it.

## Auth

Unauthenticated by default — fine when bound to `127.0.0.1`. Set
`MCP_AUTH_TOKEN` (see [Configuration](configuration.md)) to require
`Authorization: Bearer <token>` on every `/mcp` request (`/health` stays
public, since health checks generally can't carry a secret and the endpoint
reveals nothing sensitive). `mcp-serve` logs a warning at startup if it's
bound to a non-localhost address with no token set.

```bash
export MCP_AUTH_TOKEN=$(openssl rand -hex 32)
uv run pipeline mcp-serve --host 0.0.0.0
```

This is a single shared static token, not the `mcp` SDK's OAuth
(`AuthSettings`/`TokenVerifier`) support — that models a full OAuth resource
server (issuer URL, protected-resource metadata, token introspection), which
is disproportionate for "one secret, checked on every request." If this
server ever needs per-user identity or scoped tokens, that's the trigger to
move to the SDK's OAuth support (`_BearerAuthMiddleware` in `server.py` is
intentionally minimal and easy to replace wholesale, not extend piecemeal).

## Connecting a client

Point any Streamable-HTTP-capable MCP client at
`http://<host>:<port>/mcp` (adding the `Authorization` header above if
`MCP_AUTH_TOKEN` is set). For Claude Code, add it as a project or user MCP
server pointing at that URL (consult Claude Code's own MCP server
configuration docs for the exact config file shape, since that's part of the
Claude Code product, not this codebase).

## Extending it

Add a new tool with `@mcp.tool()` on a plain function in `server.py` — the
`mcp` SDK derives the tool's input schema from the function's type hints and
its description from the docstring. Reach for `_container.<use_case>` or
`_container.<repository>` rather than constructing new adapters — if the
capability you need isn't already on `Container`, add it there first (see
[Onboarding → Add a new use case](../onboarding.md#add-a-new-use-case)) so the
CLI and MCP server stay backed by identical wiring. Add a new static resource
with `@mcp.resource("okf://...")`; avoid template resources
(`okf://{param}`) for anything under a concept id that contains `/`, since
the SDK's default resource-path security is meant for single path segments,
not bundle-relative concept ids — a plain tool (like `get_concept`) is the
better fit for that shape.
