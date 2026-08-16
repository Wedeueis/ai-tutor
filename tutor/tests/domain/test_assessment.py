"""Rubric rollup and the rating mapping — pure domain, no fakes, no I/O.

The mapping is the thing worth protecting here. It decides what FSRS is told,
and FSRS decides the next month of the learner's schedule; if a model picked it
instead, the schedule would depend on a prompt nobody can diff.
"""

from __future__ import annotations

import pytest

from tutor.domain.assessment import (
    AGAIN_BELOW,
    EASY_FROM,
    HARD_BELOW,
    EvalResult,
    NotGraded,
    Rubric,
    RubricContent,
    RubricScore,
    aggregate_scores,
    rating_for,
    render_grade,
    render_rubrics,
)
from tutor.domain.scheduling import Rating


def _scores(*values: float | None) -> list[RubricScore]:
    return [RubricScore(rubric_id=f"r{i}", score=v) for i, v in enumerate(values)]


# --- the rollup -----------------------------------------------------------


def test_the_average_is_unweighted():
    """Weighting criteria against each other is a pedagogical claim, and there
    is no evidence to make it from yet."""
    result = aggregate_scores(_scores(1.0, 0.0))

    assert result.average_score == 0.5
    assert result.graded


def test_an_unjudged_criterion_is_left_out_rather_than_counted_as_zero():
    """A grader's silence is not the learner's failure."""
    assert aggregate_scores(_scores(1.0, None)).average_score == 1.0


def test_nothing_judged_is_not_the_same_as_judged_badly():
    """The distinction the whole `graded` flag exists for: an empty grading is
    a broken grader, and a 0.0 average is a failed answer."""
    empty = aggregate_scores(_scores(None, None))
    failed = aggregate_scores(_scores(0.0, 0.0))

    assert empty.average_score == failed.average_score == 0.0
    assert not empty.graded
    assert failed.graded


def test_no_scores_at_all_is_not_graded():
    assert not aggregate_scores([]).graded


# --- the mapping ----------------------------------------------------------


@pytest.mark.parametrize(
    ("average", "expected"),
    [
        (0.0, Rating.AGAIN),
        (0.49, Rating.AGAIN),
        (0.5, Rating.HARD),
        (0.74, Rating.HARD),
        (0.75, Rating.GOOD),
        (0.94, Rating.GOOD),
        (0.95, Rating.EASY),
        (1.0, Rating.EASY),
    ],
)
def test_the_bands(average, expected):
    assert rating_for(EvalResult(average_score=average, graded=True)) is expected


def test_the_mapping_is_deterministic_and_takes_nothing_but_the_result():
    """RF4.4: pure, testable without an LLM. No clock, no state, no model."""
    result = aggregate_scores(_scores(0.8, 0.9))

    assert rating_for(result) is rating_for(result) is Rating.GOOD


def test_the_thresholds_are_named_and_ordered():
    """Three constants a person can disagree with, rather than magic numbers
    buried in an if-chain — they are a starting position, not a fitted one."""
    assert 0 < AGAIN_BELOW < HARD_BELOW < EASY_FROM <= 1.0


def test_the_rating_is_monotonic_in_the_score():
    ratings = [
        rating_for(EvalResult(average_score=n / 20, graded=True)) for n in range(21)
    ]

    assert ratings == sorted(ratings)


def test_an_ungraded_result_refuses_rather_than_recording_a_lapse():
    """`AGAIN` here would write a failure the learner never had into an
    append-only log, and FSRS would then shorten every later interval on that
    evidence. A review that could not be graded must not become an event."""
    with pytest.raises(NotGraded):
        rating_for(aggregate_scores([]))


# --- what gets written into the event -------------------------------------


def test_rubrics_render_as_text_because_there_is_nothing_left_to_point_at():
    """The rubric was generated for one exchange and discarded (RF4.3), so the
    event stores the text or loses it."""
    rendered = render_rubrics(
        [
            Rubric("mechanism", RubricContent("Names the mechanism.")),
            Rubric("limits", RubricContent("Says when it fails.")),
        ]
    )

    assert rendered == "- mechanism: Names the mechanism.\n- limits: Says when it fails."


def test_the_grade_records_the_rollup_and_every_reason():
    """What a person would need to see, years later, to decide the grade was
    unfair."""
    rendered = render_grade(
        aggregate_scores(
            [
                RubricScore("mechanism", 1.0, "named it exactly"),
                RubricScore("limits", 0.0, "did not mention failure modes"),
                RubricScore("nuance", None),
            ]
        )
    )

    assert "average 0.50" in rendered
    assert "mechanism: 1.00 — named it exactly" in rendered
    assert "nuance: unjudged" in rendered
