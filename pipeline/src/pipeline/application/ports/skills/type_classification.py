from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DraftConcept, TypeClassificationVerdict


class TypeClassificationSkillPort(Protocol):
    """LLM-backed: resolves a draft's `type` against the vocabulary of types already
    in use in the vault, so producers don't mint near-duplicate type names."""

    def classify(
        self, draft: DraftConcept, known_types: list[str]
    ) -> TypeClassificationVerdict: ...
