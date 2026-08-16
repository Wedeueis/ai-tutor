"""One session's worth of work, taken from the study plan.

The plan says what there is to do and in what order; this says how much of it
fits in one sitting and which end to start from. Keeping them separate matters
because they answer to different things — the plan answers to the graph and the
log, a session answers to how long the learner has.

**Composed once, at the start** (RF2.7). A session is a frozen value, not a
live view over the plan: reviews inside it change FSRS state, and a session
that re-derived itself mid-dialogue would reorder under the learner's feet.
Mastery changes surface in the *next* session.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from tutor.application.study_plan import PlanItem, StudyPlan, WorkKind

DEFAULT_SESSION_SIZE = 10
"""How many concepts one sitting holds. A size, not a ratio.

This is the only number a caller may set, and it deliberately says nothing
about the *mix* — that is derived (RF3.4)."""


@dataclass(frozen=True)
class Session:
    goal_id: str
    items: tuple[PlanItem, ...] = ()
    composed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __iter__(self) -> Iterator[PlanItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def exploit(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self if item.kind is WorkKind.EXPLOIT)

    @property
    def explore(self) -> tuple[PlanItem, ...]:
        return tuple(item for item in self if item.kind is WorkKind.EXPLORE)


def compose_session(
    plan: StudyPlan,
    size: int = DEFAULT_SESSION_SIZE,
    *,
    now: datetime | None = None,
) -> Session:
    """Fill a session from the plan: **due-and-under-target first**, then the
    rest of the under-target work, then new ground (RF3.4).

    Three bands, each keeping the plan's own order inside it — so
    prerequisites still come before what depends on them, and a tie still
    breaks the same way it did in the plan. The bands only decide which kind of
    work is reached first when there is not room for all of it.

    Blocked items are left out. They are in the plan because they are what the
    work is *for*, but a concept whose prerequisites are unmet is not something
    the learner can sit down and do today.

    **There is no ratio knob and no explore/exploit parameter.** Adaptive
    balancing is deferred to #21 precisely because it needs a learner history
    to adapt to; a knob here would be that feature arriving by the back door,
    and an unpredictable ordering over an empty record is worse than a derived
    one."""
    now = now or datetime.now(UTC)
    actionable = plan.actionable()

    due = [item for item in actionable if _is_due(item, now)]
    strengthen = [
        item
        for item in actionable
        if item.kind is WorkKind.EXPLOIT and not _is_due(item, now)
    ]
    explore = [item for item in actionable if item.kind is WorkKind.EXPLORE]

    ordered = [*due, *strengthen, *explore]
    return Session(
        goal_id=plan.goal_id,
        items=tuple(ordered[: max(size, 0)]),
        composed_at=now,
    )


def _is_due(item: PlanItem, now: datetime) -> bool:
    """Due means FSRS scheduled it for today or earlier.

    A concept with no `due` has never been reviewed, so it is explore work
    rather than overdue work — "never studied" is not the same claim as "you
    were supposed to review this in March"."""
    return item.due is not None and item.due <= now
