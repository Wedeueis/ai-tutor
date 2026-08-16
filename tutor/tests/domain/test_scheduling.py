"""FSRS-6, checked against the reference implementation.

**The differential test is the point of this file** (RF4.2). FSRS's 21 weights
are fitted, not derived, and its stability update is a product of four
exponentials — nobody can review that by reasoning. The only way to know our
implementation is right is to run the same review sequence through `fsrs` and
compare. `fsrs` is dev-only (`tests/test_boundary.py` enforces it); a runtime
dependency would make the oracle and the subject the same code.

Sequences matter more than single steps here: stability compounds, so a
formula wrong in the second decimal agrees on review one and diverges by
review five.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Card, Scheduler
from fsrs import Rating as ReferenceRating

from tutor.domain.scheduling import (
    ALGORITHM,
    DEFAULT_PARAMETERS,
    PARAMETERS_ID,
    Rating,
    SchedulerState,
    State,
    calculate_next_review,
    retrievability,
)

START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

_REFERENCE_RATING = {
    Rating.AGAIN: ReferenceRating.Again,
    Rating.HARD: ReferenceRating.Hard,
    Rating.GOOD: ReferenceRating.Good,
    Rating.EASY: ReferenceRating.Easy,
}


def _reference_scheduler() -> Scheduler:
    # Fuzzing off: it is the one source of randomness in the reference, and the
    # thing this implementation deliberately does not have.
    return Scheduler(parameters=DEFAULT_PARAMETERS, enable_fuzzing=False)


def _run_both(reviews: list[tuple[Rating, timedelta]]):
    """The same review sequence through both implementations."""
    scheduler = _reference_scheduler()
    card = Card()
    state = SchedulerState()

    for rating, offset in reviews:
        at = START + offset
        card, _ = scheduler.review_card(card, _REFERENCE_RATING[rating], at)
        state = calculate_next_review(state, rating, at)

    return state, card


def _assert_matches(state: SchedulerState, card: Card) -> None:
    assert state.stability == pytest.approx(card.stability, rel=1e-9)
    assert state.difficulty == pytest.approx(card.difficulty, rel=1e-9)
    assert state.due == card.due
    assert state.last_review == card.last_review
    assert int(state.state) == int(card.state)


# --- the differential test ----------------------------------------------


@pytest.mark.parametrize("rating", list(Rating))
def test_a_first_review_matches_the_reference(rating):
    _assert_matches(*_run_both([(rating, timedelta())]))


@pytest.mark.parametrize(
    "sequence",
    [
        pytest.param([Rating.GOOD, Rating.GOOD, Rating.GOOD], id="steady-good"),
        pytest.param([Rating.EASY, Rating.EASY, Rating.EASY], id="always-easy"),
        pytest.param([Rating.AGAIN, Rating.AGAIN, Rating.AGAIN], id="always-again"),
        pytest.param([Rating.HARD, Rating.HARD, Rating.HARD], id="always-hard"),
        pytest.param(
            [Rating.GOOD, Rating.GOOD, Rating.AGAIN, Rating.GOOD, Rating.GOOD],
            id="lapse-then-recover",
        ),
        pytest.param(
            [Rating.EASY, Rating.AGAIN, Rating.HARD, Rating.GOOD, Rating.EASY, Rating.AGAIN],
            id="erratic",
        ),
        pytest.param([Rating.GOOD] * 12, id="long-run"),
    ],
)
def test_a_review_sequence_matches_the_reference(sequence):
    """Spaced a week apart, so each review runs the long-term path."""
    reviews = [(rating, timedelta(days=7 * i)) for i, rating in enumerate(sequence)]

    _assert_matches(*_run_both(reviews))


def test_same_day_re_reviews_match_the_reference():
    """The short-term branch: elapsed < 1 day takes a different formula
    entirely, and a session that quizzes a concept twice hits it."""
    reviews = [
        (Rating.AGAIN, timedelta()),
        (Rating.GOOD, timedelta(minutes=2)),
        (Rating.GOOD, timedelta(minutes=20)),
        (Rating.GOOD, timedelta(days=3)),
    ]

    _assert_matches(*_run_both(reviews))


def test_a_long_gap_matches_the_reference():
    """Two years between reviews — retrievability near zero, which is where
    the forgetting curve's exponent matters most."""
    reviews = [
        (Rating.GOOD, timedelta()),
        (Rating.GOOD, timedelta(days=1)),
        (Rating.HARD, timedelta(days=730)),
    ]

    _assert_matches(*_run_both(reviews))


