"""`VaultPort` over `pipeline`'s MCP server — the only way `tutor` reaches the
vault (PRD v3 §2, rule 1).

Read-only, and structurally so: nothing here calls a writing tool, because
`pipeline`'s MCP surface does not expose one. `tutor` never writes the OKF
bundle (#8).

This is a plain MCP **client**, not an `McpToolset`. `agent/` wires a toolset so
a model can call these tools; here the tutor's own code calls them — the study
plan needs `requires::` edges whether or not a model asked for them."""

from __future__ import annotations

import json
import logging
import re
from contextlib import AsyncExitStack
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tutor.application.ports.outbound.vault import Concept, ConceptMatch, Edge

logger = logging.getLogger(__name__)

REQUIRES = "requires"
"""The only prerequisite tier anything here reads.

`pipeline` also emits `may_require::` for edges its gate was not confident
about. Those are recorded for a human to review and are **inert by design**:
a study plan that walked them would send the learner to study things the gate
explicitly declined to vouch for."""

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)
_CATEGORIES_SECTION = re.compile(r"^##\s+Categories\s*$(.*?)(?=^##\s|\Z)", re.M | re.S)
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class McpVault:
    """Holds one MCP session open across calls, opened lazily on first use.

    `pipeline` serves this statelessly, so a fresh session per call would also
    be correct — it would just pay an initialize round-trip for every concept
    read, and a teaching session reads a lot of concepts."""

    def __init__(self, url: str, timeout_seconds: float = 30.0) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def _connect(self) -> ClientSession:
        if self._session is not None:
            return self._session

        stack = AsyncExitStack()
        try:
            read, write, _ = await stack.enter_async_context(
                streamable_http_client(self._url)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            # Never leave a half-open connection behind: the next call would
            # find `self._session` unset and try again against a live stack.
            await stack.aclose()
            raise

        self._stack, self._session = stack, session
        logger.debug("connected to pipeline MCP at %s", self._url)
        return session

    async def aclose(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = self._session = None

    async def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        session = await self._connect()
        result = await session.call_tool(tool, arguments)
        return _payload(result)

    # --- VaultPort -------------------------------------------------------

    async def get_concept(self, concept_id: str) -> Concept:
        rendered = await self._call("get_concept", {"concept_id": concept_id})
        return parse_concept(concept_id, str(rendered))

    async def search(self, query: str, k: int = 5) -> list[ConceptMatch]:
        rows = await self._call("search_wiki", {"query": query, "k": k})
        return [
            ConceptMatch(concept_id=str(row["concept_id"]), score=float(row["score"]))
            for row in rows or []
            if isinstance(row, dict) and "concept_id" in row
        ]

    async def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        """Walks `requires::` outward. No new MCP tool needed — `trace_lineage`
        already returns every typed path, which is more than reachability and
        exactly what a study plan needs to order work (RF3.1).

        Returns edges, not paths: the caller wants the dependency graph, and
        the same edge appearing on three paths is still one dependency."""
        paths = await self._call(
            "trace_lineage",
            {
                "concept_id": concept_id,
                "relation_type": REQUIRES,
                "direction": "outgoing",
                "max_hops": max_hops,
            },
        )
        edges: list[Edge] = []
        seen: set[tuple[str, str]] = set()
        for path in paths or []:
            for link in path or []:
                if not isinstance(link, dict):
                    continue
                edge = Edge(
                    from_id=normalize_id(str(link.get("from", ""))),
                    to_id=normalize_id(str(link.get("to", ""))),
                    relation_type=str(link.get("relation_type", "")),
                )
                # Defensive: `relation_type` was already filtered server-side,
                # but nothing downstream distinguishes the tiers, so a stray
                # `may_require::` edge would silently become a hard dependency.
                if edge.relation_type != REQUIRES:
                    continue
                key = (edge.from_id, edge.to_id)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(edge)
        return edges


def parse_concept(concept_id: str, rendered: str) -> Concept:
    """Rendered markdown (YAML frontmatter + body) back into a `Concept`.

    Tolerant on purpose, per WIKI_SPEC §11: unknown keys are ignored, a missing
    or unparseable frontmatter block yields a concept with an empty body rather
    than an error. `pipeline` owns conformance; a reader that rejected content
    would just make the tutor fail on material a human can plainly read."""
    match = _FRONTMATTER.match(rendered)
    if match is None:
        return Concept(concept_id=concept_id, body=rendered.strip())

    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        logger.warning("could not parse frontmatter for %s", concept_id)
        data = {}
    if not isinstance(data, dict):
        data = {}

    body = match.group(2)
    return Concept(
        concept_id=concept_id,
        title=_optional_str(data.get("title")),
        description=_optional_str(data.get("description")),
        body=body.strip(),
        domain=_optional_str(data.get("domain")),
        categories=_categories(body),
    )


def _categories(body: str) -> list[str]:
    """Category membership is §6 links under a `## Categories` heading, not a
    frontmatter field — the ontology rides on the ordinary link graph
    (CLAUDE.md, "Categories")."""
    section = _CATEGORIES_SECTION.search(body)
    if section is None:
        return []
    return [normalize_id(target) for target in _MARKDOWN_LINK.findall(section.group(1))]


def normalize_id(raw: str) -> str:
    """`/id.md`, `id.md` and `id` all name the same concept — the same
    normalization `pipeline` applies when it walks the graph."""
    target = raw[1:] if raw.startswith("/") else raw
    return target[: -len(".md")] if target.endswith(".md") else target


def _optional_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value.strip() else None


def _payload(result: Any) -> Any:
    """The useful part of a `CallToolResult`.

    Prefers `structuredContent`, falling back to decoding the text block —
    servers differ in which they populate, and a tool returning a bare string
    (`get_concept`) has no structured form at all."""
    if getattr(result, "isError", False):
        raise VaultUnavailable(f"MCP tool call failed: {_text(result)}")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]

    text = _text(result)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text  # a plain string, e.g. rendered markdown


def _text(result: Any) -> str | None:
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text is not None:
            return str(text)
    return None


class VaultUnavailable(RuntimeError):
    """The vault could not be read. Distinct from "the concept does not exist":
    a teaching session can carry on without one concept, but not without the
    vault."""
