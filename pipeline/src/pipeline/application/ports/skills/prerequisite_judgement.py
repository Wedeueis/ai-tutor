from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DraftConcept
from pipeline.domain.eval import Rubric
from pipeline.domain.prerequisites import PrerequisiteAssessment, PrerequisiteCandidate


class PrerequisiteJudgementSkillPort(Protocol):
    """LLM-backed: for each candidate, scores whether the draft genuinely
    *requires* it — whether a learner ignorant of the candidate could follow
    the draft at all.

    Returns one `PrerequisiteAssessment` per candidate it judged, each holding
    raw rubric scores. Which tier those scores earn is NOT decided here: that's
    `domain/prerequisites.py`'s `select_prerequisites`, the same split
    `QualityEvalSkillPort` makes by leaving the rollup to `aggregate_scores`.
    A candidate may be omitted from the result entirely when it is plainly
    unrelated — an omitted candidate is not an edge."""

    def judge(
        self,
        draft: DraftConcept,
        candidates: list[PrerequisiteCandidate],
        rubrics: list[Rubric],
    ) -> list[PrerequisiteAssessment]: ...
