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

from mcp.server.mcpserver import MCPServer

from pipeline.adapters.filesystem import frontmatter_codec, frontmatter_mapping
from pipeline.cli.main import Container
from pipeline.config import Settings
from pipeline.domain.concept import ConceptId

mcp = MCPServer(
    "okf-wiki",
    instructions=(
        "Search and read concepts from this Open Knowledge Format (OKF) vault. "
        "Concept ids are bundle-relative paths without the `.md` suffix "
        "(e.g. `domains/observability/logging`). Use search_wiki to find "
        "relevant concepts, then get_concept to read one in full."
    ),
)

# Built once per process and reused across requests — the underlying adapters
# (ChromaDB, SQLite, the markdown repository) are safe to share, and rebuilding
# the container per call would reopen those stores on every tool invocation.
_container = Container(Settings.from_env())


@mcp.tool()
def search_wiki(query: str, k: int = 5) -> list[dict]:
    """Semantic search over the vault's concepts. Returns the closest matches
    to the query, most relevant first, with their similarity score."""
    matches = _container.search_concepts.run(query, k=k)
    return [{"concept_id": str(match.concept_id), "score": match.score} for match in matches]


@mcp.tool()
def get_concept(concept_id: str) -> str:
    """Fetch one concept's full content — YAML frontmatter plus markdown body
    — by its id (the bundle-relative path without `.md`, e.g. `references/rfc-9110`)."""
    concept = _container.concept_repository.load(ConceptId(concept_id))
    data = frontmatter_mapping.to_yaml(concept.frontmatter)
    return frontmatter_codec.render(data, concept.body)


@mcp.tool()
def list_concepts(concept_type: str | None = None) -> list[str]:
    """List concept ids in the vault. Pass concept_type (e.g. "Domain") to
    filter by frontmatter `type`; omit it to list every concept."""
    if concept_type is not None:
        return _container.metadata_repository.find_ids_by_type(concept_type)
    return [str(concept_id) for concept_id in _container.concept_repository.list()]


@mcp.tool()
def list_types(domain: str | None = None) -> list[str]:
    """List the distinct frontmatter `type` values in use, optionally scoped
    to one domain id (as recorded in a concept's `domain` frontmatter field)."""
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


def run(host: str = "127.0.0.1", port: int = 8000, stateless: bool = True) -> None:
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        stateless_http=stateless,
    )
