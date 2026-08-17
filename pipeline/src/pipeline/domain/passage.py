"""A passage: the original text a concept was distilled from.

**Not a concept.** It has no markdown file, no row in `concepts`, no entry in
`links`, and it never appears in a search result. It surfaces only as a §5.1
source — which is the whole point of the distinction: the vault holds curated
knowledge, and a passage is the raw material that knowledge was read out of.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Passage:
    id: str
    text: str
    ordinal: int | None = None
    source_concept_id: str | None = None
    """The `references/<slug>` hub for the document this came from, when the
    passage came from a parsed document at all. A hand-written note in
    `vault/raw/` produced no hub and has none."""

    @property
    def locator(self) -> str | None:
        """Display text for *where* this is, matching the `sources[].locator`
        written into the concept's frontmatter, so the two agree without
        either having to parse the other."""
        return None if self.ordinal is None else f"passage {self.ordinal}"

    @property
    def source_id(self) -> str | None:
        """The `sources[].id` this passage earned on the concepts it produced
        — the footnote label. Derived the same way `_add_source` derives it,
        which is what lets a caller ask for one specific citation."""
        if self.source_concept_id is None:
            return None
        slug = self.source_concept_id.rsplit("/", 1)[-1]
        return f"{slug}-p{self.ordinal}" if self.ordinal is not None else None


@dataclass(frozen=True)
class RecalledPassage:
    """A passage plus the text around it — what "read it in context" means.

    Neighbours are carried as rendered text rather than as `Passage` objects
    because the caller is a model reading prose, not code walking a list."""

    passage: Passage
    before: str | None = None
    after: str | None = None
