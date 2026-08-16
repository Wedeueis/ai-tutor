"""The vault adapter: parsing, and the tier boundary it has to hold.

The MCP session is faked rather than mocked with a library — what matters here
is what the adapter does with a *payload*, and `pipeline`'s tools return
loosely-typed dicts and rendered markdown that nothing downstream should have
to handle raw.

A live end-to-end test is marked `integration`; it needs `pipeline mcp-serve`.
"""

from __future__ import annotations

import json
import os

import pytest

from tutor.adapters.mcp.vault import (
    McpVault,
    VaultUnavailable,
    normalize_id,
    parse_concept,
)
from tutor.application.ports.outbound.vault import Concept, Edge


@pytest.fixture
def anyio_backend():
    return "asyncio"


CONCEPT = """---
type: Concept
title: Multi-head attention
description: Several attention heads in parallel.
domain: domains/machine-learning
generated:
  by: pipeline/0.1
  at: 2026-01-01
---

Multi-head attention runs several attention operations in parallel.

## Prerequisites

requires:: [[/scaled-dot-product-attention]]

## Categories

- [Attention](/categories/attention.md)
- [Transformers](/categories/transformers.md)

## Related

- [Qubits](/qubits.md)
"""


class FakeSession:
    """Stands in for an initialized `ClientSession`."""

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, tool: str, arguments: dict):
        self.calls.append((tool, arguments))
        return _Result(self._responses[tool])


class _Result:
    def __init__(self, payload: object, is_error: bool = False) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.content = [_Text(text)]
        self.structuredContent = None
        self.isError = is_error


class _Text:
    def __init__(self, text: str) -> None:
        self.text = text


def _vault(responses: dict[str, object]) -> tuple[McpVault, FakeSession]:
    vault = McpVault("http://127.0.0.1:8000/mcp")
    session = FakeSession(responses)
    vault._session = session  # type: ignore[assignment]
    return vault, session


# --- parsing a concept ---------------------------------------------------


def test_frontmatter_and_body_are_separated():
    concept = parse_concept("multi-head-attention", CONCEPT)

    assert concept.concept_id == "multi-head-attention"
    assert concept.title == "Multi-head attention"
    assert concept.description == "Several attention heads in parallel."
    assert concept.domain == "domains/machine-learning"
    assert concept.body.startswith("Multi-head attention runs")


def test_categories_are_read_from_the_body_not_the_frontmatter():
    """Category membership is §6 links under a `## Categories` heading — the
    ontology rides on the ordinary link graph."""
    concept = parse_concept("multi-head-attention", CONCEPT)

    assert concept.categories == ["categories/attention", "categories/transformers"]


def test_links_outside_the_categories_section_are_not_categories():
    """`## Related` sits right after it in the same body."""
    assert "qubits" not in parse_concept("x", CONCEPT).categories


def test_a_concept_with_no_categories_section_has_none():
    rendered = "---\ntype: Concept\n---\n\nJust a body.\n"

    assert parse_concept("x", rendered).categories == []


def test_content_without_frontmatter_is_read_as_a_body():
    """§11 says tolerate, not reject. A reader that raised here would fail on
    material a human can plainly read."""
    concept = parse_concept("x", "Just some markdown.")

    assert concept.body == "Just some markdown."
    assert concept.title is None


def test_unparseable_frontmatter_does_not_raise():
    rendered = "---\ntype: [unclosed\n---\n\nBody survives.\n"

    concept = parse_concept("x", rendered)

    assert concept.body == "Body survives."
    assert concept.title is None


def test_unknown_frontmatter_keys_are_ignored_not_rejected():
    rendered = "---\ntype: Concept\ntitle: T\nsome_future_field: 1\n---\n\nBody.\n"

    assert parse_concept("x", rendered).title == "T"


def test_an_empty_title_reads_as_absent():
    rendered = "---\ntype: Concept\ntitle: '  '\n---\n\nBody.\n"

    assert parse_concept("x", rendered).title is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("/a/b.md", "a/b"), ("a/b.md", "a/b"), ("/a/b", "a/b"), ("a/b", "a/b")],
)
def test_link_forms_normalize_to_one_id(raw, expected):
    assert normalize_id(raw) == expected


# --- the tools -----------------------------------------------------------


