"""Pure markdown body helpers for weaving §6 links into concept bodies.
Maintains one invariant everywhere a body is mutated after creation: a
trailing link-list section (`## Related` on a normal concept, `## Derived
concepts` on a source-document hub) is always the LAST section of the body —
merges insert their addition before it (`insert_before_related`), and new
links are appended into it in place, deduped by concept id
(`add_link_section`). No I/O — pure string transforms."""

from __future__ import annotations

from pipeline.domain.agent import RelatedConcept
from pipeline.domain.prerequisites import PrerequisiteEdge

_RELATED_HEADING = "## Related"
_CATEGORIES_HEADING = "## Categories"
_PREREQUISITES_HEADING = "## Prerequisites"


def insert_before_related(body: str, addition: str) -> str:
    """Inserts `addition` immediately before a trailing `## Related` section,
    if one exists; otherwise appends it normally. Keeps `## Related` last
    even as merge additions accumulate after a concept was first created."""
    index = body.find(f"\n{_RELATED_HEADING}")
    if index == -1:
        return f"{body}\n\n{addition}"
    return f"{body[:index].rstrip()}\n\n{addition}\n\n{body[index:].strip()}\n"


def add_link_section(body: str, heading: str, links: list[RelatedConcept]) -> str:
    """Ensures `body` ends with `heading` containing one bullet per link not
    already present (deduped by concept id). Idempotent — safe to call again
    with links already present. `heading` must start with `#`."""
    new_links = [link for link in links if not _has_link(body, link.concept_id)]
    if not new_links:
        return body

    bullets = "\n".join(
        f"- [{link.title or link.concept_id}](/{link.concept_id}.md)"
        + (f" — {link.reason}" if link.reason else "")
        for link in new_links
    )

    index = body.find(f"\n{heading}")
    if index == -1:
        return f"{body}\n\n{heading}\n\n{bullets}\n"
    return f"{body.rstrip()}\n{bullets}\n"


def add_related_links(body: str, links: list[RelatedConcept]) -> str:
    """`add_link_section` under the `## Related` heading — see module docstring."""
    return add_link_section(body, _RELATED_HEADING, links)


def add_category_links(body: str, links: list[RelatedConcept]) -> str:
    """`add_link_section` under the `## Categories` heading — the Wikipedia-
    style ontology's concept -> Category edges."""
    return add_link_section(body, _CATEGORIES_HEADING, links)


def add_prerequisite_links(body: str, edges: list[PrerequisiteEdge]) -> str:
    """Writes each edge as a Dataview-style inline field under a
    `## Prerequisites` heading:

        requires:: [[/attention-mechanism]]

    The line format is not cosmetic. `SqliteMetadataRepository` scrapes typed
    links with `^([a-z][a-z0-9_-]*):: \\[\\[([^\\]]+)\\]\\]$` (MULTILINE), so a
    line with different spacing, or with anything trailing it, is silently not
    an edge at all — it renders fine in Obsidian and never reaches
    `typed_links`. Hence one edge per line, exactly, and the rationale kept out
    of the body (it lives in the bundle log instead).

    Deduped by **target**, not by rendered line: a concept already linked to
    the target at either tier is left alone, so re-running ingest or the
    backfill neither duplicates a line nor silently retiers an existing edge.
    """
    new_edges = [edge for edge in edges if not _has_typed_link(body, edge.target_id)]
    if not new_edges:
        return body

    lines = "\n".join(f"{edge.relation_type}:: [[/{edge.target_id}]]" for edge in new_edges)
    return _append_to_section(body, _PREREQUISITES_HEADING, lines)


def _append_to_section(body: str, heading: str, addition: str) -> str:
    """Appends `addition` to the end of `heading`'s section, creating the
    section before any trailing `## Related` if it doesn't exist yet. Unlike
    `add_link_section`, this doesn't assume its section is the body's last —
    `## Related` is, by the invariant in this module's docstring."""
    index = body.find(f"\n{heading}")
    if index == -1:
        return insert_before_related(body, f"{heading}\n\n{addition}")

    next_heading = body.find("\n## ", index + len(heading))
    if next_heading == -1:
        return f"{body.rstrip()}\n{addition}\n"
    return f"{body[:next_heading].rstrip()}\n{addition}\n{body[next_heading:]}"


def _has_link(body: str, concept_id: object) -> bool:
    return f"(/{concept_id}.md)" in body


def _has_typed_link(body: str, concept_id: object) -> bool:
    """Any relation type pointing at this target. Deliberately blind to which
    one — see `add_prerequisite_links`. Note `_has_link` cannot serve here: it
    matches the `(/id.md)` markdown form, never the `[[/id]]` wikilink one."""
    return f"[[/{concept_id}]]" in body
