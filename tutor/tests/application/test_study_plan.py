"""The study plan as a projection.

Two layers, tested differently. `project` is pure, so it is exercised with
plain data — a graph, some statuses, a clock. `StudyPlanner` is exercised
against a fake vault and a **real** `SqliteLearnerStore` driving the **real**
FSRS scheduler, because the property RF3.5 asks for — a plan that re-routes
when a prerequisite regresses — is only convincing if the regression is
produced by an actual bad review rather than by hand-written state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.application.ports.outbound.vault import Concept, ConceptMatch, Edge
from tutor.application.study_plan import (
    ConceptStatus,
    PlanItem,
    StudyPlanner,
    WorkKind,
    project,
)
from tutor.domain.depth import DepthLevel
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import (
    ALGORITHM,
    PARAMETERS_ID,
    Rating,
    SchedulerState,
    calculate_next_review,
)

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _requires(*pairs: tuple[str, str]) -> list[Edge]:
    return [Edge(from_id=a, to_id=b, relation_type="requires") for a, b in pairs]


def _mastered(stability: float = 400.0, due: datetime | None = None) -> SchedulerState:
    """A state comfortably above every threshold, so a test that is about
    ordering is not accidentally about `meets_target`."""
    return SchedulerState(
        stability=stability,
        difficulty=5.0,
        due=due or NOW + timedelta(days=200),
        last_review=NOW - timedelta(days=1),
    )


def _weak(due: datetime | None = None) -> SchedulerState:
    """Reviewed, but nowhere near even `aware`'s seven days."""
    return SchedulerState(
        stability=1.0,
        difficulty=5.0,
        due=due or NOW,
        last_review=NOW - timedelta(days=1),
    )


def _ids(plan) -> list[str]:
    return [item.concept_id for item in plan]


# --- what lands in the plan ----------------------------------------------


def test_a_lone_goal_never_reviewed_is_explore_work():
    plan = project("transformers", [], {}, now=NOW)

    assert _ids(plan) == ["transformers"]
    assert plan.items[0].kind is WorkKind.EXPLORE
    assert not plan.items[0].blocked


def test_a_concept_at_its_target_is_simply_absent():
    """Nothing to do about it, so it is not work. This is also the mechanism
    behind re-routing: the plan has no memory of having dropped it, so the
    moment it regresses it is back."""
    plan = project(
        "transformers",
        [],
        {"transformers": ConceptStatus("transformers", state=_mastered())},
        now=NOW,
    )

    assert list(plan) == []


def test_a_reviewed_concept_under_target_is_exploit_work():
    plan = project(
        "transformers",
        [],
        {"transformers": ConceptStatus("transformers", state=_weak())},
        now=NOW,
    )

    assert plan.items[0].kind is WorkKind.EXPLOIT


def test_the_split_is_the_review_history_not_a_threshold():
    """EXPLORE means "never touched"; EXPLOIT means "touched and not yet
    durable". Nothing here reads a ratio, and there is no knob to set one
    (RF3.4, deferred in #21)."""
    statuses = {
        "seen": ConceptStatus("seen", state=_weak()),
        "unseen": ConceptStatus("unseen"),
    }
    plan = project("seen", _requires(("seen", "unseen")), statuses, now=NOW)

    kinds = {item.concept_id: item.kind for item in plan}
    assert kinds == {"seen": WorkKind.EXPLOIT, "unseen": WorkKind.EXPLORE}


# --- ordering -------------------------------------------------------------


def test_prerequisites_come_before_what_depends_on_them():
    plan = project(
        "attention",
        _requires(("attention", "softmax"), ("softmax", "exponentials")),
        {},
        now=NOW,
    )

    assert _ids(plan) == ["exponentials", "softmax", "attention"]


def test_within_one_depth_the_most_overdue_comes_first():
    statuses = {
        "a": ConceptStatus("a", state=_weak(due=NOW + timedelta(days=3))),
        "b": ConceptStatus("b", state=_weak(due=NOW - timedelta(days=10))),
        "c": ConceptStatus("c", state=_weak(due=NOW - timedelta(days=1))),
    }
    plan = project(
        "goal",
        _requires(("goal", "a"), ("goal", "b"), ("goal", "c")),
        statuses,
        now=NOW,
    )

    assert _ids(plan)[:3] == ["b", "c", "a"]


def test_strengthening_comes_before_opening_new_ground():
    statuses = {"known": ConceptStatus("known", state=_weak())}
    plan = project(
        "goal", _requires(("goal", "known"), ("goal", "new")), statuses, now=NOW
    )

    assert _ids(plan)[:2] == ["known", "new"]


def test_ties_are_broken_by_id_so_the_plan_does_not_shuffle_between_runs():
    """Two concepts due the same day must order identically every time, or the
    learner sees a different plan each morning from the same evidence — the
    same reason FSRS's fuzzing is off (RF4.1)."""
    edges = _requires(("goal", "zebra"), ("goal", "aardvark"), ("goal", "mongoose"))
    statuses = {
        name: ConceptStatus(name, state=_weak(due=NOW))
        for name in ("zebra", "aardvark", "mongoose")
    }

    first = _ids(project("goal", edges, statuses, now=NOW))
    again = _ids(project("goal", list(reversed(edges)), statuses, now=NOW))

    assert first[:3] == ["aardvark", "mongoose", "zebra"]
    assert first == again


