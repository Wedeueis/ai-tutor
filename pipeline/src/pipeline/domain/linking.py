"""Pure markdown body helpers for weaving §6 links into concept bodies.
Maintains one invariant everywhere a body is mutated after creation: a
trailing link-list section (`## Related` on a normal concept, `## Derived
concepts` on a source-document hub) is always the LAST section of the body —
merges insert their addition before it (`insert_before_related`), and new
links are appended into it in place, deduped by concept id
(`add_link_section`). No I/O — pure string transforms."""

from __future__ import annotations

from pipeline.domain.agent import RelatedConcept

_RELATED_HEADING = "## Related"


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


def _has_link(body: str, concept_id) -> bool:
    return f"(/{concept_id}.md)" in body
