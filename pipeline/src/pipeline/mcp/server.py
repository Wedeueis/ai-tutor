"""MCP server exposing the OKF vault as tools an MCP client (e.g. Claude) can
call directly, reusing the same ports/adapters the CLI is built on.

Runs over Streamable HTTP in stateless mode (`stateless_http=True`): every
request is handled independently, with no session store and no long-lived SSE
stream pinned to one worker process. That lets this server run behind an
ordinary load balancer with several replicas instead of needing sticky
sessions — the shape the MCP spec's Streamable HTTP transport recommends for
stateless deployments.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pipeline.adapters.filesystem import frontmatter_codec, frontmatter_mapping
from pipeline.cli.main import Container
from pipeline.config import Settings
from pipeline.domain.concept import ConceptId
from pipeline.logging_config import configure_logging

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "okf-wiki",
    instructions=(
        "Search and read concepts from this Open Knowledge Format (OKF) vault. "
        "Concept ids are bundle-relative paths without the `.md` suffix "
        "(e.g. `domains/observability/logging`). Use search_wiki to find "
        "relevant concepts, then get_concept to read one in full."
    ),
)

_settings = Settings.from_env()
configure_logging(_settings.log_level)

# Built once per process and reused across requests — the underlying adapters
# (ChromaDB, SQLite, the markdown repository) are safe to share, and rebuilding
# the container per call would reopen those stores on every tool invocation.
# Note: sync tool functions below run on an anyio worker-thread pool, not the
# thread that built this Container — every adapter it wires up must tolerate
# being called from a different thread than the one that constructed it (the
# SQLite adapters do this via ThreadLocalSqliteConnection; see
# adapters/sqlite/_thread_local_connection.py).
_container = Container(_settings)

_BLANK_OPTIONAL_VALUES = {"", "null", "none"}


def _none_if_blank(value: str | None) -> str | None:
    """Tool-calling models don't reliably omit optional string args —
    observed in practice sending "" or the literal "null" rather than
    leaving a parameter unset — so treat those the same as not-provided."""
    if value is None or value.strip().lower() in _BLANK_OPTIONAL_VALUES:
        return None
    return value


@mcp.tool()
def search_wiki(
    query: str,
    k: int = 5,
    concept_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Hybrid search over the vault's concepts: vector + lexical (FTS5)
    results fused via reciprocal rank fusion, then expanded/reranked through
    the link graph. Returns the closest matches, most relevant first — `score`
    is a fused rank-based number, not a raw 0-1 cosine similarity. Pass
    concept_type (optionally with since/until, ISO dates) to try a
    deterministic structured match first — e.g. "which Decision concepts
    were made in May" — falling back to the hybrid pipeline if it comes up
    short."""
    concept_type = _none_if_blank(concept_type)
    since = _none_if_blank(since)
    until = _none_if_blank(until)
    logger.info("mcp: search_wiki(query=%r, k=%d, concept_type=%r)", query, k, concept_type)
    matches = _container.search_concepts.run(
        query,
        k=k,
        type=concept_type,
        since=date.fromisoformat(since) if since else None,
        until=date.fromisoformat(until) if until else None,
    )
    return [{"concept_id": str(match.concept_id), "score": match.score} for match in matches]


@mcp.tool()
def get_concept(concept_id: str) -> str:
    """Fetch one concept's full content — YAML frontmatter plus markdown body
    — by its id (the bundle-relative path without `.md`, e.g. `references/rfc-9110`)."""
    logger.info("mcp: get_concept(concept_id=%r)", concept_id)
    concept = _container.concept_repository.load(ConceptId(concept_id))
    data = frontmatter_mapping.to_yaml(concept.frontmatter)
    return frontmatter_codec.render(data, concept.body)


