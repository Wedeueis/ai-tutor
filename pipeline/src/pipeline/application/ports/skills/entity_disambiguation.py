from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import CandidateMatch, DisambiguationVerdict, DraftConcept


class EntityDisambiguationSkillPort(Protocol):
    """LLM-backed: given a draft and candidate existing concepts (from vector
    search), decide same-entity (merge/link) vs. genuinely new (create)."""

    def disambiguate(
        self, draft: DraftConcept, candidates: list[CandidateMatch]
    ) -> DisambiguationVerdict: ...