def test_retrievability_matches_the_reference():
    scheduler = _reference_scheduler()
    card = Card()
    card, _ = scheduler.review_card(card, ReferenceRating.Good, START)
    state = calculate_next_review(SchedulerState(), Rating.GOOD, START)

    for days in (0, 1, 7, 30, 365):
        at = START + timedelta(days=days)
        assert retrievability(state, at) == pytest.approx(
            scheduler.get_card_retrievability(card, at), rel=1e-9
        )


# --- properties the reference does not give us --------------------------


def test_scheduling_is_deterministic():
    """No fuzzing, and no switch for it. `replay` must rebuild the same
    projection every time, and two concepts due the same day must order the
    same way on every run (RF4.1)."""
    reviews = [(Rating.GOOD, timedelta(days=7 * i)) for i in range(6)]

    first, _ = _run_both(reviews)
    second, _ = _run_both(reviews)

    assert first == second


def test_a_first_review_needs_no_prior_state():
    """`SqliteLearnerStore` starts a replay from an empty `SchedulerState()`."""
    state = calculate_next_review(SchedulerState(), Rating.GOOD, START)

    assert state.stability is not None
    assert state.last_review == START


def test_the_timestamp_changes_the_outcome():
    """Why `reviewed_at` is required rather than optional: the same rating
    means different things a day and a year later."""
    after_one = calculate_next_review(SchedulerState(), Rating.GOOD, START)

    soon = calculate_next_review(after_one, Rating.GOOD, START + timedelta(days=1))
    late = calculate_next_review(after_one, Rating.GOOD, START + timedelta(days=365))

    assert soon.stability != late.stability


def test_recall_increases_stability_and_a_lapse_reduces_it():
    """The one property worth asserting in plain terms, because everything
    else here is checked by comparison rather than by reading."""
    learned = calculate_next_review(SchedulerState(), Rating.GOOD, START)
    learned = calculate_next_review(learned, Rating.GOOD, START + timedelta(days=1))

    recalled = calculate_next_review(learned, Rating.GOOD, START + timedelta(days=10))
    lapsed = calculate_next_review(learned, Rating.AGAIN, START + timedelta(days=10))

    assert recalled.stability > learned.stability
    assert lapsed.stability < learned.stability


def test_a_lapse_from_review_drops_into_relearning():
    state = calculate_next_review(SchedulerState(), Rating.EASY, START)
    assert state.state is State.REVIEW

    lapsed = calculate_next_review(state, Rating.AGAIN, START + timedelta(days=5))

    assert lapsed.state is State.RELEARNING


def test_the_review_interval_is_at_least_one_day():
    """An interval is a date: "tomorrow" is the soonest a review can be
    scheduled, however low stability falls."""
    state = SchedulerState()
    for i in range(4):
        state = calculate_next_review(state, Rating.AGAIN, START + timedelta(days=i))

    graduated = calculate_next_review(state, Rating.HARD, START + timedelta(days=10))
    if graduated.state is State.REVIEW:
        assert graduated.due - graduated.last_review >= timedelta(days=1)


# --- the identity that makes checkpoints verifiable ----------------------


def test_the_algorithm_and_parameter_set_are_named():
    """A checkpoint is valid only for the exact pair that produced it (§7), so
    both have to be recordable strings rather than implicit."""
    assert ALGORITHM == "fsrs-6"
    assert PARAMETERS_ID
    assert len(DEFAULT_PARAMETERS) == 21