@mcp.tool()
def list_concepts(concept_type: str | None = None) -> list[str]:
    """List concept ids in the vault. Pass concept_type (e.g. "Domain") to
    filter by frontmatter `type`; omit it to list every concept."""
    logger.info("mcp: list_concepts(concept_type=%r)", concept_type)
    if concept_type is not None:
        return _container.metadata_repository.find_ids_by_type(concept_type)
    return [str(concept_id) for concept_id in _container.concept_repository.list()]


@mcp.tool()
def list_types(domain: str | None = None) -> list[str]:
    """List the distinct frontmatter `type` values in use, optionally scoped
    to one domain id (as recorded in a concept's `domain` frontmatter field)."""
    logger.info("mcp: list_types(domain=%r)", domain)
    return _container.metadata_repository.list_distinct_types(domain=domain)


@mcp.tool()
def related_concepts(concept_id: str) -> dict:
    """Outgoing and incoming §6 links for one concept — the cluster of
    related concepts around it, independent of tags. Concept ids are
    bundle-relative paths without the `.md` suffix. Category links (`##
    Categories`) are ordinary §6 links, so a concept's Category shows up
    here too, alongside its other related concepts."""
    logger.info("mcp: related_concepts(concept_id=%r)", concept_id)
    graph = _container.metadata_repository.find_links(concept_id)
    return {"outgoing": graph.outgoing, "incoming": graph.incoming}


@mcp.tool()
def find_relations(concept_id: str, relation_type: str | None = None) -> dict:
    """Typed relations for one concept (e.g. `supersedes`) — a Dataview-style
    `relation_type:: [[target]]` line in the body, distinct from plain,
    untyped §6 links. Optionally filter to one relation_type."""
    relation_type = _none_if_blank(relation_type)
    logger.info("mcp: find_relations(concept_id=%r, relation_type=%r)", concept_id, relation_type)
    links = _container.metadata_repository.find_relations(concept_id, relation_type)
    return {
        "outgoing": [
            {"to": link.to_id, "relation_type": link.relation_type}
            for link in links
            if link.from_id == concept_id
        ],
        "incoming": [
            {"from": link.from_id, "relation_type": link.relation_type}
            for link in links
            if link.from_id != concept_id
        ],
    }


@mcp.tool()
def trace_lineage(
    concept_id: str,
    relation_type: str | None = None,
    direction: str = "both",
    max_hops: int = 3,
) -> list[list[dict]]:
    """Every typed-relation path up to max_hops away from a concept (e.g. to
    answer "was this decision superseded?" by walking `supersedes`/
    `superseded_by` edges) — the full chain, not just reachability.
    direction is one of "outgoing", "incoming", or "both"."""
    relation_type = _none_if_blank(relation_type)
    logger.info(
        "mcp: trace_lineage(concept_id=%r, relation_type=%r, direction=%r, max_hops=%d)",
        concept_id,
        relation_type,
        direction,
        max_hops,
    )
    paths = _container.trace_lineage.run(
        concept_id, relation_type=relation_type, direction=direction, max_hops=max_hops
    )
    return [
        [{"from": link.from_id, "to": link.to_id, "relation_type": link.relation_type} for link in path]
        for path in paths
    ]


@mcp.tool()
def get_source(concept_id: str) -> list[dict]:
    """Resolves one concept's §5.1 `sources[]` straight to the referenced
    `vault/references/` document's full content — grounding an answer in
    the original meeting/email/document a concept was derived from, without
    a manual second get_concept round trip."""
    logger.info("mcp: get_source(concept_id=%r)", concept_id)
    concept = _container.concept_repository.load(ConceptId(concept_id))
    results = []
    for source in concept.frontmatter.sources:
        resource = source.resource
        if not resource.startswith("/") or not resource.endswith(".md"):
            continue
        source_id = resource[1:-len(".md")]
        if not _container.concept_repository.exists(ConceptId(source_id)):
            continue
        source_concept = _container.concept_repository.load(ConceptId(source_id))
        data = frontmatter_mapping.to_yaml(source_concept.frontmatter)
        results.append(
            {"resource": resource, "content": frontmatter_codec.render(data, source_concept.body)}
        )
    return results


