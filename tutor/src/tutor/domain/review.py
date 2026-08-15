"""The review log — the single source of truth for what the learner knows.

There is no `LearnerModel` aggregate and no `MasteryScore`. The learner's state
*is* this append-only log (PRD v3 §3.2, decided in #9 and #18); FSRS state and
mastery are projections over it, rebuildable by replay.

There is no `user_id` anywhere. This system has exactly one learner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tutor.domain.scheduling import Rating


@dataclass(frozen=True)
class ReviewEvent:
    """One review, appended and never modified.

    Carries **the full exchange as text**, not pointers: the question asked,
    the rubric used to grade it, the learner's answer, and the resulting grade.
    A row has to stay independently interpretable years later, after the
    concept has been rewritten and the rubric file has moved or been deleted —
    a pointer would rot and take the only record of the exchange with it.

    `algorithm` and `parameters` record the scheduling identity in force at the
    time. They are what makes a checkpoint verifiable: a checkpoint is valid
    only for the exact `(algorithm, parameters)` that produced it, and changing
    either forces a full replay from the first event (PRD v3 §7)."""

    concept_id: str
    rating: Rating
    reviewed_at: datetime
    algorithm: str
    parameters: str
    question: str
    rubric: str
    answer: str
    grade: str
    discursive: bool = False
    """Whether this was a free-text answer graded against a rubric rather than
    a self-reported recall grade. The `specialist` depth level's evidence
    requirement needs to distinguish them (PRD v3 RF4.4)."""
