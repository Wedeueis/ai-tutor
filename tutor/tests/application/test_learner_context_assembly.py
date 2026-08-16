"""Assembling the volatile tier from the store.

Driven against a real `SqliteLearnerStore`: the whole question here is what the
log says about a concept, and a fake store would just be restating the answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.application.learner_context import context_for
from tutor.application.ports.outbound.vault import Concept
from tutor.domain.depth import DepthLevel
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import (
    ALGORITHM,
    PARAMETERS_ID,
    Rating,
    calculate_next_review,
)

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    learner_store = SqliteLearnerStore(
        tmp_path / "learner.db", calculate_next_review, ALGORITHM, PARAMETERS_ID
    )
    yield learner_store
    learner_store.close()


def _review(store, concept_id: str, rating: Rating, at: datetime) -> None:
    store.append_review(
        ReviewEvent(
            concept_id=concept_id,
            rating=rating,
            reviewed_at=at,
            algorithm=ALGORITHM,
            parameters=PARAMETERS_ID,
            question="q",
            rubric="r",
            answer="a",
            grade="g",
        )
    )


def test_a_concept_never_reviewed_has_an_empty_context(store):
    context = context_for(Concept(concept_id="attention"), store)

    assert context.is_first_meeting
    assert context.last_reviewed_at is None
    assert context.depth_target is DepthLevel.AWARE


def test_the_context_counts_reviews_and_takes_the_latest(store):
    _review(store, "attention", Rating.AGAIN, NOW - timedelta(days=90))
    _review(store, "attention", Rating.GOOD, NOW - timedelta(days=30))
    _review(store, "attention", Rating.HARD, NOW - timedelta(days=5))

    context = context_for(Concept(concept_id="attention"), store)

    assert context.times_seen == 3
    assert context.last_rating is Rating.HARD
    assert context.last_reviewed_at == NOW - timedelta(days=5)


def test_another_concepts_history_does_not_leak_in(store):
    _review(store, "other", Rating.EASY, NOW)

    assert context_for(Concept(concept_id="attention"), store).is_first_meeting


def test_the_deepest_target_among_the_concepts_categories_wins(store):
    """Same rule the study plan uses, and for the same reason: adding a broad
    Category must not quietly lower what is asked of a concept."""
    store.set_depth_target("categories/graphrag", DepthLevel.SPECIALIST)
    store.set_depth_target("categories/ml", DepthLevel.AWARE)
    concept = Concept(
        concept_id="graphrag", categories=["categories/ml", "categories/graphrag"]
    )

    assert context_for(concept, store).depth_target is DepthLevel.SPECIALIST


def test_the_context_carries_no_scheduler_state(store):
    """`ReviewSummary` and `SchedulerState` are separate types on purpose — one
    field on a shared object is all it would take for stability to arrive in a
    prompt because it happened to be in scope (#39)."""
    _review(store, "attention", Rating.GOOD, NOW - timedelta(days=5))

    context = context_for(Concept(concept_id="attention"), store)

    assert not hasattr(context, "stability")
    assert not hasattr(context, "difficulty")
    assert not hasattr(context, "due")


def test_the_summary_reads_the_log_not_the_projection(store):
    """`scheduler_state` would have been the shortcut, and it carries exactly
    the fields that must never reach a model."""
    _review(store, "attention", Rating.EASY, NOW - timedelta(days=5))

    summary = store.review_summary("attention")

    assert (summary.times_seen, summary.last_rating) == (1, Rating.EASY)
    assert not hasattr(summary, "stability")


def test_an_unreviewed_summary_is_empty_rather_than_an_error(store):
    summary = store.review_summary("never-seen")

    assert summary.times_seen == 0
    assert summary.last_rating is None
    assert summary.last_reviewed_at is None
