from __future__ import annotations

from typing import Protocol

from pipeline.domain.passage import Passage


class PassageReaderPort(Protocol):
    """Reading back the original text a concept was distilled from.

    **Read-only, and deliberately narrow.** Nothing here writes: passages are
    produced by `parse-sources` as a side effect of chunking, and a port that
    could also create one would invite a second writer for material that must
    stay a faithful copy of the source.

    Today this is backed by the intake store, where chunks already live with
    their text and `ordinal`. That store is a work queue — `pipeline clear
    --reset-intake` empties it, taking the passages and the concept↔passage
    edge with them — so recall degrades to "nothing recorded" after an intake
    reset. Making passages durable means moving them to their own table and
    swapping the adapter behind this port; no caller changes.
    """

    def for_concept(self, concept_id: str) -> list[Passage]:
        """Every passage that contributed to this concept, in document order.

        More than one is the normal case for a concept merged from several
        parts of one document — which is exactly what per-passage
        `sources[].id` was introduced to make legible."""
        ...

    def neighbours(self, passage_id: str, radius: int = 1) -> list[Passage]:
        """Passages adjacent to this one in the same document, ordinal-ordered
        and excluding the passage itself.

        Adjacency is by position, not by distance: chunks skipped as garbled
        tables leave gaps in the ordinals, so "the next passage" is the next
        one that survived, and a gap honestly means something is missing in
        between rather than that the two are contiguous."""
        ...
