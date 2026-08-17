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
_FOOTNOTES_HEADING = "## Sources"

_TRAILING_HEADINGS = (
    _FOOTNOTES_HEADING,
    _PREREQUISITES_HEADING,
    _CATEGORIES_HEADING,
    _RELATED_HEADING,
)
"""Sections that live *after* a concept's prose, in no particular order among
themselves. Prose additions go before all of them; `## Related` still ends up
last because `add_link_section` only ever appends into it."""


def insert_before_related(body: str, addition: str) -> str:
    """Inserts `addition` after the prose and before **every** trailing
    section, so merge additions accumulate with the prose they belong to
    rather than landing inside a link or footnote list.

    Targets the *first* trailing section rather than `## Related` alone. Aiming
    only at `## Related` was survivable while the sections in between held
    links — an addition landing under `## Categories` was untidy but harmless.
    It stopped being harmless once `## Sources` began carrying footnote
    definitions: a paragraph inserted between a definition and the next one
    reads as part of the footnote list, and the marker it carries ends up
    detached from the prose it attributes."""
    index = _first_trailing_section(body)
    if index == -1:
        return f"{body}\n\n{addition}"
    return f"{body[:index].rstrip()}\n\n{addition}\n\n{body[index:].strip()}\n"


def _first_trailing_section(body: str) -> int:
    """Index of the earliest trailing section heading, or -1 for none."""
    found = [
        index
        for index in (body.find(f"\n{heading}") for heading in _TRAILING_HEADINGS)
        if index != -1
    ]
    return min(found) if found else -1


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


def cite(text: str, label: str) -> str:
    """Attaches a footnote marker to a block of body text (WIKI_SPEC §5.1).

    The marker goes at the end of the block's last non-empty line rather than
    on a line of its own, because `[^label]` alone renders as a stray link.
    Idempotent: a block already carrying this label is returned unchanged, so
    re-running ingest over the same chunk cannot stack markers."""
    marker = f"[^{label}]"
    if marker in text:
        return text

    lines = text.rstrip().split("\n")
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip():
            lines[index] = f"{lines[index].rstrip()}{marker}"
            break
    else:
        return text
    return "\n".join(lines)


def cite_body(body: str, label: str) -> str:
    """`cite`, but aimed at a body's prose rather than at a bare block.

    By the time a created concept is stamped with its source, its body already
    carries the woven `## Categories` / `## Related` sections — so citing the
    body's true last line would hang the footnote marker off a link bullet.
    Everything before the first `## ` heading is the prose; that is what a
    passage actually produced, and that is what gets the marker."""
    index = body.find("\n## ")
    if index == -1:
        return cite(body, label)
    head, tail = body[:index], body[index:]
    return f"{cite(head, label)}\n{tail.lstrip(chr(10))}"


def add_footnote(body: str, label: str, definition: str) -> str:
    """Ensures `body` carries a `[^label]: ...` definition, deduped by label.

    Definitions live under their own `## Sources` heading rather than at the
    very bottom of the file, so that the module invariant holds: a trailing
    link section stays last. Renderers that support footnotes collect them at
    the bottom of the *rendered* page regardless of where they are written, so
    nothing is lost by keeping the source tidy."""
    if f"\n[^{label}]:" in body or body.startswith(f"[^{label}]:"):
        return body
    return _append_to_section(body, _FOOTNOTES_HEADING, f"[^{label}]: {definition}")
