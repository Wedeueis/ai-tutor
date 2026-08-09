from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DraftConcept
from pipeline.domain.eval import Rubric, RubricScore


class QualityEvalSkillPort(Protocol):
    """LLM-backed: scores a draft against each rubric independently (returning one
    RubricScore per Rubric), given the original raw text for grounding checks.
    Pass/fail is NOT decided here — that's deterministic domain logic, see
    domain/eval.py's aggregate_scores."""

    def evaluate(
        self, draft: DraftConcept, rubrics: list[Rubric], raw_content: str
    ) -> list[RubricScore]: ...
