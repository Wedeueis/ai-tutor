"""FSRS scheduling state and the rating scale that drives it. Pure domain —
no I/O, no dependencies, nothing to mock (NFR7).

The scheduling *algorithm* lands in this module in Task 2.1, tested
differentially against `py-fsrs`. This file currently defines only the state
the rest of the system needs to talk about."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Rating(IntEnum):
    """FSRS's four-point grade. The values are FSRS's own and are stored raw in
    `review_events`, so a replay years from now does not depend on this enum
    still existing."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class State(IntEnum):
    """Where a concept sits in the FSRS learning progression."""

    LEARNING = 1
    REVIEW = 2
    RELEARNING = 3


@dataclass(frozen=True)
class SchedulerState:
    """FSRS state for one **concept** — not one card. Assessments are ephemeral
    and regenerated per review, so there is no card identity to key on
    (PRD v3 RF4.3).

    A projection, rebuildable by replaying `review_events`. Never authoritative:
    if this disagrees with the log, the log is right.

    `stability` and `retrievability` are deliberately different things.
    Stability is durability and moves only when you review, so it is what
    `meets_target` keys on; retrievability decays with time alone and drives
    *when* to review. Keying mastery on retrievability would reshuffle the
    study plan with no new evidence (PRD v3 RF3.2)."""

    stability: float | None = None
    difficulty: float | None = None
    due: datetime | None = None
    last_review: datetime | None = None
    state: State = State.LEARNING
    step: int = 0