# --- blocked work ---------------------------------------------------------


def test_a_goal_whose_prerequisite_is_unmet_is_blocked_but_still_listed():
    """Blocked items stay in the plan: they are what the work ahead of them is
    for, and hiding them would make a plan of five prerequisites look like a
    plan with no goal in it."""
    plan = project("attention", _requires(("attention", "softmax")), {}, now=NOW)

    goal = next(item for item in plan if item.concept_id == "attention")
    assert goal.blocked
    assert goal.unmet_prerequisites == ("softmax",)
    assert _ids(plan.actionable()) == ["softmax"]


def test_a_met_prerequisite_unblocks_its_dependent():
    statuses = {"softmax": ConceptStatus("softmax", state=_mastered())}
    plan = project("attention", _requires(("attention", "softmax")), statuses, now=NOW)

    assert _ids(plan) == ["attention"]
    assert not plan.items[0].blocked


# --- the tiers ------------------------------------------------------------


def test_may_require_edges_are_ignored():
    """`may_require::` is recorded for human review and is inert by design
    (#14). A plan that walked it would send the learner to study something the
    quality gate explicitly declined to vouch for."""
    edges = [
        Edge(from_id="attention", to_id="softmax", relation_type="requires"),
        Edge(from_id="attention", to_id="calculus", relation_type="may_require"),
    ]
    plan = project("attention", edges, {}, now=NOW)

    assert "calculus" not in _ids(plan)
    assert _ids(plan) == ["softmax", "attention"]


# --- cycles ---------------------------------------------------------------


def test_a_cycle_terminates_and_is_reported_rather_than_resolved():
    """The emitter avoids cycles, but a backfilled or hand-edited graph can
    still contain one and consumers must tolerate it (RF1.1). Both members
    reading as blocked is a legible symptom of the bad edge; a hang or a silent
    tie-break would hide it."""
    plan = project("a", _requires(("a", "b"), ("b", "a")), {}, now=NOW)

    assert sorted(_ids(plan)) == ["a", "b"]
    assert all(item.blocked for item in plan)
    assert plan.actionable() == ()


def test_a_self_edge_does_not_loop():
    plan = project("a", _requires(("a", "a")), {}, now=NOW)

    assert _ids(plan) == ["a"]


# --- depth targets --------------------------------------------------------


def test_the_target_is_carried_on_the_item():
    statuses = {"x": ConceptStatus("x", target=DepthLevel.SPECIALIST)}
    plan = project("x", [], statuses, now=NOW)

    assert plan.items[0].target is DepthLevel.SPECIALIST


def test_a_deeper_target_keeps_a_concept_in_the_plan_that_aware_would_release():
    """The same evidence, two targets: 30 days of stability is `working` but
    not `specialist`."""
    state = SchedulerState(stability=45.0, difficulty=5.0, last_review=NOW)

    working = project(
        "x", [], {"x": ConceptStatus("x", DepthLevel.WORKING, state)}, now=NOW
    )
    specialist = project(
        "x", [], {"x": ConceptStatus("x", DepthLevel.SPECIALIST, state)}, now=NOW
    )

    assert list(working) == []
    assert _ids(specialist) == ["x"]


def test_specialist_needs_discursive_evidence_however_durable_the_memory():
    state = SchedulerState(stability=1000.0, difficulty=5.0, last_review=NOW)
    status = ConceptStatus("x", DepthLevel.SPECIALIST, state)

    assert _ids(project("x", [], {"x": status}, now=NOW)) == ["x"]

    with_evidence = ConceptStatus(
        "x", DepthLevel.SPECIALIST, state, has_discursive_evidence=True
    )
    assert list(project("x", [], {"x": with_evidence}, now=NOW)) == []


def test_an_unknown_concept_is_untargeted_rather_than_an_error():
    """The plan routinely reaches concepts nobody has ever opened."""
    plan = project("goal", _requires(("goal", "never-seen")), {}, now=NOW)

    item: PlanItem = next(i for i in plan if i.concept_id == "never-seen")
    assert item.target is DepthLevel.AWARE
    assert item.kind is WorkKind.EXPLORE


# --- the planner, over the ports ------------------------------------------


class FakeVault:
    """`VaultPort` over dictionaries. The graph and the categories are the only
    two things the planner reads from the vault."""

    def __init__(
        self,
        edges: list[Edge],
        categories: dict[str, list[str]] | None = None,
        missing: set[str] | None = None,
    ) -> None:
        self.edges = edges
        self.categories = categories or {}
        self.missing = missing or set()
        self.max_hops_seen: list[int] = []

    async def get_concept(self, concept_id: str) -> Concept:
        if concept_id in self.missing:
            raise RuntimeError(f"no such concept: {concept_id}")
        return Concept(
            concept_id=concept_id, categories=self.categories.get(concept_id, [])
        )

    async def search(self, query: str, k: int = 5) -> list[ConceptMatch]:
        return []

    async def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        self.max_hops_seen.append(max_hops)
        return self.edges


