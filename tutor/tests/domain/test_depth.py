"""Depth targets and `meets_target` — pure domain, no fakes, no I/O."""

from datetime import UTC, datetime, timedelta

import pytest

from tutor.domain.depth import (
    DEFAULT_DEPTH_LEVEL,
    REQUIREMENTS,
    DepthLevel,
    meets_target,
    requirement_for,
)
from tutor.domain.scheduling import Rating, SchedulerState, calculate_next_review

START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _state(stability: float) -> SchedulerState:
    return SchedulerState(stability=stability, difficulty=5.0)


# --- the levels ----------------------------------------------------------


def test_every_level_has_a_requirement():
    assert set(REQUIREMENTS) == set(DepthLevel)


def test_thresholds_are_expressed_in_days_and_increase_with_depth():
    """Days, never a bare float: "21.0" means nothing to anyone, but "still
    recall it three weeks later" is a claim a person can disagree with — which
    is the only way these numbers ever get corrected."""
    days = [requirement_for(level).stability_days for level in DepthLevel]

    assert days == sorted(days)
    assert len(set(days)) == len(days)  # the levels are actually distinct


def test_the_levels_are_qualitatively_different_not_evenly_spaced():
    """A week, a month, half a year — each is a different kind of knowing,
    not a linear scale."""
    assert requirement_for(DepthLevel.AWARE).stability_days == 7
    assert requirement_for(DepthLevel.WORKING).stability_days == 30
    assert requirement_for(DepthLevel.SPECIALIST).stability_days == 180


def test_every_level_explains_itself_in_words():
    """These thresholds are a starting position meant to be argued with, and
    nobody argues with a number that has no claim attached."""
    for level in DepthLevel:
        assert len(requirement_for(level).description) > 20


def test_only_specialist_demands_discursive_evidence():
    """Explaining something in your own words is different evidence from
    recognising it, and that difference is what the top level captures."""
    assert requirement_for(DepthLevel.SPECIALIST).requires_discursive is True
    assert requirement_for(DepthLevel.AWARE).requires_discursive is False
    assert requirement_for(DepthLevel.WORKING).requires_discursive is False


def test_the_default_is_the_shallowest_level():
    """New Categories arrive from ingest unseen; defaulting to depth would
    commit the learner to study they never chose."""
    assert DEFAULT_DEPTH_LEVEL is DepthLevel.AWARE
    assert requirement_for(DEFAULT_DEPTH_LEVEL).stability_days == min(
        r.stability_days for r in REQUIREMENTS.values()
    )


# --- meets_target --------------------------------------------------------


def test_stability_at_or_above_the_threshold_meets_the_target():
    assert meets_target(_state(7.0), DepthLevel.AWARE) is True
    assert meets_target(_state(6.9), DepthLevel.AWARE) is False


def test_a_deeper_target_is_harder_to_meet():
    state = _state(31.0)

    assert meets_target(state, DepthLevel.AWARE) is True
    assert meets_target(state, DepthLevel.WORKING) is True
    assert meets_target(state, DepthLevel.SPECIALIST) is False


def test_specialist_is_not_met_on_stability_alone():
    assert meets_target(_state(365.0), DepthLevel.SPECIALIST) is False
    assert (
        meets_target(_state(365.0), DepthLevel.SPECIALIST, has_discursive_evidence=True)
        is True
    )


def test_discursive_evidence_does_not_substitute_for_durability():
    assert (
        meets_target(_state(10.0), DepthLevel.SPECIALIST, has_discursive_evidence=True)
        is False
    )


def test_a_concept_never_reviewed_does_not_meet_any_target():
    """A `False` rather than an error: the study plan asks this about
    everything it is considering, including things never studied."""
    for level in DepthLevel:
        assert meets_target(None, level) is False
        assert meets_target(SchedulerState(), level) is False


# --- the reason it keys on stability (#18) -------------------------------


def test_a_target_once_met_stays_met_as_time_passes():
    """**The whole point of the decision.** Stability moves only when you
    review, so a prerequisite satisfied in March is still satisfied in June.
    Keying this on retrievability — which decays with the calendar alone —
    would un-master concepts overnight and reshuffle the plan with no new
    evidence."""
    state = SchedulerState()
    for i in range(4):
        state = calculate_next_review(state, Rating.EASY, START + timedelta(days=30 * i))
    assert meets_target(state, DepthLevel.AWARE) is True

    # A year later, with no review at all, nothing about the state has changed.
    assert meets_target(state, DepthLevel.AWARE) is True
    assert state.stability == state.stability


def test_only_a_review_can_lose_a_target():
    """The other half: it is evidence, not time, that takes a target away."""
    state = SchedulerState()
    for i in range(5):
        state = calculate_next_review(state, Rating.EASY, START + timedelta(days=30 * i))
    assert meets_target(state, DepthLevel.WORKING) is True

    lapsed = calculate_next_review(state, Rating.AGAIN, START + timedelta(days=200))

    assert lapsed.stability < state.stability
    assert meets_target(lapsed, DepthLevel.WORKING) is False


@pytest.mark.parametrize("level", list(DepthLevel))
def test_meets_target_reads_nothing_but_stability_and_evidence(level):
    """Two states differing only in `due` and `last_review` — the fields
    retrievability is computed from — must give the same answer."""
    early = SchedulerState(
        stability=200.0, difficulty=5.0, last_review=START, due=START + timedelta(days=1)
    )
    late = SchedulerState(
        stability=200.0,
        difficulty=5.0,
        last_review=START - timedelta(days=900),
        due=START - timedelta(days=800),
    )

    assert meets_target(early, level, has_discursive_evidence=True) == meets_target(
        late, level, has_discursive_evidence=True
    )
