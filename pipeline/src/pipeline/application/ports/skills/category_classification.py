from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import CategoryCandidate, CategoryClassificationVerdict, DraftConcept


class CategoryClassificationSkillPort(Protocol):
    """LLM-backed: assigns a draft to zero or more existing `type: Category`
    concepts (scoped to the draft's domain), or proposes new category titles
    when nothing existing plausibly fits — the Wikipedia-style ontology layer
    underneath `type: Domain`."""

    def classify(
        self, draft: DraftConcept, known_categories: list[CategoryCandidate]
    ) -> CategoryClassificationVerdict: ...
