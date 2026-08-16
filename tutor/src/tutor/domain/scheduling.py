"""FSRS-6 scheduling. Pure domain — no I/O, no dependencies, nothing to mock
(NFR7). The standard library is all this imports, deliberately.

**Why reimplement an algorithm we already have a package for.** `fsrs` is a
dev-only dependency and stays that way (RF4.2): it is the *oracle* the
differential test in `tests/domain/test_scheduling.py` checks this against. A
runtime dependency would make the oracle and the subject the same code, and the
test would then prove nothing. FSRS's formulas are empirical — nobody can check
them by reasoning, only by comparison against a reference — so that test is
load-bearing rather than a nicety.

**Fuzzing is off, and there is no switch for it.** `fsrs` fuzzes review
intervals by default via `random()`. Here the schedule has to be a pure
function of the review log: replaying the same events must rebuild the same
projection, and two concepts due the same day must order deterministically
(PRD v3 RF4.1). A randomised interval would make `SqliteLearnerStore.replay`
produce a different answer each time it ran.

**Keyed by concept, not by card.** Assessments are ephemeral and regenerated
per review (RF4.3), so there is no card identity — which is also why nothing
here has an id."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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


# --- FSRS-6 -------------------------------------------------------------

ALGORITHM = "fsrs-6"
"""Recorded on every `ReviewEvent` and on every checkpoint. A checkpoint is
valid only for the exact `(algorithm, parameters)` that produced it, so this
string is what makes a stale projection detectable rather than silently
wrong (PRD v3 §7)."""

DEFAULT_PARAMETERS: tuple[float, ...] = (
    0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001,
    1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
    1.8729, 0.5425, 0.0912, 0.0658, 0.1542,
)
"""FSRS-6's 21 fitted weights. Empirical: they came from fitting against review
histories, not from a derivation, which is exactly why the differential test
exists.

