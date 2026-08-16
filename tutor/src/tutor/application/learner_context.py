"""Assembling the volatile tier from the store.

Two lookups and a resolution, kept out of `HermesDomainOrchestrator` on
purpose: the harness is a composition root for *prompts* and has no business
holding a store. Passing the finished context in is what keeps it that way, and
what makes every composition test runnable without a database.
"""

from __future__ import annotations

from tutor.application.ports.outbound.learner_store import LearnerStorePort
from tutor.application.ports.outbound.vault import Concept
from tutor.domain.depth import deepest
from tutor.domain.learner_context import LearnerContext


def context_for(concept: Concept, learner_store: LearnerStorePort) -> LearnerContext:
    """The learner's history with one concept, plus how deep they chose to go.

    The depth target is the deepest across the concept's Categories — the same
    rule the study plan uses, and for the same reason: any other rule lets
    adding a broad Category quietly lower what is asked of a concept."""
    summary = learner_store.review_summary(concept.concept_id)
    return LearnerContext(
        times_seen=summary.times_seen,
        last_reviewed_at=summary.last_reviewed_at,
        last_rating=summary.last_rating,
        depth_target=deepest(
            learner_store.depth_target(category) for category in concept.categories
        ),
    )
