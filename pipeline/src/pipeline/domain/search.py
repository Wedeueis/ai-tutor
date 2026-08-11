"""Reciprocal rank fusion — combines several independently-ranked candidate
lists (e.g. semantic, lexical, graph) into one ranking, without needing their
scores to be on comparable scales. Pure domain logic, no I/O."""

from __future__ import annotations

from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import ConceptId

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    *ranked_id_lists: list[ConceptId], k: int = DEFAULT_RRF_K
) -> list[CandidateMatch]:
    """For each list, a concept's contribution is 1 / (k + rank), rank being its
    1-indexed position within that list. Contributions are summed across every
    list a concept appears in, then the merged set is sorted descending."""
    scores: dict[ConceptId, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, concept_id in enumerate(ranked_ids, start=1):
            scores[concept_id] = scores.get(concept_id, 0.0) + 1.0 / (k + rank)

    return sorted(
        (CandidateMatch(concept_id=concept_id, score=score) for concept_id, score in scores.items()),
        key=lambda match: match.score,
        reverse=True,
    )