Re-fitting these to the learner's own history is a real future feature — and
the moment it happens, every checkpoint computed under the old set becomes
invalid. That is why `PARAMETERS_ID` below travels with the state."""

PARAMETERS_ID = "default"
"""Names the parameter *set*, not its values. Stored on each checkpoint beside
`ALGORITHM`; change the numbers above and this must change too, or replay will
resume from projections the new parameters never produced."""

DESIRED_RETENTION = 0.9
LEARNING_STEPS: tuple[timedelta, ...] = (timedelta(minutes=1), timedelta(minutes=10))
RELEARNING_STEPS: tuple[timedelta, ...] = (timedelta(minutes=10),)
MAXIMUM_INTERVAL_DAYS = 36500

_STABILITY_MIN = 0.001
_MIN_DIFFICULTY = 1.0
_MAX_DIFFICULTY = 10.0

_DECAY = -DEFAULT_PARAMETERS[20]
_FACTOR = 0.9 ** (1 / _DECAY) - 1


def retrievability(state: SchedulerState, at: datetime) -> float:
    """Probability of recall right now — the forgetting curve.

    Drives *when* to review. Deliberately **not** what `meets_target` reads:
    retrievability falls with the calendar alone, so keying mastery on it would
    un-master a concept overnight with no new evidence (RF3.2, issue #18)."""
    if state.last_review is None or state.stability is None:
        return 0.0
    elapsed_days = max(0, (at - state.last_review).days)
    return float((1 + _FACTOR * elapsed_days / state.stability) ** _DECAY)


def calculate_next_review(
    state: SchedulerState, rating: Rating, reviewed_at: datetime
) -> SchedulerState:
    """Advance one concept's schedule by one review.

    `reviewed_at` is **required**. Elapsed time since the last review drives the
    stability update, so PRD v2's two-argument signature could not have worked
    — the same rating means different things a day and a year later."""
    elapsed_days = (
        (reviewed_at - state.last_review).days if state.last_review else None
    )
    same_day = elapsed_days is not None and elapsed_days < 1

    if state.stability is None or state.difficulty is None:
        stability = _initial_stability(rating)
        difficulty = _clamp_difficulty(_initial_difficulty(rating))
    elif same_day:
        stability = _short_term_stability(state.stability, rating)
        difficulty = _next_difficulty(state.difficulty, rating)
    else:
        stability = _next_stability(
            state.difficulty, state.stability, retrievability(state, reviewed_at), rating
        )
        difficulty = _next_difficulty(state.difficulty, rating)

    next_state, next_step, interval = _next_schedule(state, rating, stability)
    return replace(
        state,
        stability=stability,
        difficulty=difficulty,
        state=next_state,
        step=next_step,
        due=reviewed_at + interval,
        last_review=reviewed_at,
    )


def _next_schedule(
    state: SchedulerState, rating: Rating, stability: float
) -> tuple[State, int, timedelta]:
    """Which state the concept lands in, and how far out it is scheduled.

    The learning and relearning ladders are structurally identical — same
    rules, different step lists — so they share one implementation rather than
    two that can drift apart."""
    if state.state is State.REVIEW:
        if rating is Rating.AGAIN and RELEARNING_STEPS:
            return State.RELEARNING, 0, RELEARNING_STEPS[0]
        return State.REVIEW, 0, _review_interval(stability)

    steps = LEARNING_STEPS if state.state is State.LEARNING else RELEARNING_STEPS
    return _step_through(steps, state.step, rating, stability)


def _step_through(
    steps: tuple[timedelta, ...], step: int, rating: Rating, stability: float
) -> tuple[State, int, timedelta]:
    graduated = (State.REVIEW, 0, _review_interval(stability))
    if not steps or (step >= len(steps) and rating is not Rating.AGAIN):
        return graduated

    if rating is Rating.AGAIN:
        return State.LEARNING if steps is LEARNING_STEPS else State.RELEARNING, 0, steps[0]

    current = State.LEARNING if steps is LEARNING_STEPS else State.RELEARNING
    if rating is Rating.HARD:
        if step == 0 and len(steps) == 1:
            return current, step, steps[0] * 1.5
        if step == 0:
            return current, step, (steps[0] + steps[1]) / 2
        return current, step, steps[step]

    if rating is Rating.GOOD:
        if step + 1 == len(steps):
            return graduated
        return current, step + 1, steps[step + 1]

    return graduated  # EASY graduates immediately


def _review_interval(stability: float) -> timedelta:
    """Days until recall is predicted to fall to `DESIRED_RETENTION`.

    Rounded to whole days and floored at 1: an interval is a date, and
    "tomorrow" is the soonest a review can meaningfully be scheduled."""
    days = (stability / _FACTOR) * ((DESIRED_RETENTION ** (1 / _DECAY)) - 1)
    return timedelta(days=min(max(round(days), 1), MAXIMUM_INTERVAL_DAYS))


def _initial_stability(rating: Rating) -> float:
    return _clamp_stability(DEFAULT_PARAMETERS[rating - 1])


def _initial_difficulty(rating: Rating) -> float:
    """Unclamped on purpose: `_next_difficulty`'s mean reversion pulls toward
    this value computed for EASY, and clamping it there would bias the target
    the whole curve reverts to."""
    return DEFAULT_PARAMETERS[4] - math.e ** (DEFAULT_PARAMETERS[5] * (rating - 1)) + 1


def _next_difficulty(difficulty: float, rating: Rating) -> float:
    delta = -(DEFAULT_PARAMETERS[6] * (rating - 3))
    damped = difficulty + (10.0 - difficulty) * delta / 9.0
    reverted = (
        DEFAULT_PARAMETERS[7] * _initial_difficulty(Rating.EASY)
        + (1 - DEFAULT_PARAMETERS[7]) * damped
    )
    return _clamp_difficulty(reverted)


def _next_stability(
    difficulty: float, stability: float, recall_probability: float, rating: Rating
) -> float:
    if rating is Rating.AGAIN:
        return _clamp_stability(
            _forget_stability(difficulty, stability, recall_probability)
        )
    return _clamp_stability(
        _recall_stability(difficulty, stability, recall_probability, rating)
    )


def _recall_stability(
    difficulty: float, stability: float, recall_probability: float, rating: Rating
) -> float:
    hard_penalty = DEFAULT_PARAMETERS[15] if rating is Rating.HARD else 1
    easy_bonus = DEFAULT_PARAMETERS[16] if rating is Rating.EASY else 1
    return stability * (
        1
        + math.e ** DEFAULT_PARAMETERS[8]
        * (11 - difficulty)
        * (stability ** -DEFAULT_PARAMETERS[9])
        * (math.e ** ((1 - recall_probability) * DEFAULT_PARAMETERS[10]) - 1)
        * hard_penalty
        * easy_bonus
    )


def _forget_stability(
    difficulty: float, stability: float, recall_probability: float
) -> float:
    long_term = (
        DEFAULT_PARAMETERS[11]
        * (difficulty ** -DEFAULT_PARAMETERS[12])
        * (((stability + 1) ** DEFAULT_PARAMETERS[13]) - 1)
        * (math.e ** ((1 - recall_probability) * DEFAULT_PARAMETERS[14]))
    )
    short_term = stability / (
        math.e ** (DEFAULT_PARAMETERS[17] * DEFAULT_PARAMETERS[18])
    )
    return min(long_term, short_term)


def _short_term_stability(stability: float, rating: Rating) -> float:
    """Same-day re-review. The increase is floored at 1.0 for anything but
    AGAIN, so answering correctly twice in one session can never *reduce*
    durability."""
    increase = (
        math.e ** (DEFAULT_PARAMETERS[17] * (rating - 3 + DEFAULT_PARAMETERS[18]))
    ) * (stability ** -DEFAULT_PARAMETERS[19])
    if rating is not Rating.AGAIN:
        increase = max(increase, 1.0)
    return _clamp_stability(stability * increase)


def _clamp_stability(stability: float) -> float:
    return max(stability, _STABILITY_MIN)


def _clamp_difficulty(difficulty: float) -> float:
    return min(max(difficulty, _MIN_DIFFICULTY), _MAX_DIFFICULTY)
