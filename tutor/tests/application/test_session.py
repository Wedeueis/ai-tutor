"""Filling one session from the study plan.

Every plan here is built by `project` rather than hand-assembled, so these
tests fail if the plan's own ordering changes underneath them — the session is
a prefix of the plan, and that relationship is the thing worth protecting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tutor.application.ports.outbound.vault import Edge
from tutor.application.session import DEFAULT_SESSION_SIZE, compose_session
from tutor.application.study_plan import ConceptStatus, WorkKind, project
from tutor.domain.scheduling import SchedulerState

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def _requires(*pairs: tuple[str, str]) -> list[Edge]:
    return [Edge(from_id=a, to_id=b, relation_type="requires") for a, b in pairs]


def _reviewed(due: datetime) -> SchedulerState:
    """Reviewed once and still well under `aware`'s seven days, so the concept
    is under target and the test is about *when* it is due."""
    return SchedulerState(
        stability=1.0, difficulty=5.0, due=due, last_review=NOW - timedelta(days=2)
    )


def _ids(session) -> list[str]:
    return [item.concept_id for item in session]


# --- what fills a session -------------------------------------------------


def test_due_and_under_target_comes_before_anything_else():
    """RF3.4's ordering, and the accept criterion for this task."""
    statuses = {
        "overdue": ConceptStatus("overdue", state=_reviewed(NOW - timedelta(days=5))),
        "not-yet-due": ConceptStatus(
            "not-yet-due", state=_reviewed(NOW + timedelta(days=5))
        ),
    }
    plan = project(
        "goal",
        _requires(("goal", "overdue"), ("goal", "not-yet-due")),
        statuses,
        now=NOW,
    )

    session = compose_session(plan, size=3, now=NOW)

    assert _ids(session)[0] == "overdue"


def test_strengthening_comes_before_new_ground():
    statuses = {"known": ConceptStatus("known", state=_reviewed(NOW + timedelta(days=5)))}
    plan = project(
        "goal", _requires(("goal", "known"), ("goal", "new")), statuses, now=NOW
    )

    session = compose_session(plan, size=2, now=NOW)

    assert _ids(session) == ["known", "new"]


def test_the_three_bands_in_order():
    statuses = {
        "due": ConceptStatus("due", state=_reviewed(NOW - timedelta(days=1))),
        "later": ConceptStatus("later", state=_reviewed(NOW + timedelta(days=30))),
    }
    plan = project(
        "goal",
        _requires(("goal", "due"), ("goal", "later"), ("goal", "unseen")),
        statuses,
        now=NOW,
    )

    session = compose_session(plan, size=4, now=NOW)

    assert _ids(session)[:3] == ["due", "later", "unseen"]


def test_due_exactly_now_counts_as_due():
    statuses = {"x": ConceptStatus("x", state=_reviewed(NOW))}
    plan = project("goal", _requires(("goal", "x")), statuses, now=NOW)

    assert compose_session(plan, now=NOW).items[0].concept_id == "x"


def test_never_reviewed_is_new_ground_not_overdue_work():
    """"Never studied" is a different claim from "you were supposed to review
    this in March", and the session must not conflate them."""
    plan = project("goal", _requires(("goal", "unseen")), {}, now=NOW)

    session = compose_session(plan, now=NOW)

    assert all(item.kind is WorkKind.EXPLORE for item in session)
    assert session.exploit == ()


# --- size -----------------------------------------------------------------


def test_a_session_is_a_prefix_of_the_plans_own_order_within_each_band():
    plan = project(
        "goal",
        _requires(("goal", "a"), ("goal", "b"), ("goal", "c"), ("goal", "d")),
        {},
        now=NOW,
    )

    session = compose_session(plan, size=2, now=NOW)

    assert _ids(session) == _ids(plan.actionable())[:2]


def test_a_short_plan_is_not_padded():
    plan = project("goal", [], {}, now=NOW)

    assert len(compose_session(plan, size=DEFAULT_SESSION_SIZE, now=NOW)) == 1


def test_a_plan_with_nothing_to_do_gives_an_empty_session():
    """Everything at target: the honest answer is that there is nothing to
    study, not a session padded with work that is already done."""
    done = SchedulerState(stability=500.0, difficulty=5.0, last_review=NOW)
    plan = project("goal", [], {"goal": ConceptStatus("goal", state=done)}, now=NOW)

    session = compose_session(plan, now=NOW)

    assert len(session) == 0
    assert session.goal_id == "goal"


# --- blocked work ---------------------------------------------------------


def test_blocked_concepts_are_left_out():
    """They stay in the *plan* — they are what the work is for — but a concept
    whose prerequisites are unmet is not something to sit down and do today."""
    plan = project(
        "attention", _requires(("attention", "softmax")), {}, now=NOW
    )

    session = compose_session(plan, now=NOW)

    assert _ids(plan) == ["softmax", "attention"]
    assert _ids(session) == ["softmax"]


# --- no knob --------------------------------------------------------------


def test_the_mix_is_derived_and_there_is_no_ratio_to_set():
    """RF3.4 has no ratio knob, and #21 is deferred precisely so one does not
    appear here. The only number a caller may pass is a size."""
    import inspect

    parameters = set(inspect.signature(compose_session).parameters)

    assert parameters == {"plan", "size", "now"}


def test_the_composition_is_frozen_at_composition_time():
    """RF2.7: a session is a value, not a live view. Reviews inside it change
    FSRS state, and a session that re-derived itself would reorder under the
    learner's feet — mastery changes surface in the *next* session."""
    plan = project(
        "goal", _requires(("goal", "a"), ("goal", "b")), {}, now=NOW
    )
    session = compose_session(plan, now=NOW)

    later = project(
        "goal",
        _requires(("goal", "a"), ("goal", "b")),
        {"a": ConceptStatus("a", state=SchedulerState(stability=500.0, last_review=NOW))},
        now=NOW,
    )

    assert _ids(session) == ["a", "b"]
    assert _ids(later) == ["b", "goal"]  # the next session would differ
    assert _ids(session) == ["a", "b"]  # this one did not move
