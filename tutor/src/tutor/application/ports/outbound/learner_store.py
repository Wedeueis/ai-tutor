"""Episodic memory: the review log, the learner's declared depth targets, and
the projections rebuilt from them.

Backed by `learner.db`, owned entirely by `tutor` and shared with nothing —
not `pipeline`, and not ADK's session database, which is kept separate on
purpose because ADK is pre-1.0 and its schema will churn while the review
history is the one thing here that cannot be regenerated (PRD v3 §7).

Nothing on this port takes a `user_id`. There is exactly one learner."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from tutor.domain.depth import DepthLevel
from tutor.domain.review import ReviewEvent, ReviewSummary
from tutor.domain.scheduling import SchedulerState


class LearnerStorePort(Protocol):
    def append_review(self, event: ReviewEvent) -> None:
        """Append-only. There is deliberately no update or delete: the log is
        authoritative, and everything else here is derived from it."""
        ...

    def scheduler_state(self, concept_id: str) -> SchedulerState | None:
        """The cached projection, or None for a concept never reviewed.

        Implementations must reject a checkpoint whose `(algorithm,
        parameters)` differs from what is in force and replay instead. Reusing
        a stale checkpoint after a parameter re-fit silently corrupts
        scheduling, so the identity is compared before use rather than
        maintained by remembering to clear a table (PRD v3 §7)."""
        ...

    def review_summary(self, concept_id: str) -> ReviewSummary:
        """The concept's history as the *prompt* is allowed to see it (RF2.7).

        Deliberately not `scheduler_state`, even though both are projections
        over the same log. That one carries stability and difficulty, which must
        never reach a model (#39); this one carries how often, how recently and
        how it went. Two types rather than one is what stops a scheduler field
        arriving in a prompt because it happened to be on an object already in
        scope.

        Never raises: a concept nobody has reviewed has an empty summary, not
        an error."""
        ...

    def has_discursive_evidence(self, concept_id: str) -> bool:
        """Has this concept ever been reviewed by a free-text answer graded
        against a rubric, rather than a self-reported recall grade?

        A question about the **log**, not about the projection — which is why
        it is its own method rather than a field on `SchedulerState`. FSRS
        state records how durable the memory is; this records what kind of
        evidence produced it, and the `specialist` depth level asks for both
        (RF4.4). Explaining something in your own words is different evidence
        from recognising it, and nothing in a stability number distinguishes
        them."""
        ...

    def due_concepts(self, at: datetime, limit: int | None = None) -> list[str]:
        """Everything scheduled for `at` or earlier, most overdue first.

        This is the seeding for `tutor review` — the primary loop of any
        spaced-repetition system, and the one thing Phase 4's goal-rooted
        planning could not express: a concept overdue but off the path to
        whatever you named was stranded (#39)."""
        ...

    def replay(self, concept_id: str | None = None) -> None:
        """Rebuilds projections from the log — one concept, or all of them.

        Off the read path and cheap enough not to need care: a heavy decade is
        ~730k events (~35 MB), a full rebuild is seconds, one concept is
        milliseconds."""
        ...

    def depth_target(self, category_id: str) -> DepthLevel:
        """Never raises for an unknown Category — it resolves to `aware`
        (`DEFAULT_DEPTH_LEVEL`). New Categories arrive from ingest unseen, and
        defaulting to depth would commit the learner to study they never
        chose."""
        ...

    def set_depth_target(self, category_id: str, level: DepthLevel) -> None:
        """The only authoritative state here that is not an event, and the only
        thing in `learner.db` that cannot be rebuilt by replay — it is declared
        intent, not something that happened."""
        ...
