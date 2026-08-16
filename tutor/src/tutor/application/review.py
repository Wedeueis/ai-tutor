"""One review, end to end: ask, grade, record.

The shape of this module follows from #10. There is no `AssessmentItem` table,
no card, and nothing to invalidate when a concept is rewritten — an assessment
is generated from the concept's current content, used once, and thrown away.
**The review event is its only trace**, which is why the event carries the whole
exchange as text rather than pointers to things that will move or be deleted.

Two ways in, and the difference between them is evidence rather than
convenience:

- `review` — a written answer graded against rubrics. Marked `discursive`, and
  the only kind that satisfies `specialist` (RF4.4).
- `self_report` — the learner grading their own recall, as in any flashcard
  app. Cheap, honest about what it is, and never enough for the top level.

Both append to the same log and both go through the same scheduler. The log
does not have two shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tutor.application.ports.outbound.assessment import Assessment, AssessmentSkillPort
from tutor.application.ports.outbound.learner_store import LearnerStorePort
from tutor.application.ports.outbound.vault import VaultPort
from tutor.domain.assessment import (
    aggregate_scores,
    rating_for,
    render_grade,
    render_rubrics,
)
from tutor.domain.depth import DEFAULT_DEPTH_LEVEL, DepthLevel
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import ALGORITHM, PARAMETERS_ID, Rating

SELF_REPORTED = "self-reported recall"
"""What stands in for a rubric when there was none. The event's `rubric` field
is never empty: a row that says nothing about how it was graded is a row nobody
can interpret later."""


class ConductReview:
    """Generates an assessment, grades the answer, and appends the event.

    Holds the scheduling identity because the *event* carries it: `algorithm`
    and `parameters` record what was in force when the review happened, and a
    checkpoint is valid only for the exact pair that produced it (§7)."""

    def __init__(
        self,
        vault: VaultPort,
        learner_store: LearnerStorePort,
        assessments: AssessmentSkillPort,
        algorithm: str = ALGORITHM,
        parameters: str = PARAMETERS_ID,
    ) -> None:
        self._vault = vault
        self._learner_store = learner_store
        self._assessments = assessments
        self._algorithm = algorithm
        self._parameters = parameters

    async def ask(
        self, concept_id: str, level: DepthLevel = DEFAULT_DEPTH_LEVEL
    ) -> Assessment:
        """Read the concept **now** and write a question from what it says now.

        Deliberately re-read every time rather than cached: the vault is
        authoritative and `pipeline` rewrites concepts as it ingests more, so a
        question generated last month may be asking about text that no longer
        exists. Regenerating is what makes there be nothing to invalidate."""
        concept = await self._vault.get_concept(concept_id)
        return await self._assessments.generate(concept, level)

    async def record(
        self,
        assessment: Assessment,
        answer: str,
        *,
        reviewed_at: datetime | None = None,
    ) -> ReviewEvent:
        """Grade a written answer and append the event.

        Raises `NotGraded` if the grader scored nothing — and appends nothing
        in that case. A grading failure must not be written into an append-only
        log as a lapse the learner never had."""
        result = aggregate_scores(await self._assessments.grade(assessment, answer))
        rating = rating_for(result)  # raises before anything is written
        return self._append(
            concept_id=assessment.concept_id,
            rating=rating,
            reviewed_at=reviewed_at,
            question=assessment.question,
            rubric=render_rubrics(assessment.rubrics),
            answer=answer,
            grade=render_grade(result),
            discursive=True,
        )

    def self_report(
        self,
        concept_id: str,
        rating: Rating,
        *,
        question: str = "",
        answer: str = "",
        reviewed_at: datetime | None = None,
    ) -> ReviewEvent:
        """The learner grading their own recall. Synchronous — no model is
        involved, which is the entire difference.

        **Not** marked discursive: no rubric judged it, so it cannot be the
        evidence `specialist` asks for, however honest the learner is being."""
        return self._append(
            concept_id=concept_id,
            rating=rating,
            reviewed_at=reviewed_at,
            question=question,
            rubric=SELF_REPORTED,
            answer=answer,
            grade=f"self-reported {rating.name.lower()}",
            discursive=False,
        )

    def _append(
        self,
        *,
        concept_id: str,
        rating: Rating,
        reviewed_at: datetime | None,
        question: str,
        rubric: str,
        answer: str,
        grade: str,
        discursive: bool,
    ) -> ReviewEvent:
        event = ReviewEvent(
            concept_id=concept_id,
            rating=rating,
            reviewed_at=reviewed_at or datetime.now(UTC),
            algorithm=self._algorithm,
            parameters=self._parameters,
            question=question,
            rubric=rubric,
            answer=answer,
            grade=grade,
            discursive=discursive,
        )
        self._learner_store.append_review(event)
        return event