@pytest.mark.anyio
async def test_get_concept_returns_a_parsed_concept():
    vault, session = _vault({"get_concept": CONCEPT})

    concept = await vault.get_concept("multi-head-attention")

    assert isinstance(concept, Concept)
    assert concept.title == "Multi-head attention"
    assert session.calls == [("get_concept", {"concept_id": "multi-head-attention"})]


@pytest.mark.anyio
async def test_search_returns_matches():
    vault, session = _vault(
        {"search_wiki": [{"concept_id": "a", "score": 0.9}, {"concept_id": "b", "score": 0.4}]}
    )

    matches = await vault.search("attention", k=2)

    assert [(m.concept_id, m.score) for m in matches] == [("a", 0.9), ("b", 0.4)]
    assert session.calls == [("search_wiki", {"query": "attention", "k": 2})]


@pytest.mark.anyio
async def test_search_tolerates_a_malformed_row():
    vault, _ = _vault({"search_wiki": [{"concept_id": "a", "score": 0.9}, {"oops": 1}, None]})

    assert [m.concept_id for m in await vault.search("q")] == ["a"]


# --- prerequisites, and the tier boundary --------------------------------


@pytest.mark.anyio
async def test_prerequisites_asks_only_for_the_requires_tier():
    """`may_require::` is recorded for human review and is inert by design.
    A plan that walked it would send the learner to study things the gate
    explicitly declined to vouch for."""
    vault, session = _vault({"trace_lineage": []})

    await vault.prerequisites("multi-head-attention", max_hops=2)

    _, arguments = session.calls[0]
    assert arguments["relation_type"] == "requires"
    assert arguments["direction"] == "outgoing"
    assert arguments["max_hops"] == 2


@pytest.mark.anyio
async def test_a_may_require_edge_is_dropped_even_if_the_server_returns_one():
    """Belt and braces: the server already filters, but nothing downstream
    distinguishes the tiers, so a stray edge would silently become a hard
    dependency."""
    vault, _ = _vault(
        {
            "trace_lineage": [
                [{"from": "a", "to": "/b", "relation_type": "requires"}],
                [{"from": "a", "to": "/c", "relation_type": "may_require"}],
            ]
        }
    )

    edges = await vault.prerequisites("a")

    assert [e.to_id for e in edges] == ["b"]


@pytest.mark.anyio
async def test_paths_are_flattened_into_unique_edges():
    """`trace_lineage` returns every path, so a shared edge appears on several.
    The caller wants a dependency graph, and one dependency is one edge."""
    vault, _ = _vault(
        {
            "trace_lineage": [
                [{"from": "a", "to": "/b", "relation_type": "requires"}],
                [
                    {"from": "a", "to": "/b", "relation_type": "requires"},
                    {"from": "b", "to": "/c", "relation_type": "requires"},
                ],
            ]
        }
    )

    edges = await vault.prerequisites("a")

    assert edges == [
        Edge(from_id="a", to_id="b", relation_type="requires"),
        Edge(from_id="b", to_id="c", relation_type="requires"),
    ]


@pytest.mark.anyio
async def test_no_prerequisites_is_an_empty_list_not_an_error():
    vault, _ = _vault({"trace_lineage": []})

    assert await vault.prerequisites("a") == []


@pytest.mark.anyio
async def test_a_failed_tool_call_names_the_vault_as_unavailable():
    """Distinct from "that concept does not exist": a session can carry on
    without one concept, but not without the vault."""
    vault = McpVault("http://127.0.0.1:8000/mcp")

    class Failing:
        async def call_tool(self, tool, arguments):
            return _Result("connection refused", is_error=True)

    vault._session = Failing()  # type: ignore[assignment]

    with pytest.raises(VaultUnavailable):
        await vault.get_concept("x")


# --- against a live server -----------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reads_the_real_vault_over_mcp():
    """Needs `cd pipeline && uv run pipeline mcp-serve`.

    The faked tests above pin the parsing; this one pins that the payload
    shapes are what the real server actually sends."""
    url = os.environ.get("PIPELINE_MCP_URL", "http://127.0.0.1:8000/mcp")
    vault = McpVault(url)
    try:
        matches = await vault.search("attention", k=3)
        assert matches, "the vault returned no matches for a broad query"

        concept = await vault.get_concept(matches[0].concept_id)
        assert concept.concept_id == matches[0].concept_id
        assert concept.body

        # Should not raise whether or not this concept has any edges yet.
        assert isinstance(await vault.prerequisites(concept.concept_id), list)
    finally:
        await vault.aclose()
