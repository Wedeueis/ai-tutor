"""The session loop.

Every decision in #39 that could break silently is asserted here. The store and
the scheduler are real — the queue's behaviour depends on what FSRS actually
does to a due date, and a fake would just be restating the expectation. Only
the model and the learner are faked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.teaching_turn import Answer
from tutor.application.ports.outbound.vault import Concept, ConceptMatch, Edge
from tutor.application.review import ConductReview
from tutor.application.teaching import (
    DEFAULT_VISIT_CAP,
    REQUEUE_WITHIN,
    SessionReport,
    TeachSession,
    _Queue,
    due_seed,
)
from tutor.domain.assessment import Rubric, RubricContent, RubricScore
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
def anyio_backend():
    return "asyncio"


# --- the queue, in isolation ----------------------------------------------


def test_the_queue_hands_concepts_out_in_order():
    queue = _Queue(pending=["a", "b"])

    assert [queue.take(), queue.take(), queue.take()] == ["a", "b", None]


def test_a_requeued_concept_goes_to_the_back():
    """Spaced by the rest of the work rather than asked again immediately —
    the loop does not sleep out the ten minutes, it approximates them."""
    queue = _Queue(pending=["a", "b", "c"])
    queue.take()
    queue.requeue("a")

    assert [queue.take(), queue.take(), queue.take()] == ["b", "c", "a"]


def test_the_visit_cap_stops_a_failed_concept_looping_forever():
    """Without it, `AGAIN` schedules a minute out, the learner fails again, and
    the session never reaches anything else."""
    queue = _Queue(pending=["a"], visit_cap=3)

    allowed = []
    while (concept := queue.take()) is not None:
        allowed.append(concept)
        queue.requeue(concept)

    assert len(allowed) == 3


def test_a_suppressed_concept_never_comes_back():
    queue = _Queue(pending=["a", "b"])
    queue.suppress("a")

    assert queue.take() == "b"
    assert not queue.requeue("a")


# --- fakes ----------------------------------------------------------------


class FakeVault:
    def __init__(self, categories: dict[str, list[str]] | None = None) -> None:
        self.categories = categories or {}
        self.reads: list[str] = []

    async def get_concept(self, concept_id: str) -> Concept:
        self.reads.append(concept_id)
        return Concept(
            concept_id=concept_id,
            title=concept_id,
            body=f"The body of {concept_id}.",
            categories=self.categories.get(concept_id, []),
        )

    async def search(self, query: str, k: int = 5) -> list[ConceptMatch]:
        return []

    async def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        return []


class FakeAssessments:
    def __init__(self, score: float = 1.0) -> None:
        self.score = score
        self.levels: list[DepthLevel] = []

    async def generate(self, concept: Concept, level: DepthLevel) -> Assessment:
        self.levels.append(level)
        return Assessment(
            concept_id=concept.concept_id,
            question=f"What is {concept.concept_id}?",
            rubrics=[Rubric("r1", RubricContent("Says what it is."))],
        )

    async def grade(self, assessment: Assessment, answer: str) -> list[RubricScore]:
        if answer == "UNGRADABLE":
            return [RubricScore("r1", None)]
        return [RubricScore("r1", self.score)]


class FakeTurns:
    """Plays a scripted set of answers, and records what it was given."""

    def __init__(self, answers: dict[str, list[Answer]] | None = None) -> None:
        self.answers = answers or {}
        self.default = Answer(text="an answer")
        self.posed: list[str] = []
        self.taught: list[tuple[str, object]] = []
        self.contexts: list[object] = []

    async def pose(self, assessment, concept, context) -> Answer:
        self.posed.append(assessment.concept_id)
        self.contexts.append(context)
        scripted = self.answers.get(assessment.concept_id)
        if scripted:
            return scripted.pop(0)
        return self.default

    async def teach(self, assessment, answer, event) -> None:
        self.taught.append((assessment.concept_id, event))


@pytest.fixture
def store(tmp_path):
    learner_store = SqliteLearnerStore(
        tmp_path / "learner.db", calculate_next_review, ALGORITHM, PARAMETERS_ID
    )
    yield learner_store
    learner_store.close()


def _session(store, *, turns=None, assessments=None, vault=None, cap=DEFAULT_VISIT_CAP):
    vault = vault or FakeVault()
    turns = turns or FakeTurns()
    assessments = assessments or FakeAssessments()
    session = TeachSession(
        vault,
        store,
        ConductReview(vault, store, assessments),
        turns,
        visit_cap=cap,
        clock=lambda: NOW,
    )
    return session, turns, assessments, vault


# --- the loop -------------------------------------------------------------


@pytest.mark.anyio
async def test_a_session_reviews_every_seeded_concept(store):
    session, _, _, _ = _session(store)

    report = await session.run(["a", "b"])

    assert report.concept_ids == ("a", "b")
    assert len(report.reviewed) == 2
    assert {event.concept_id for event in report.reviewed} == {"a", "b"}


@pytest.mark.anyio
async def test_the_event_is_written_before_any_teaching_happens(store):
    """The grading boundary (#39). Anything the agent says before `record` is
    help, and FSRS would compute stability from assisted recall while treating
    it as unassisted."""
    session, turns, _, _ = _session(store)

    await session.run(["a"])

    concept_id, event = turns.taught[0]
    assert concept_id == "a"
    assert event is not None  # already written when teaching began
    assert store.events("a") == [event]


@pytest.mark.anyio
async def test_teaching_does_not_move_the_schedule(store):
    """`teach` returns nothing and writes nothing — one event per visit,
    however many turns the agent takes afterwards."""
    session, turns, _, _ = _session(store)

    await session.run(["a"])

    assert len(turns.taught) == 1
    assert len(store.events("a")) == 1


@pytest.mark.anyio
async def test_the_depth_target_reaches_the_question(store):
    """Via the volatile tier's context, so the question asked matches how deep
    the learner chose to go."""
    vault = FakeVault(categories={"a": ["categories/deep"]})
    store.set_depth_target("categories/deep", DepthLevel.SPECIALIST)
    session, _, assessments, _ = _session(store, vault=vault)

    await session.run(["a"])

    assert assessments.levels == [DepthLevel.SPECIALIST]


@pytest.mark.anyio
async def test_the_concept_is_fetched_once_per_visit(store):
    """It is used three times — the question, the volatile tier, the depth
    target — and re-reading would be three round-trips where one will do."""
    session, _, _, vault = _session(store)

    await session.run(["a"])

    assert vault.reads == ["a"]


# --- the queue in the loop ------------------------------------------------


@pytest.mark.anyio
async def test_a_failed_concept_is_re_tested_in_the_same_session(store):
    """The decision that made the session a queue. `LEARNING_STEPS` is
    `(1 min, 10 min)`; under a single pass a completely failed concept would be
    gone until tomorrow, which is exactly when the failure is cheapest to fix."""
    turns = FakeTurns({"a": [Answer(text="wrong"), Answer(text="better")]})
    session, _, _, _ = _session(store, turns=turns, assessments=FakeAssessments(score=0.0))

    report = await session.run(["a"])

    assert turns.posed.count("a") > 1
    assert len(report.reviewed) > 1


@pytest.mark.anyio
async def test_the_visit_cap_bounds_a_concept_nobody_can_answer(store):
    session, turns, _, _ = _session(
        store, assessments=FakeAssessments(score=0.0), cap=2
    )

    await session.run(["a"])

    assert turns.posed.count("a") == 2


@pytest.mark.anyio
async def test_a_concept_due_in_days_does_not_come_back(store):
    """The requeue window separates two scales that never overlap: learning
    steps are minutes, graduated intervals are at least a day."""
    session, turns, _, _ = _session(store)
    for _ in range(3):  # graduate it out to a day-scale interval
        await session.run(["a"])

    state = store.scheduler_state("a")
    assert state is not None and state.due is not None
    assert state.due - NOW > REQUEUE_WITHIN
    assert turns.posed.count("a") == 3  # once per run, never requeued


@pytest.mark.anyio
async def test_requeueing_reads_the_scheduler_not_the_rating(store):
    """"Was it AGAIN?" would be a second, disagreeing opinion about
    scheduling. A concept still climbing the learning ladder comes back even
    when the last answer was fine."""
    session, turns, _, _ = _session(store, assessments=FakeAssessments(score=0.8))

    report = await session.run(["a"])

    # Answered well both times, and still asked twice: the first GOOD left it
    # on the learning ladder, due in ten minutes, so the scheduler asked for it
    # back. A rule keyed on "was it AGAIN?" would have moved on.
    assert [event.rating for event in report.reviewed] == [Rating.GOOD, Rating.GOOD]
    assert turns.posed.count("a") == 2

    # It stopped coming back when FSRS graduated it, not when the cap hit.
    state = store.scheduler_state("a")
    assert state is not None and state.due is not None
    assert state.due - NOW > REQUEUE_WITHIN


# --- skip, abandon, and the empty answer ----------------------------------


@pytest.mark.anyio
async def test_a_skip_writes_nothing_and_leaves_the_concept_due(store):
    """A skip is a scheduling preference, not evidence. Recording `AGAIN` would
    put a lapse the learner never had into an append-only log."""
    turns = FakeTurns({"a": [Answer(skipped=True)]})
    session, _, _, _ = _session(store, turns=turns)

    report = await session.run(["a"])

    assert store.events("a") == []
    assert store.scheduler_state("a") is None
    assert report.skipped == ("a",)


@pytest.mark.anyio
async def test_a_skipped_concept_does_not_come_back_this_session(store):
    turns = FakeTurns({"a": [Answer(skipped=True)]})
    session, _, _, _ = _session(store, turns=turns)

    await session.run(["a", "b"])

    assert turns.posed == ["a", "b"]


@pytest.mark.anyio
async def test_i_dont_know_is_an_attempt_and_gets_graded(store):
    """The most informative `AGAIN` there is. Telling it from a skip by reading
    the prose would put model judgement back on the write path."""
    turns = FakeTurns({"a": [Answer(text="I don't know")]})
    session, _, _, _ = _session(store, turns=turns, assessments=FakeAssessments(score=0.0))

    await session.run(["a"])

    events = store.events("a")
    assert events and events[0].rating is Rating.AGAIN
    assert events[0].answer == "I don't know"


@pytest.mark.anyio
async def test_an_empty_answer_writes_nothing(store):
    turns = FakeTurns({"a": [Answer(text="   ")]})
    session, _, _, _ = _session(store, turns=turns)

    await session.run(["a"])

    assert store.events("a") == []


@pytest.mark.anyio
async def test_abandoning_stops_the_session_and_keeps_what_was_done(store):
    """Nothing to unwind: every earlier review was committed as it happened, so
    quitting halfway is indistinguishable from finishing (#39)."""
    turns = FakeTurns({"b": [Answer(abandoned=True)]})
    session, _, _, _ = _session(store, turns=turns)

    report = await session.run(["a", "b", "c"])

    assert report.abandoned
    assert len(store.events("a")) == 1
    assert store.events("b") == []
    assert "c" not in turns.posed


# --- a grader that failed -------------------------------------------------


@pytest.mark.anyio
async def test_an_ungradable_answer_writes_nothing_and_does_not_stop_the_session(store):
    """The grader failed, not the learner. An invented `AGAIN` would be
    permanent, and FSRS would shorten every later interval from it (#36)."""
    turns = FakeTurns({"a": [Answer(text="UNGRADABLE")]})
    session, _, _, _ = _session(store, turns=turns)

    report = await session.run(["a", "b"])

    assert store.events("a") == []
    assert report.ungraded == ("a",)
    assert len(store.events("b")) == 1


@pytest.mark.anyio
async def test_teaching_still_happens_when_grading_failed(store):
    """The learner answered; they should still get taught, and the turn is told
    there is no event."""
    turns = FakeTurns({"a": [Answer(text="UNGRADABLE")]})
    session, _, _, _ = _session(store, turns=turns)

    await session.run(["a"])

    assert turns.taught == [("a", None)]


# --- nothing is persisted about the session -------------------------------


@pytest.mark.anyio
async def test_the_report_is_a_return_value_not_a_row(store):
    """No `sessions` table (#39). Every review it counts was already committed
    independently, so the report cannot disagree with the log."""
    session, _, _, _ = _session(store)

    report = await session.run(["a"])

    tables = {
        row["name"]
        for row in store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "sessions" not in tables
    assert isinstance(report, SessionReport)


@pytest.mark.anyio
async def test_an_empty_seed_is_a_session_with_nothing_in_it(store):
    session, _, _, _ = _session(store)

    report = await session.run([])

    assert report.is_empty
    assert report.concept_ids == ()


# --- due-driven seeding ---------------------------------------------------


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


@pytest.mark.anyio
async def test_due_seeding_returns_the_most_overdue_first(store):
    """`tutor review`: no goal, no graph walk — everything here has been
    studied before, so prerequisite ordering has nothing to contribute."""
    _review(store, "old", Rating.GOOD, NOW - timedelta(days=400))
    _review(store, "recent", Rating.GOOD, NOW - timedelta(days=100))
    store.scheduler_state("old")
    store.scheduler_state("recent")

    assert await due_seed(store, at=NOW) == ["old", "recent"]


@pytest.mark.anyio
async def test_due_seeding_leaves_out_what_is_not_due_yet(store):
    _review(store, "future", Rating.EASY, NOW)

    assert await due_seed(store, at=NOW) == []


@pytest.mark.anyio
async def test_due_seeding_ignores_concepts_never_reviewed(store):
    """Nothing is "due" that was never scheduled — new material is `tutor
    teach`'s job, not `tutor review`'s."""
    assert await due_seed(store, at=NOW) == []


@pytest.mark.anyio
async def test_due_seeding_respects_a_limit(store):
    for name in ("a", "b", "c"):
        _review(store, name, Rating.GOOD, NOW - timedelta(days=400))
        store.scheduler_state(name)

    assert len(await due_seed(store, at=NOW, limit=2)) == 2
