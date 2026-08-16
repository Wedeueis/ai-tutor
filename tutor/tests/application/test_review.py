"""One review, end to end.

Driven against a real `SqliteLearnerStore` — the append-only log is the point
of this task, and a fake store would let the test pass while the thing that
must be durable was not written. Only the model is faked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.vault import Concept, ConceptMatch, Edge
from tutor.application.review import SELF_REPORTED, ConductReview
from tutor.domain.assessment import NotGraded, Rubric, RubricContent, RubricScore
from tutor.domain.depth import DepthLevel
from tutor.domain.scheduling import (
    ALGORITHM,
    PARAMETERS_ID,
    Rating,
    calculate_next_review,
)

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeVault:
    def __init__(self, body: str = "Attention weights every token.") -> None:
        self.body = body
        self.reads: list[str] = []

    async def get_concept(self, concept_id: str) -> Concept:
        self.reads.append(concept_id)
        return Concept(concept_id=concept_id, title="Attention", body=self.body)

    async def search(self, query: str, k: int = 5) -> list[ConceptMatch]:
        return []

    async def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        return []


class FakeAssessments:
    """Records what it was shown, and returns whatever it was told to."""

    def __init__(self, scores: list[RubricScore] | None = None) -> None:
        self.scores = scores if scores is not None else [RubricScore("r1", 1.0)]
        self.saw_body: str | None = None
        self.saw_level: DepthLevel | None = None
        self.graded: list[tuple[Assessment, str]] = []

    async def generate(self, concept: Concept, level: DepthLevel) -> Assessment:
        self.saw_body = concept.body
        self.saw_level = level
        return Assessment(
            concept_id=concept.concept_id,
            question=f"What does {concept.title} do?",
            rubrics=[Rubric("r1", RubricContent("Names the mechanism."))],
        )

    async def grade(self, assessment: Assessment, answer: str) -> list[RubricScore]:
        self.graded.append((assessment, answer))
        return self.scores


@pytest.fixture
def store(tmp_path):
    learner_store = SqliteLearnerStore(
        tmp_path / "learner.db", calculate_next_review, ALGORITHM, PARAMETERS_ID
    )
    yield learner_store
    learner_store.close()


def _review(store, assessments=None, vault=None) -> ConductReview:
    return ConductReview(
        vault or FakeVault(), store, assessments or FakeAssessments()
    )


# --- generating the question ----------------------------------------------


@pytest.mark.anyio
async def test_the_question_comes_from_the_concepts_current_content(store):
    """RF4.3's accept criterion. The vault is re-read every time rather than
    cached: `pipeline` rewrites concepts as it ingests, so a cached question
    can end up asking about text that no longer exists."""
    vault = FakeVault(body="First version.")
    assessments = FakeAssessments()
    review = _review(store, assessments, vault)

    await review.ask("attention")
    assert assessments.saw_body == "First version."

    vault.body = "Rewritten after more ingest."
    await review.ask("attention")

    assert assessments.saw_body == "Rewritten after more ingest."
    assert vault.reads == ["attention", "attention"]


@pytest.mark.anyio
async def test_the_depth_target_reaches_the_question(store):
    """`aware` asks whether the learner recognises it; `specialist` asks them
    to explain it. The levels differ in what is asked, not only in their
    stability thresholds."""
    assessments = FakeAssessments()

    await _review(store, assessments).ask("attention", DepthLevel.SPECIALIST)

    assert assessments.saw_level is DepthLevel.SPECIALIST


# --- recording a graded answer --------------------------------------------


@pytest.mark.anyio
async def test_a_graded_answer_appends_exactly_one_event(store):
    review = _review(store)
    assessment = await review.ask("attention")

    await review.record(assessment, "It weights every token.", reviewed_at=NOW)

    events = store.events("attention")
    assert len(events) == 1
    assert events[0].rating is Rating.EASY


@pytest.mark.anyio
async def test_the_event_carries_the_whole_exchange_as_text(store):
    """Not pointers: the assessment is discarded, and the concept and rubric
    will be rewritten or deleted. A row has to stay interpretable on its own."""
    review = _review(store)
    assessment = await review.ask("attention")

    await review.record(assessment, "It weights every token.", reviewed_at=NOW)

    event = store.events("attention")[0]
    assert event.question == "What does Attention do?"
    assert "Names the mechanism." in event.rubric
    assert event.answer == "It weights every token."
    assert "average 1.00" in event.grade


@pytest.mark.anyio
async def test_a_graded_answer_is_marked_discursive(store):
    """The evidence `specialist` asks for, and what `StudyPlanner` reads off
    the log (RF4.4)."""
    review = _review(store)
    assessment = await review.ask("attention")

    await review.record(assessment, "an answer", reviewed_at=NOW)

    assert store.events("attention")[0].discursive
    assert store.has_discursive_evidence("attention")


@pytest.mark.anyio
async def test_the_rating_comes_from_the_rollup_not_from_the_model(store):
    """The model returned scores and no verdict; the band did the rest."""
    assessments = FakeAssessments([RubricScore("r1", 0.6), RubricScore("r2", 0.6)])
    review = _review(store, assessments)
    assessment = await review.ask("attention")

    await review.record(assessment, "partial", reviewed_at=NOW)

    assert store.events("attention")[0].rating is Rating.HARD


@pytest.mark.anyio
async def test_the_scheduling_identity_is_recorded_on_the_event(store):
    """A checkpoint is valid only for the pair that produced it (§7), so the
    pair has to be on the event."""
    review = _review(store)
    assessment = await review.ask("attention")

    event = await review.record(assessment, "an answer", reviewed_at=NOW)

    assert (event.algorithm, event.parameters) == (ALGORITHM, PARAMETERS_ID)


@pytest.mark.anyio
async def test_a_review_moves_the_schedule(store):
    """End to end: the event lands, the projection advances, and the concept
    gets a due date it did not have."""
    review = _review(store)
    assessment = await review.ask("attention")
    assert store.scheduler_state("attention") is None

    await review.record(assessment, "an answer", reviewed_at=NOW)

    state = store.scheduler_state("attention")
    assert state is not None and state.due is not None and state.stability is not None


# --- a grading that failed ------------------------------------------------


@pytest.mark.anyio
async def test_an_ungradable_answer_writes_nothing_at_all(store):
    """A grader that scored nothing is broken. Recording `AGAIN` would put a
    lapse the learner never had into an append-only log, and FSRS would shorten
    every later interval on that evidence."""
    assessments = FakeAssessments([RubricScore("r1", None)])
    review = _review(store, assessments)
    assessment = await review.ask("attention")

    with pytest.raises(NotGraded):
        await review.record(assessment, "an answer", reviewed_at=NOW)

    assert store.events("attention") == []


# --- self-reported recall -------------------------------------------------


def test_a_self_report_is_not_discursive_however_honest_it_is(store):
    """No rubric judged it, so it cannot be the evidence `specialist` asks
    for."""
    _review(store).self_report("attention", Rating.EASY, reviewed_at=NOW)

    event = store.events("attention")[0]
    assert not event.discursive
    assert not store.has_discursive_evidence("attention")


def test_a_self_report_still_says_how_it_was_graded(store):
    """A row whose `rubric` field is empty is a row nobody can interpret
    later."""
    _review(store).self_report("attention", Rating.HARD, reviewed_at=NOW)

    event = store.events("attention")[0]
    assert event.rubric == SELF_REPORTED
    assert event.grade == "self-reported hard"


def test_both_kinds_of_review_share_one_log_and_one_scheduler(store):
    """The log does not have two shapes: a self-report and a graded answer are
    the same kind of row, differing in evidence."""
    review = _review(store)
    review.self_report("attention", Rating.GOOD, reviewed_at=NOW)
    review.self_report("attention", Rating.GOOD, reviewed_at=NOW + timedelta(days=3))

    assert len(store.events("attention")) == 2
    assert store.scheduler_state("attention") is not None


# --- nothing pedagogical persists -----------------------------------------


def test_nothing_is_stored_but_events_targets_and_projections(store):
    """RF4.3: no assessment items, no cards, no rubric table. The item's only
    trace is the text on the event."""
    tables = {
        row["name"]
        for row in store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert tables <= {
        "review_events",
        "depth_targets",
        "scheduler_state",
        "checkpoints",
        "sqlite_sequence",
    }
