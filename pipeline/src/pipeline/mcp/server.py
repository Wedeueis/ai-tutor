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


@mcp.tool()
def search_wiki(query: str, k: int = 5) -> list[dict]:
    """Semantic search over the vault's concepts. Returns the closest matches
    to the query, most relevant first, with their similarity score."""
    logger.info("mcp: search_wiki(query=%r, k=%d)", query, k)
    matches = _container.search_concepts.run(query, k=k)
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


def _vault_file(relative_path: str) -> str:
    path = _container.settings.vault_path / relative_path
    return path.read_text(encoding="utf-8")


@mcp.resource("okf://moc", name="MOC", description="Curated, thematic entry point into the vault.")
def moc() -> str:
    return _vault_file("MOC.md")


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
    description="Chronological update history for the vault (OKF §9).",
)
def log() -> str:
    return _vault_file("log.md")


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
