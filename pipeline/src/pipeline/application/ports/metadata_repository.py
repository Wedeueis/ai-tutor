from __future__ import annotations

from datetime import date
from typing import Protocol

from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import Concept, LinkGraph, TypedLink


class MetadataRepositoryPort(Protocol):
    """Structured queries over concept metadata (type, tags, status, links, ...)
    that don't need a semantic/vector search."""

    def upsert(self, concept: Concept) -> None: ...

    def list_distinct_types(self, domain: str | None = None) -> list[str]: ...

    def find_ids_by_type(self, concept_type: str, domain: str | None = None) -> list[str]: ...

    def find_links(self, concept_id: str) -> LinkGraph: ...

    def search_fts(self, query: str, k: int) -> list[CandidateMatch]:
        """Lexical (BM25) search over concept bodies — hybrid search's stage-1
        lexical leg, alongside vector search."""
        ...

    def expand_neighbors(
        self,
        seed_ids: list[str],
        max_hops: int,
        decay: float,
        category_decay: float,
    ) -> dict[str, float]:
        """Walk the link graph outward from `seed_ids` up to `max_hops` hops,
        returning concept_id -> cumulative decayed score for every newly-reached
        concept (seeds excluded). A hop that enters/leaves a `type: Category`
        concept uses `category_decay` instead of `decay` — a shared category is
        a stronger topical signal than an arbitrary body link."""
        ...

    def find_by_type_and_date(
        self, concept_type: str, since: date | None, until: date | None
    ) -> list[str]:
        """Structured prefilter for `SearchConcepts`' stage 0 ("ontology-
        first") — concept ids of the given `type` whose `generated.at` falls
        within [`since`, `until`] (either bound may be None)."""
        ...

    def find_relations(self, concept_id: str, relation_type: str | None = None) -> list[TypedLink]:
        """Outgoing and incoming typed relations for one concept, optionally
        filtered to one `relation_type`."""
        ...

    def trace_lineage(
        self,
        concept_id: str,
        relation_type: str | None,
        direction: str,
        max_hops: int,
    ) -> list[list[TypedLink]]:
        """Every typed-relation path up to `max_hops` hops from `concept_id`
        (`direction` one of "outgoing", "incoming", "both") — the full chain
        (e.g. decision -> superseded_by -> decision), not just reachability,
        so a caller can reconstruct history rather than only confirm a link
        exists."""
        ...

    def delete(self, concept_id: str) -> None: ...
