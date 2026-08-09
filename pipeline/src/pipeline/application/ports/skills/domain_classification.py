from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DomainCandidate, DomainClassificationVerdict, DraftConcept


class DomainClassificationSkillPort(Protocol):
    """LLM-backed: resolves which existing Domain (if any) a draft belongs to. Low
    confidence should yield `domain=None` rather than a forced or invented match —
    Domains stay human-curated."""

    def classify(
        self, draft: DraftConcept, candidates: list[DomainCandidate]
    ) -> DomainClassificationVerdict: ...