@pytest.fixture
def store(tmp_path: Path) -> SqliteLearnerStore:
    """The real store, driving the real FSRS scheduler. The re-routing property
    is worth nothing if the regression is hand-written."""
    learner_store = SqliteLearnerStore(
        tmp_path / "learner.db",
        scheduler=calculate_next_review,
        algorithm=ALGORITHM,
        parameters=PARAMETERS_ID,
    )
    yield learner_store
    learner_store.close()


def _review(
    store: SqliteLearnerStore,
    concept_id: str,
    rating: Rating,
    at: datetime,
    *,
    discursive: bool = False,
) -> None:
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
            discursive=discursive,
        )
    )


def _study_until_durable(
    store: SqliteLearnerStore, concept_id: str, start: datetime
) -> datetime:
    """Review well, spaced out, until the concept is comfortably past `aware`'s
    seven days. Driven through the real scheduler rather than asserted into
    place."""
    at = start
    for _ in range(3):
        _review(store, concept_id, Rating.EASY, at)
        state = store.scheduler_state(concept_id)
        assert state is not None and state.due is not None
        at = state.due
    return at


@pytest.mark.anyio
async def test_the_planner_projects_from_the_graph_the_log_and_the_targets(store):
    vault = FakeVault(_requires(("attention", "softmax")))
    _study_until_durable(store, "softmax", NOW - timedelta(days=400))

    plan = await StudyPlanner(vault, store).plan("attention", now=NOW)

    assert _ids(plan) == ["attention"]  # softmax is done, so it is not work


@pytest.mark.anyio
async def test_the_plan_re_routes_when_a_prerequisite_regresses(store):
    """RF3.5, the property that let re-routing be *deleted* as a feature.

    Nothing invalidates anything: the plan is rebuilt from the log, and a
    prerequisite that just got answered badly is under target again."""
    vault = FakeVault(_requires(("attention", "softmax")))
    at = _study_until_durable(store, "softmax", NOW - timedelta(days=400))

    before = await StudyPlanner(vault, store).plan("attention", now=NOW)
    assert _ids(before) == ["attention"]

    _review(store, "softmax", Rating.AGAIN, at + timedelta(days=1))

    after = await StudyPlanner(vault, store).plan("attention", now=NOW)
    assert _ids(after) == ["softmax", "attention"]
    goal = next(item for item in after if item.concept_id == "attention")
    assert goal.unmet_prerequisites == ("softmax",)


@pytest.mark.anyio
async def test_the_deepest_target_among_a_concepts_categories_wins(store):
    """Adding a broad `aware` Category must not quietly lower what is asked of
    a concept the learner chose to specialise in (#20)."""
    vault = FakeVault([], categories={"graphrag": ["categories/graphrag", "categories/ml"]})
    store.set_depth_target("categories/graphrag", DepthLevel.SPECIALIST)
    store.set_depth_target("categories/ml", DepthLevel.AWARE)

    plan = await StudyPlanner(vault, store).plan("graphrag", now=NOW)

    assert plan.items[0].target is DepthLevel.SPECIALIST


@pytest.mark.anyio
async def test_a_concept_in_no_category_defaults_to_aware(store):
    plan = await StudyPlanner(FakeVault([]), store).plan("loose-note", now=NOW)

    assert plan.items[0].target is DepthLevel.AWARE


@pytest.mark.anyio
async def test_discursive_evidence_comes_from_the_log(store):
    """`specialist` asks for a graded free-text answer on top of durability,
    and only the log records that one happened (RF4.4)."""
    vault = FakeVault([], categories={"x": ["categories/deep"]})
    store.set_depth_target("categories/deep", DepthLevel.SPECIALIST)
    at = NOW - timedelta(days=1500)
    for _ in range(3):
        _review(store, "x", Rating.EASY, at, discursive=True)
        state = store.scheduler_state("x")
        assert state is not None and state.due is not None
        at = state.due

    assert store.has_discursive_evidence("x")
    plan = await StudyPlanner(vault, store).plan("x", now=NOW)

    assert list(plan) == []


@pytest.mark.anyio
async def test_a_broken_prerequisite_link_does_not_make_the_plan_unbuildable(store):
    """Broken links are tolerated by the format, not errors (§6). A renamed
    prerequisite must not take the whole plan down with it."""
    vault = FakeVault(_requires(("attention", "renamed-away")), missing={"renamed-away"})

    plan = await StudyPlanner(vault, store).plan("attention", now=NOW)

    assert _ids(plan) == ["renamed-away", "attention"]


@pytest.mark.anyio
async def test_the_walk_is_bounded_by_max_hops(store):
    vault = FakeVault([])

    await StudyPlanner(vault, store, max_hops=2).plan("x", now=NOW)

    assert vault.max_hops_seen == [2]
