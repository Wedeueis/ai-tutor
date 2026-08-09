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
| `search_wiki` | `(query: str, k: int = 5) -> list[dict]` | `SearchConcepts` use case | Returns `[{"concept_id": ..., "score": ...}, ...]`, most relevant first — same semantics as `pipeline search`. |
| `get_concept` | `(concept_id: str) -> str` | `ConceptRepositoryPort.load` + `frontmatter_codec.render` | Returns the concept's full markdown — YAML frontmatter block plus body — exactly as it's stored in the vault. `concept_id` is the bundle-relative path without `.md` (e.g. `domains/coffee/cold-brew-coffee`). `ConceptId` rejects `..`/absolute/backslash-containing ids (and `MarkdownConceptRepository` re-checks containment after resolving symlinks) — a remote client can't use this to read files outside the vault. |
| `list_concepts` | `(concept_type: str \| None = None) -> list[str]` | `MetadataRepositoryPort.find_ids_by_type` or `ConceptRepositoryPort.list` | Pass a `type` (e.g. `"Domain"`) to filter; omit it to list every concept id in the vault. |
| `list_types` | `(domain: str \| None = None) -> list[str]` | `MetadataRepositoryPort.list_distinct_types` | Every distinct frontmatter `type` in use, optionally scoped to one domain id. |

Each tool's docstring is what the MCP client sees as its description — keep
them in sync with this table if you change one.

## Resources

Static, read-only text resources for the vault's own navigation surfaces:

| URI | Content |
|---|---|
| `okf://moc` | `vault/MOC.md` — the curated, thematic entry point |
| `okf://index` | `vault/index.md` — the mechanical directory listing (OKF §8) |
| `okf://log` | `vault/log.md` — the chronological update history (OKF §9) |

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
