"""Prerequisite edges: which concepts a learner must already understand
before a given concept is followable at all.

Two tiers, because precision matters more than recall here — a study plan
built on a wrong prerequisite sends someone to study something they don't
need, and there is no signal that tells them so:

- `requires::`   — confident. The ONLY tier any consumer reads.
- `may_require::` — uncertain. Recorded, inert, reviewable by a human. Nothing
  in this codebase reads it, and nothing should start.

The tier is decided by the same rubric rollup that gates concept quality
(`domain/eval.py`'s `aggregate_scores`), applied per edge rather than per
concept: an edge whose rubric scores clear the threshold is `requires::`,
one that doesn't is `may_require::`. This module is pure — the judging
happens behind `PrerequisiteSkillPort`, the graph lookups behind
`MetadataRepositoryPort`.

**On the rollup, and a superseded suspicion.** An earlier note here argued the
flat mean was the wrong shape for a precision-first gate, because a
plainly-sibling pair scored `blocks_comprehension` 0.0 and still averaged 0.70
into `requires::` on `llama3.1:8b`. Measuring against the gold set disproved
it: that model scored 0.517 precision by saying yes to nearly everything, and
its per-rubric means separated true from false pairs by 0.007 — the mean was
not outvoting a good signal, there was no signal to outvote. With a model that
can make the judgement, the same rubrics and the same flat mean score **1.000
precision** on the same 30 pairs. The rollup is fine; it was never the
constraint (issues #24, #19)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from pipeline.domain.concept import ConceptId
from pipeline.domain.eval import EvalResult, RubricScore, aggregate_scores


class PrerequisiteTier(str, Enum):
    """The relation type each tier is written as. The enum value IS the
    relation type, so the string that lands in `typed_links` is derived from
    the tier rather than repeated next to it."""

    REQUIRES = "requires"
    MAY_REQUIRE = "may_require"


@dataclass(frozen=True)
class PrerequisiteCandidate:
    """One existing concept offered to the prerequisite skill as something the
    draft might depend on. `description` is included because a prerequisite
    judgement turns on what the target actually teaches, which a title alone
    often doesn't convey ("Attention" — the mechanism, or the concept?)."""

    concept_id: ConceptId
    title: str | None
    description: str | None = None


@dataclass(frozen=True)
class PrerequisiteAssessment:
    """The skill's per-edge verdict: one rubric score per rubric, for one
    candidate. Pass/fail is NOT decided here — that's `select_prerequisites`
    below, mirroring how `QualityEvalSkillPort` leaves the rollup to
    `aggregate_scores`."""

    target_id: ConceptId
    scores: list[RubricScore] = field(default_factory=list)
    rationale: str = ""


@dataclass(frozen=True)
class PrerequisiteEdge:
    """One prerequisite edge, tiered and ready to write onto the *dependent*
    concept's body. Unlike relatedness, this edge is directional and gets no
    reciprocal backlink: "A requires B" is a claim about A."""

    target_id: ConceptId
    tier: PrerequisiteTier
    eval: EvalResult
    rationale: str = ""

    @property
    def relation_type(self) -> str:
        return self.tier.value


def select_prerequisites(
    source_id: str,
    assessments: list[PrerequisiteAssessment],
    threshold: float,
    reachable_by: Mapping[str, set[str]] | None = None,
) -> list[PrerequisiteEdge]:
    """Rolls each assessment up into a tiered edge.

    `reachable_by` maps a candidate's id to the ids reachable from it by
    following `requires::` edges. An edge whose target can already reach
    `source_id` would close a cycle, so it is **demoted to `may_require::`
    rather than dropped** — the judgement was made and is worth keeping for
    review, and demoting keeps the `requires::` tier acyclic without losing
    it. Dropping would silently discard a signal a human might want to act
    on; leaving it would put a cycle in the one tier consumers walk.

    A self-edge is dropped outright: it is never a judgement worth reviewing.

    An assessment that left any rubric unscored cannot reach `requires::`.
    `aggregate_scores` averages over the scores it was *given*, so a model that
    answered one rubric at 1.0 and skipped the rest would otherwise sail
    through the gate on a single opinion. That rollup is shared with concept
    quality and stays as it is; completeness is enforced here, where precision
    is the requirement (RF1.3).
    """
    reachable_by = reachable_by or {}
    edges: list[PrerequisiteEdge] = []
    for assessment in assessments:
        target = str(assessment.target_id)
        if target == source_id:
            continue

        result = aggregate_scores(assessment.scores, threshold=threshold)
        complete = bool(assessment.scores) and all(s.score is not None for s in assessment.scores)
        tier = (
            PrerequisiteTier.REQUIRES
            if result.passed and complete
            else PrerequisiteTier.MAY_REQUIRE
        )
        if tier is PrerequisiteTier.REQUIRES and source_id in reachable_by.get(target, set()):
            tier = PrerequisiteTier.MAY_REQUIRE

        edges.append(
            PrerequisiteEdge(
                target_id=assessment.target_id,
                tier=tier,
                eval=result,
                rationale=assessment.rationale,
            )
        )
    return edges
