"""The LLM-backed seam: writing a question, and scoring the answer against it.

Two verbs, kept apart because they happen at different times with the learner's
answer in between — and because only the first one may look at the concept. A
grader that could re-read the vault while judging would be free to mark an
answer wrong for omitting something the question never asked.

**Nothing here decides a rating.** The model scores each rubric independently;
`rating_for` maps the rollup, in pure domain code (RF4.4). Keeping the port
narrow is what makes that split enforceable rather than a convention — there is
no verb here that returns a `Rating`.

Async, like `VaultPort`: these are model calls, and ADK runs the tutor inside an
event loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from tutor.application.ports.outbound.vault import Concept
from tutor.domain.assessment import Rubric, RubricScore
from tutor.domain.depth import DepthLevel


@dataclass(frozen=True)
class Assessment:
    """One question and the criteria its answer will be judged against.

    **Ephemeral** (RF4.3). Generated per review from the concept's current
    content, used once, and discarded — the review event's text is its only
    trace. It has no id and no persistence, because a stored item would need a
    card identity, deduplication, and invalidation when the concept is
    rewritten, and #10 removed all three by removing the item."""

    concept_id: str
    question: str
    rubrics: list[Rubric] = field(default_factory=list)


class AssessmentSkillPort(Protocol):
    async def generate(
        self, concept: Concept, level: DepthLevel
    ) -> Assessment:
        """Write a question from the concept's **current** content.

        `level` is passed because the depth target changes what a fair question
        is: `aware` asks whether the learner recognises the concept, while
        `specialist` asks them to explain it in their own words. Grading the
        same answer against a harder question is how the levels differ in
        practice, not just in their thresholds."""
        ...

    async def grade(
        self, assessment: Assessment, answer: str
    ) -> list[RubricScore]:
        """Score the answer against each rubric independently.

        One `RubricScore` per `Rubric`, and no verdict. A criterion the grader
        cannot judge comes back with `score=None` rather than a zero."""
        ...
