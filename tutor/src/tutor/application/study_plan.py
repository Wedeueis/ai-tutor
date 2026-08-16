"""What to study next, projected from the graph, the log and the targets.

**A study plan is a value, not an entity.** There is no `study_plans` table, no
id, and no way to save one (PRD v3 RF3.1, decided in #4). It is recomputed from
*(prerequisite graph, review log, depth targets)* every time anyone asks.

That is what deleted v2's "re-routing" as a feature. A stored plan has to be
invalidated when a prerequisite regresses, which means something has to notice
the regression and remember to act on it; a projection re-routes by
construction, because the regressed prerequisite is simply under target again
the next time the plan is built. RF3.5 keeps the property as a *stated
behaviour with a test* so it stays intentional rather than accidental.

The projection itself (`project`) is pure — a graph, a set of statuses and a
clock in, an ordered plan out. `StudyPlanner` is the part that gathers those
three things through the ports. Splitting them is what lets the ordering rules,
the cycle tolerance and the re-routing property be tested without a vault, a
database or a model.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from tutor.application.ports.outbound.learner_store import LearnerStorePort
from tutor.application.ports.outbound.vault import Edge, VaultPort
from tutor.domain.depth import DEFAULT_DEPTH_LEVEL, DepthLevel, deepest, meets_target
from tutor.domain.scheduling import SchedulerState

logger = logging.getLogger(__name__)

REQUIRES = "requires"
"""The only prerequisite tier the planner reads (RF3.1).

