"""`learner.db`: the append-only log, and the projections rebuilt from it.

The scheduler is injected, so these tests use a trivial counting one — what is
under test here is persistence, replay, and checkpoint validity, none of which
should depend on FSRS's actual arithmetic (that is Task 2.1's differential
test against `fsrs`)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.domain.depth import DepthLevel
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import Rating, SchedulerState, State

ALGORITHM = "fsrs-6"
PARAMETERS = "default"


def counting_scheduler(
    state: SchedulerState, rating: Rating, reviewed_at: datetime
) -> SchedulerState:
    """Stand-in for `calculate_next_review`. Order-sensitive and cumulative, so
    a replay that drops, repeats or reorders an event produces a different
    number — which is what these tests need to be able to see."""
    stability = (state.stability or 0.0) * 2 + float(rating)
    return SchedulerState(
        stability=stability,
        difficulty=(state.difficulty or 0.0) + 1,
        due=reviewed_at + timedelta(days=stability),
        last_review=reviewed_at,
        state=State.REVIEW,
        step=state.step + 1,
    )


def _store(tmp_path, scheduler=counting_scheduler, algorithm=ALGORITHM, parameters=PARAMETERS):
    return SqliteLearnerStore(
        tmp_path / "learner.db", scheduler, algorithm=algorithm, parameters=parameters
    )


def _event(concept_id="attention", rating=Rating.GOOD, day=1, **overrides) -> ReviewEvent:
    defaults = dict(
        concept_id=concept_id,
        rating=rating,
        reviewed_at=datetime(2026, 1, day, 12, 0, tzinfo=UTC),
        algorithm=ALGORITHM,
        parameters=PARAMETERS,
        question="What does scaled dot-product attention divide by?",
        rubric="Names sqrt(d_k) and says why.",
        answer="By the square root of the key dimension.",
        grade="correct",
    )
    return ReviewEvent(**{**defaults, **overrides})


# --- the log is append-only ----------------------------------------------


def test_events_round_trip_with_the_full_exchange_intact(tmp_path):
    """A row has to stay independently interpretable years later, after the
    concept has been rewritten and the rubric file has moved."""
    store = _store(tmp_path)
    event = _event(discursive=True)

    store.append_review(event)

    assert store.events("attention") == [event]


def test_updating_a_review_event_is_refused_by_the_database(tmp_path):
    """Not merely "the store exposes no update method" — the log is the one
    thing here that cannot be regenerated, so a stray UPDATE from a migration
    script or a sqlite3 prompt has to fail too."""
    store = _store(tmp_path)
    store.append_review(_event())

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store._connection.execute("UPDATE review_events SET rating = 1")


def test_deleting_a_review_event_is_refused_by_the_database(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event())

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store._connection.execute("DELETE FROM review_events")


def test_events_are_returned_oldest_first(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(day=3, answer="third"))
    store.append_review(_event(day=1, answer="first"))

    # Insertion order, not timestamp order: the log records what happened when
    # it was recorded, and replay follows it.
    assert [e.answer for e in store.events("attention")] == ["third", "first"]


# --- projections ---------------------------------------------------------


def test_a_never_reviewed_concept_has_no_scheduler_state(tmp_path):
    assert _store(tmp_path).scheduler_state("attention") is None


def test_the_projection_is_built_from_the_log_on_read(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(rating=Rating.GOOD, day=1))

    state = store.scheduler_state("attention")

    assert state == counting_scheduler(SchedulerState(), Rating.GOOD, _event().reviewed_at)


def test_successive_events_accumulate_in_order(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(rating=Rating.GOOD, day=1))
    store.append_review(_event(rating=Rating.EASY, day=2))

    # 0*2+3 = 3, then 3*2+4 = 10. A dropped or reordered event gives a
    # different number.
    assert store.scheduler_state("attention").stability == 10.0
    assert store.scheduler_state("attention").step == 2


def test_a_second_read_does_not_reapply_events_already_folded_in(tmp_path):
    """The checkpoint exists so a read is not a full replay; if it were
    ignored, the cumulative scheduler above would keep doubling."""
    store = _store(tmp_path)
    store.append_review(_event(day=1))

    first = store.scheduler_state("attention")
    second = store.scheduler_state("attention")

    assert first == second


def test_an_event_appended_after_a_read_is_picked_up_by_the_next_one(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(rating=Rating.GOOD, day=1))
    store.scheduler_state("attention")

    store.append_review(_event(rating=Rating.EASY, day=2))

    assert store.scheduler_state("attention").stability == 10.0


def test_concepts_do_not_share_a_projection(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(concept_id="attention", rating=Rating.GOOD))
    store.append_review(_event(concept_id="embeddings", rating=Rating.EASY))

    assert store.scheduler_state("attention").stability == 3.0
    assert store.scheduler_state("embeddings").stability == 4.0


# --- replay --------------------------------------------------------------


def test_replay_rebuilds_a_discarded_projection_exactly(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(rating=Rating.GOOD, day=1))
    store.append_review(_event(rating=Rating.EASY, day=2))
    expected = store.scheduler_state("attention")

    store._connection.execute("DELETE FROM scheduler_state")
    store._connection.execute("DELETE FROM checkpoints")
    store._connection.commit()
    store.replay("attention")

    assert store.scheduler_state("attention") == expected


def test_replay_without_a_concept_rebuilds_every_reviewed_concept(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event(concept_id="attention", rating=Rating.GOOD))
    store.append_review(_event(concept_id="embeddings", rating=Rating.EASY))

    store._connection.execute("DELETE FROM scheduler_state")
    store._connection.commit()
    store.replay()

    assert store.scheduler_state("attention").stability == 3.0
    assert store.scheduler_state("embeddings").stability == 4.0


# --- checkpoint validity: the load-bearing rule (PRD v3 §7) --------------


def test_a_checkpoint_from_different_parameters_is_rejected_and_forces_a_replay(tmp_path):
    """Stale-checkpoint reuse after a parameter re-fit silently corrupts
    scheduling — nothing raises, the intervals are simply wrong from then on.
    So validity is checked before use, and a mismatch replays from the first
    event rather than resuming."""
    first = _store(tmp_path, parameters="default")
    first.append_review(_event(rating=Rating.GOOD, day=1))
    first.append_review(_event(rating=Rating.EASY, day=2))
    assert first.scheduler_state("attention").stability == 10.0
    first.close()

    # Same log, same algorithm, re-fitted parameters, and a scheduler that
    # behaves differently under them.
    def refitted(state, rating, reviewed_at):
        return SchedulerState(
            stability=(state.stability or 0.0) + float(rating),
            difficulty=(state.difficulty or 0.0) + 1,
            due=reviewed_at,
            last_review=reviewed_at,
            state=State.REVIEW,
            step=state.step + 1,
        )

    second = _store(tmp_path, scheduler=refitted, parameters="refitted-2026-02")

    # 3 + 4 = 7 under a full replay. Resuming from the stale checkpoint would
    # have given 10 + 4 = 14, with nothing to signal the error.
    assert second.scheduler_state("attention").stability == 7.0


def test_a_checkpoint_from_a_different_algorithm_is_rejected(tmp_path):
    first = _store(tmp_path, algorithm="fsrs-6")
    first.append_review(_event(rating=Rating.GOOD, day=1))
    first.scheduler_state("attention")
    first.close()

    second = _store(tmp_path, algorithm="sm-2")
    second.append_review(_event(rating=Rating.EASY, day=2))

    # Full replay: 0*2+3 = 3, then 3*2+4 = 10.
    assert second.scheduler_state("attention").stability == 10.0
    checkpoint = second._connection.execute(
        "SELECT algorithm FROM checkpoints WHERE concept_id = 'attention'"
    ).fetchone()
    assert checkpoint["algorithm"] == "sm-2"


def test_a_valid_checkpoint_records_the_identity_that_produced_it(tmp_path):
    store = _store(tmp_path)
    store.append_review(_event())
    store.scheduler_state("attention")

    row = store._connection.execute("SELECT * FROM checkpoints").fetchone()

    assert (row["algorithm"], row["parameters"]) == (ALGORITHM, PARAMETERS)
    assert row["last_event_id"] == 1


# --- depth targets -------------------------------------------------------


def test_an_untargeted_category_defaults_to_aware(tmp_path):
    """New Categories arrive from ingest unseen; defaulting to depth would
    commit the learner to study they never chose."""
    assert _store(tmp_path).depth_target("categories/graphrag") is DepthLevel.AWARE


def test_a_depth_target_round_trips(tmp_path):
    store = _store(tmp_path)

    store.set_depth_target("categories/graphrag", DepthLevel.SPECIALIST)

    assert store.depth_target("categories/graphrag") is DepthLevel.SPECIALIST


def test_setting_a_depth_target_again_replaces_it(tmp_path):
    store = _store(tmp_path)
    store.set_depth_target("categories/graphrag", DepthLevel.SPECIALIST)

    store.set_depth_target("categories/graphrag", DepthLevel.WORKING)

    assert store.depth_target("categories/graphrag") is DepthLevel.WORKING


def test_an_unreadable_depth_level_falls_back_rather_than_breaking_the_plan(tmp_path):
    """A level written by a future version, or by hand. One bad row must not
    make the whole study plan unbuildable."""
    store = _store(tmp_path)
    store._connection.execute(
        "INSERT INTO depth_targets (category_id, level) VALUES ('categories/x', 'guru')"
    )
    store._connection.commit()

    assert store.depth_target("categories/x") is DepthLevel.AWARE


def test_depth_targets_survive_a_replay(tmp_path):
    """They are the only authoritative state here that is not an event, and
    the only thing replay cannot rebuild — so replay must not touch them."""
    store = _store(tmp_path)
    store.set_depth_target("categories/graphrag", DepthLevel.SPECIALIST)
    store.append_review(_event())

    store.replay()

    assert store.depth_target("categories/graphrag") is DepthLevel.SPECIALIST
