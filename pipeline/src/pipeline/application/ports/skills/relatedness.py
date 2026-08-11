from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DraftConcept, RelatednessCandidate, RelatednessVerdict


class RelatednessSkillPort(Protocol):
    """LLM-backed: given a draft and candidate existing concepts (from vector
    search, already ruled out as the same entity), decide which are
    genuinely related and worth linking to — how clusters emerge in the
    link graph (WIKI_SPEC.md §6) instead of relying on flat tags."""

    def judge(
        self, draft: DraftConcept, candidates: list[RelatednessCandidate]
    ) -> RelatednessVerdict: ...
