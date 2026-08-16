"""The conversation, as a seam.

Code drives the session and the model teaches inside it (#39). This port is
where the model gets its turn — and the shape of the port is what enforces the
division: it can pose a question and it can teach, and **neither verb returns
anything the schedule reads**. `pose` returns what the learner said; `teach`
returns nothing at all.

Two verbs rather than one open-ended `converse`, because the boundary between
them is where the review event is written. Everything before `pose` returns is
unassisted recall and gets graded; everything in `teach` is help, and moves
nothing.

The ADK agent, the runner and the session live behind this. Nothing in
`teaching.py` imports ADK, which is what lets the entire loop — the queue, the
cap, the grading boundary, the skip rule — be tested without a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.vault import Concept
from tutor.domain.learner_context import LearnerContext
from tutor.domain.review import ReviewEvent


@dataclass(frozen=True)
class Answer:
    """What came back from the learner.

    `skipped` and `abandoned` are **structural**, not inferred from the text.
    Telling "I don't know" from "not this one, not now" by reading prose would
    put model judgement back on the write path, on the one path where being
    wrong is permanent (#39, and #36's `NotGraded` reasoning). A skip is a
    command the interface reads directly; anything the learner *types* is an
    attempt."""

    text: str = ""
    skipped: bool = False
    abandoned: bool = False
    """The learner closed the session mid-question. Writes nothing — and needs
    no cleanup, because every earlier review was already committed (#39)."""

    @property
    def is_attempt(self) -> bool:
        """"I don't know" is an attempt, and the most informative `AGAIN` there
        is. Only an explicit skip, an abandonment or an empty submission is
        not."""
        return not (self.skipped or self.abandoned) and bool(self.text.strip())


class TeachingTurnPort(Protocol):
    async def pose(
        self,
        assessment: Assessment,
        concept: Concept,
        context: LearnerContext,
    ) -> Answer:
        """Put the question to the learner and return their **first** response.

        The first, unassisted one — that is the whole contract. An
        implementation that let the agent hint, nudge or partially answer
        before returning would hand FSRS assisted recall while it computes
        stability as though the recall were unassisted, and every later
        interval would be derived from evidence that does not exist (#39)."""
        ...

    async def teach(
        self,
        assessment: Assessment,
        answer: Answer,
        event: ReviewEvent | None,
    ) -> None:
        """Everything after the grade: correct it, explain it, take follow-ups.

        Unbounded, and returns nothing, because **nothing here moves the
        schedule**. The event is already written by the time this is called. If
        the answer was bad the concept is already back in the queue, and this
        is the teaching that gives the second attempt a chance.

        `event` is the row that was just written — it carries the rating and
        the grade text, so this needs no second view of the grading. It is None
        when the answer could not be graded, in which case nothing was
        written."""
        ...