`pipeline` also emits `may_require::` for edges its quality gate declined to
vouch for. Those are recorded for a human to review and are **inert by
design** (#14). `McpVault.prerequisites` already filters them out server-side
and again on the way in; this filter is the third, and it is here because this
is the module that would do the damage — a plan walking `may_require::` would
send the learner to study things nothing ever confirmed were prerequisites."""

DEFAULT_MAX_HOPS = 3


class WorkKind(str, Enum):
    """Why a concept is in the plan — derived, never tuned (RF3.4).

    There is deliberately no ratio between these and no knob to set one.
    Adaptive explore/exploit balancing is deferred to #21 because it needs a
    learner history to adapt to, and an unpredictable ordering over an empty
    record is worse than a derived one."""

    EXPLOIT = "exploit"
    """Studied before and now under target: strengthen what is already there."""

    EXPLORE = "explore"
    """Never reviewed. New ground, on the frontier of what is already known."""


@dataclass(frozen=True)
class ConceptStatus:
    """Everything the projection needs to know about one concept.

    Assembled by `StudyPlanner` from three different places — the target from
    the learner's declared intent, the state from the projection over the log,
    the discursive flag from the log itself — and passed in as data so the
    projection stays pure."""

    concept_id: str
    target: DepthLevel = DEFAULT_DEPTH_LEVEL
    state: SchedulerState | None = None
    has_discursive_evidence: bool = False
    """A property of the review *log*, not of the FSRS projection: it records
    that a free-text answer was graded, which is the evidence `specialist`
    asks for on top of durability (RF4.4, and the reason Task 2.2 left it a
    parameter)."""

    @property
    def met(self) -> bool:
        return meets_target(self.state, self.target, self.has_discursive_evidence)

    @property
    def reviewed(self) -> bool:
        return self.state is not None


@dataclass(frozen=True)
class PlanItem:
    concept_id: str
    kind: WorkKind
    target: DepthLevel
    due: datetime | None = None
    distance: int = 0
    """Hops from the goal along `requires::`. The goal is 0, the things it
    directly requires are 1, and so on — so a *larger* distance means work
    that comes *earlier*."""

    unmet_prerequisites: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        """Actionable-ness, kept separate from `kind`. `kind` says what sort of
        work this is; this says whether it can be done yet. Blocked items stay
        in the plan rather than being filtered out — they are what the work
        ahead of them is *for*, and hiding them would make a plan of five
        prerequisites look like a plan with no goal in it."""
        return bool(self.unmet_prerequisites)


@dataclass(frozen=True)
class StudyPlan:
    goal_id: str
    items: tuple[PlanItem, ...] = ()
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """When this projection was taken. Not a cache key — nothing caches a
    plan — but a plan printed to a terminal or handed to a model is a claim
    about a moment, and it should say which one."""

    def __iter__(self) -> Iterator[PlanItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def actionable(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self.items if not item.blocked)


def project(
    goal_id: str,
    edges: Sequence[Edge],
    statuses: Mapping[str, ConceptStatus],
    *,
    now: datetime | None = None,
) -> StudyPlan:
    """The projection. Pure: same inputs, same plan, always.

    A concept is in the plan when there is something to do about it. Concepts
    already at or above their target are simply absent — which is why a
    regression puts one back, ahead of whatever depends on it.

    **Cycles are tolerated, not resolved.** The traversal is breadth-first with
    a visited set, so `a requires b requires a` terminates; both concepts then
    list each other as unmet and both read as blocked. That is a legible
    symptom of a bad edge rather than a hang or an arbitrary tie-break that
    hides it — and consumers have to tolerate cycles regardless, because a
    backfilled or hand-edited graph can contain one (RF1.1)."""
    now = now or datetime.now(UTC)
    requires = _adjacency(edges)
    distances = _distances_from(goal_id, requires)

    items = [
        _item(concept_id, distance, requires, statuses)
        for concept_id, distance in distances.items()
        if not _status(concept_id, statuses).met
    ]
    items.sort(key=_ordering)
    return StudyPlan(goal_id=goal_id, items=tuple(items), built_at=now)


def _item(
    concept_id: str,
    distance: int,
    requires: Mapping[str, tuple[str, ...]],
    statuses: Mapping[str, ConceptStatus],
) -> PlanItem:
    status = _status(concept_id, statuses)
    unmet = tuple(
        prerequisite
        for prerequisite in requires.get(concept_id, ())
        if not _status(prerequisite, statuses).met
    )
    return PlanItem(
        concept_id=concept_id,
        # Never reviewed is new ground, whatever its prerequisites look like;
        # a review history under target is work to strengthen. The split is a
        # fact about the log, which is why nothing here needs a threshold.
        kind=WorkKind.EXPLOIT if status.reviewed else WorkKind.EXPLORE,
        target=status.target,
        due=status.state.due if status.state else None,
        distance=distance,
        unmet_prerequisites=unmet,
    )


def _ordering(item: PlanItem) -> tuple[object, ...]:
    """Prerequisites first, then what is due, then the id.

    The id is the last key and it is not decoration: two concepts due the same
    day must not shuffle between runs, or the learner sees a different plan
    each morning from the same evidence. FSRS's fuzzing is off for the same
    reason (RF4.1)."""
    return (
        -item.distance,  # deepest prerequisite first
        item.blocked,  # what can be done now, before what cannot
        item.kind is WorkKind.EXPLORE,  # strengthen before opening new ground
        item.due.timestamp() if item.due else float("inf"),
        item.concept_id,
    )


def _adjacency(edges: Sequence[Edge]) -> dict[str, tuple[str, ...]]:
    """`{dependent: (prerequisites, ...)}`, deduplicated, order preserved."""
    graph: dict[str, list[str]] = {}
    for edge in edges:
        if edge.relation_type != REQUIRES:
            continue
        targets = graph.setdefault(edge.from_id, [])
        if edge.to_id not in targets:
            targets.append(edge.to_id)
    return {source: tuple(targets) for source, targets in graph.items()}


def _distances_from(
    goal_id: str, requires: Mapping[str, tuple[str, ...]]
) -> dict[str, int]:
    """Breadth-first hop count from the goal, first visit winning.

    The visited set is what makes this cycle-safe. It also means a concept
    reachable by both a short and a long path gets the short distance, so it is
    scheduled as late as any of its dependents allow — the conservative choice,
    since the deeper reading of a shared prerequisite is the one that has
    something waiting on it."""
    distances = {goal_id: 0}
    queue = deque([goal_id])
    while queue:
        current = queue.popleft()
        for prerequisite in requires.get(current, ()):
            if prerequisite in distances:
                continue
            distances[prerequisite] = distances[current] + 1
            queue.append(prerequisite)
    return distances


def _status(concept_id: str, statuses: Mapping[str, ConceptStatus]) -> ConceptStatus:
    """An unknown concept is untargeted and unreviewed, not an error. The plan
    routinely reaches concepts nobody has ever opened."""
    return statuses.get(concept_id) or ConceptStatus(concept_id=concept_id)


class StudyPlanner:
    """Gathers the three inputs and hands them to `project`.

    Holds no state between calls, deliberately: a planner that cached the graph
    would go stale the moment `pipeline` ingested anything, and the vault is
    authoritative for the graph."""

    def __init__(
        self,
        vault: VaultPort,
        learner_store: LearnerStorePort,
        max_hops: int = DEFAULT_MAX_HOPS,
    ) -> None:
        self._vault = vault
        self._learner_store = learner_store
        self._max_hops = max_hops

    async def plan(self, goal_id: str, *, now: datetime | None = None) -> StudyPlan:
        edges = await self._vault.prerequisites(goal_id, max_hops=self._max_hops)
        concept_ids = {goal_id}
        for edge in edges:
            concept_ids.update((edge.from_id, edge.to_id))

        statuses = {
            concept_id: await self._status_of(concept_id)
            for concept_id in sorted(concept_ids)
        }
        return project(goal_id, edges, statuses, now=now)

    async def _status_of(self, concept_id: str) -> ConceptStatus:
        return ConceptStatus(
            concept_id=concept_id,
            target=await self._target_for(concept_id),
            state=self._learner_store.scheduler_state(concept_id),
            has_discursive_evidence=self._learner_store.has_discursive_evidence(
                concept_id
            ),
        )

    async def _target_for(self, concept_id: str) -> DepthLevel:
        """The deepest target among the concept's Categories.

        Deepest, not first or last: any other rule lets *adding* a Category
        quietly lower what is asked of a concept, so "specialise in GraphRAG"
        would be undone by those concepts also sitting in a broad `aware`
        Category. A concept in no Category resolves to `aware` (#20)."""
        try:
            concept = await self._vault.get_concept(concept_id)
        except Exception:  # noqa: BLE001 - see below
            # Broken links are tolerated by the format, not errors (§6), and a
            # prerequisite pointing at a concept that has since been renamed
            # must not make the whole plan unbuildable. The concept still
            # appears in the plan, at the default target.
            logger.warning(
                "could not read %s while planning — treating it as untargeted",
                concept_id,
                exc_info=True,
            )
            return DEFAULT_DEPTH_LEVEL

        return deepest(
            self._learner_store.depth_target(category)
            for category in concept.categories
        )
