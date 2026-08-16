"""The session loop — the seam Phase 5 did not build.

Every piece existed and none of them touched: nothing called `ConductReview`
outside its tests, `build_agent` was called once to construct `root_agent`, and
`compose_session` was reached only by a CLI that printed a list and stopped.
This is where plan, agent, assessment and log finally meet.

**Code drives; the model teaches inside it** (#39). The loop decides what comes
next, when the event is written and when the session ends. The model is reached
only through `TeachingTurnPort`, which has no verb that writes anything — so a
model that misbehaves produces a bad conversation, never a corrupted schedule.
Nothing here imports ADK, which is what lets the queue, the cap, the grading
boundary and the skip rule all be tested without one.

**A queue, not a list.** `LEARNING_STEPS` is `(1 min, 10 min)` — under a single
pass those numbers would be decorative, and a concept the learner completely
failed would be gone until tomorrow, which is exactly when the failure is
cheapest to fix.

One honest limitation: the loop does **not** sleep out the ten minutes. It
approximates the spacing by putting the concept behind the rest of the queue,
so the real gap is however long the remaining work takes. That is closer to the
intent than either sleeping or asking again immediately, and it is the reason
the requeue window is generous rather than exact.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tutor.application.learner_context import context_for
from tutor.application.ports.outbound.learner_store import LearnerStorePort
from tutor.application.ports.outbound.teaching_turn import Answer, TeachingTurnPort
from tutor.application.ports.outbound.vault import VaultPort
from tutor.application.review import ConductReview
from tutor.domain.assessment import NotGraded
from tutor.domain.review import ReviewEvent

logger = logging.getLogger(__name__)

DEFAULT_VISIT_CAP = 3
"""How many times one concept may be asked in a single session.

Without a cap a badly-failed concept returns forever: `AGAIN` schedules it a
minute out, the learner fails it again, and the session never reaches anything
else. Three attempts is enough for the re-test to do its work and few enough
that a genuinely lost concept is handed to the next session instead."""

REQUEUE_WITHIN = timedelta(hours=1)
"""How soon a concept must be due to come back this sitting.

An hour cleanly separates the two scales in play: learning and relearning steps
are minutes, and every graduated review interval is at least a day. Nothing
lands in between, so this threshold never has to make a close call."""


@dataclass(frozen=True)
class SessionReport:
    """What happened. A **return value, not a row** — there is no `sessions`
    table and nothing here is persisted (#39).

    Every review it counts was already committed as it happened, so this is a
    summary of durable facts rather than a record that could disagree with
    one."""

    reviewed: tuple[ReviewEvent, ...] = ()
    concept_ids: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    ungraded: tuple[str, ...] = ()
    abandoned: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.reviewed and not self.skipped


@dataclass
class _Queue:
    """Seeded once, then re-fed. Pure — no I/O, so the mechanics are testable
    without a model, a vault or a clock."""

    pending: list[str]
    visits: dict[str, int] = field(default_factory=dict)
    suppressed: set[str] = field(default_factory=set)
    visit_cap: int = DEFAULT_VISIT_CAP

    def take(self) -> str | None:
        while self.pending:
            concept_id = self.pending.pop(0)
            if concept_id in self.suppressed:
                continue
            self.visits[concept_id] = self.visits.get(concept_id, 0) + 1
            return concept_id
        return None

    def requeue(self, concept_id: str) -> bool:
        """Back on the **end**, so the re-test is spaced by the rest of the
        work rather than asked again immediately.

        Refused once the cap is reached: at that point the concept has had its
        chance this sitting, and FSRS will offer it again tomorrow regardless."""
        if concept_id in self.suppressed:
            return False
        if self.visits.get(concept_id, 0) >= self.visit_cap:
            logger.debug("%s hit the visit cap — leaving it for next session", concept_id)
            return False
        self.pending.append(concept_id)
        return True

    def suppress(self, concept_id: str) -> None:
        """A skip. Out for the rest of the session, and it stays due — a skip
        is a scheduling preference, not evidence, so nothing is written."""
        self.suppressed.add(concept_id)


class TeachSession:
    """Runs one session over a seeded list of concepts."""

    def __init__(
        self,
        vault: VaultPort,
        learner_store: LearnerStorePort,
        review: ConductReview,
        turns: TeachingTurnPort,
        visit_cap: int = DEFAULT_VISIT_CAP,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._vault = vault
        self._learner_store = learner_store
        self._review = review
        self._turns = turns
        self._visit_cap = visit_cap
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, seed: Sequence[str]) -> SessionReport:
        queue = _Queue(pending=list(seed), visit_cap=self._visit_cap)
        reviewed: list[ReviewEvent] = []
        taught: list[str] = []
        ungraded: list[str] = []
        abandoned = False

        while (concept_id := queue.take()) is not None:
            if concept_id not in taught:
                taught.append(concept_id)

            answer, event = await self._visit(concept_id)

            if answer.abandoned:
                # Nothing to unwind: every earlier review was committed as it
                # happened, so quitting halfway is indistinguishable from
                # finishing (#39).
                abandoned = True
                break
            if answer.skipped or not answer.is_attempt:
                queue.suppress(concept_id)
                continue
            if event is None:
                ungraded.append(concept_id)
                continue

            reviewed.append(event)
            if self._should_return(concept_id):
                queue.requeue(concept_id)

        return SessionReport(
            reviewed=tuple(reviewed),
            concept_ids=tuple(taught),
            skipped=tuple(queue.suppressed),
            ungraded=tuple(ungraded),
            abandoned=abandoned,
        )

    async def _visit(self, concept_id: str) -> tuple[Answer, ReviewEvent | None]:
        """Ask, take the first answer, grade it, then teach.

        The order is the contract. `record` fires on the learner's first
        unassisted response and **before** any teaching happens, so the grade
        FSRS receives is unassisted recall — which is what it computes
        stability as though it were."""
        concept = await self._vault.get_concept(concept_id)
        context = context_for(concept, self._learner_store)
        assessment = await self._review.assess(concept, context.depth_target)

        answer = await self._turns.pose(assessment, concept, context)
        if answer.abandoned:
            return answer, None
        if not answer.is_attempt:
            return answer, None

        event: ReviewEvent | None = None
        try:
            event = await self._review.record(
                assessment, answer.text, reviewed_at=self._clock()
            )
        except NotGraded:
            # The grader failed, not the learner. Nothing is written — an
            # invented `AGAIN` would be permanent, and FSRS would shorten every
            # later interval from it (#36).
            logger.warning("could not grade the answer for %s — recording nothing", concept_id)

        await self._turns.teach(assessment, answer, event)
        return answer, event

    def _should_return(self, concept_id: str) -> bool:
        """Is this concept due again inside this sitting?

        Read off the scheduler rather than off the rating, deliberately. "Was
        it `AGAIN`?" would be a second, disagreeing opinion about scheduling —
        FSRS already answers this, through the learning and relearning steps,
        and a concept still climbing the ladder should return even when the
        last answer was fine."""
        state = self._learner_store.scheduler_state(concept_id)
        if state is None or state.due is None:
            return False
        return state.due - self._clock() <= REQUEUE_WITHIN


async def due_seed(
    learner_store: LearnerStorePort,
    at: datetime | None = None,
    limit: int | None = None,
) -> list[str]:
    """`tutor review` — everything due, most overdue first.

    No goal and no graph walk: every concept here has been studied before, so
    prerequisite ordering has nothing to contribute (#39)."""
    return learner_store.due_concepts(at or datetime.now(UTC), limit)