@mcp.tool()
def find_entity(name: str, entity_type: str | None = None) -> list[dict]:
    """Look up a concept by name — a thin convenience over search_wiki
    scoped to entity_type (e.g. "Person", "Client"), for "who is X" style
    questions."""
    entity_type = _none_if_blank(entity_type)
    logger.info("mcp: find_entity(name=%r, entity_type=%r)", name, entity_type)
    matches = _container.search_concepts.run(name, k=5, type=entity_type)
    return [{"concept_id": str(match.concept_id), "score": match.score} for match in matches]


def _vault_file(relative_path: str) -> str:
    path = _container.settings.vault_path / relative_path
    return path.read_text(encoding="utf-8")


@mcp.resource("okf://moc", name="MOC", description="Curated, thematic entry point into the vault.")
def moc() -> str:
    return _vault_file("Home.md")


@mcp.resource(
    "okf://index",
    name="index",
    description="Mechanical directory listing of the vault root (OKF §8).",
)
def index() -> str:
    return _vault_file("index.md")


@mcp.resource(
    "okf://log",
    name="log",
    description="Pipeline ingest audit trail (create/merge/reject decisions), newest first.",
)
def log() -> str:
    entries = _container.bundle_log.list_entries()
    if not entries:
        return "No log entries yet."
    lines = []
    for entry in entries:
        concept = f" concept={entry.concept_id}" if entry.concept_id else ""
        raw = f" raw={entry.raw_id[:12]}" if entry.raw_id else ""
        lines.append(f"{entry.at.isoformat()}  {entry.action}{concept}{raw}  {entry.message}")
    return "\n".join(lines)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    """Readiness probe for load balancers/orchestrators — not part of the MCP
    protocol itself (see `custom_route`'s docstring: routes registered this
    way are public and unauthenticated by design, same as any health check)."""
    checks: dict[str, str] = {}

    checks["vault"] = "ok" if _container.settings.vault_path.is_dir() else "missing"

    try:
        response = httpx.get(f"{_container.settings.ollama_host}/api/tags", timeout=2.0)
        checks["ollama"] = "ok" if response.status_code == 200 else f"http {response.status_code}"
    except httpx.HTTPError as exc:
        checks["ollama"] = f"unreachable: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if healthy else "degraded", "checks": checks}, status_code=200 if healthy else 503)


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    """Optional static-bearer-token gate for the MCP endpoint, enabled only
    when `MCP_AUTH_TOKEN` is set. This is deliberately not the `mcp` SDK's
    OAuth `AuthSettings`/`TokenVerifier` machinery — that models a full OAuth
    resource server (issuer URL, resource metadata, token introspection),
    which is disproportionate for "one shared secret, checked on every
    request" — the right fit for a small local/self-hosted deployment. If
    this server ever needs per-user identity or scoped tokens, that's the
    trigger to move to the SDK's OAuth support instead of extending this."""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        header = request.headers.get("authorization", "")
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or credential != self._token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_app(stateless: bool, host: str, auth_token: str | None) -> Starlette:
    app = mcp.streamable_http_app(stateless_http=stateless, host=host)
    if auth_token:
        app.add_middleware(_BearerAuthMiddleware, token=auth_token)
    return app


def run(
    host: str = "127.0.0.1",
    port: int = 8000,
    stateless: bool = True,
    auth_token: str | None = None,
) -> None:
    import uvicorn

    logger.info(
        "mcp-serve: starting on %s:%d (stateless=%s, auth=%s, vault=%s)",
        host,
        port,
        stateless,
        "enabled" if auth_token else "disabled",
        _container.settings.vault_path,
    )
    if not auth_token and host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "mcp-serve: binding to %s with no MCP_AUTH_TOKEN set — the vault is "
            "reachable by anyone who can reach this host, with no authentication",
            host,
        )
    app = build_app(stateless=stateless, host=host, auth_token=auth_token)
    uvicorn.run(app, host=host, port=port, log_level=_settings.log_level.lower())
