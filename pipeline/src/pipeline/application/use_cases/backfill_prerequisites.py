"""Emits prerequisite edges for concepts that predate the feature
(`pipeline prerequisites`, RF1.4) — the same judge-then-link shape
`KnowledgeAgent` runs at ingest, walking the whole bundle instead of one fresh
draft. `CategorizeConcepts` is its twin, and deliberately reads like it.

Two things differ from that twin, both on purpose:

- **Domainless concepts are not skipped.** `CategorizeConcepts` skips them
  because a Category vocabulary is scoped to a Domain and there is nothing to
  classify against. Prerequisites are not domain-scoped at all, and most of
  this vault has no `domain:` — skipping them would skip the backfill.
- **Cycles are possible here.** At ingest a brand-new concept has no incoming
  edges, so it cannot close a loop; these concepts all have neighbours
  already, so the existing `requires::` graph is consulted before an edge is
  promoted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.eval_rubrics_repository import EvalRubricsRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.skills.prerequisite_judgement import (
    PrerequisiteJudgementSkillPort,
)
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.agent import DraftConcept
from pipeline.domain.concept import NON_CONTENT_TYPES, Concept, ConceptId
from pipeline.domain.linking import add_prerequisite_links
from pipeline.domain.prerequisites import (
    PrerequisiteCandidate,
    PrerequisiteEdge,
    PrerequisiteTier,
    select_prerequisites,
)

DEFAULT_PREREQUISITE_THRESHOLD = 0.7
DEFAULT_CANDIDATE_K = 5
DEFAULT_CYCLE_MAX_HOPS = 10
PREREQUISITE_RUBRICS = "prerequisites"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillOutcome:
    """What one concept gained. Returned rather than counted so a dry run can
    show the edges without writing them."""

    concept_id: str
    edges: list[PrerequisiteEdge] = field(default_factory=list)


class BackfillPrerequisites:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        metadata_repository: MetadataRepositoryPort,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        prerequisite_judgement: PrerequisiteJudgementSkillPort,
        eval_rubrics_repository: EvalRubricsRepositoryPort,
        index_concept: IndexConcept,
        threshold: float = DEFAULT_PREREQUISITE_THRESHOLD,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        cycle_max_hops: int = DEFAULT_CYCLE_MAX_HOPS,
    ) -> None:
        self._concept_repository = concept_repository
        self._metadata_repository = metadata_repository
        self._embedding = embedding
        self._vector_search = vector_search
        self._prerequisite_judgement = prerequisite_judgement
        self._eval_rubrics_repository = eval_rubrics_repository
        self._index_concept = index_concept
        self._threshold = threshold
        self._candidate_k = candidate_k
        self._cycle_max_hops = cycle_max_hops

    def run(self, limit: int | None = None, dry_run: bool = False) -> list[BackfillOutcome]:
        """`limit` and `dry_run` exist because this is expensive and it writes
        into the graph the study plan walks. On a cloud provider a full pass is
        hundreds of metered calls, and a wrong `requires::` edge sends the
        learner to study something they do not need. Both let you look at what
        the gate would do to a handful of concepts before committing to all of
        them."""
        rubrics = self._eval_rubrics_repository.load_named(PREREQUISITE_RUBRICS)
        if not rubrics:
            raise ValueError(
                f"no '{PREREQUISITE_RUBRICS}' rubrics found — the gate cannot run without them"
            )

        outcomes: list[BackfillOutcome] = []
        for concept_id in self._concept_repository.list():
            if limit is not None and len(outcomes) >= limit:
                break
            concept = self._concept_repository.load(ConceptId(str(concept_id)))
            if concept.frontmatter.type in NON_CONTENT_TYPES:
                continue  # scaffolding: nothing requires a Category or a MOC
            if _already_has_edges(concept.body):
                continue  # idempotent: a second run changes nothing

            candidates = self._candidates_for(concept)
            if not candidates:
                continue

            assessments = self._prerequisite_judgement.judge(
                _as_draft(concept), candidates, rubrics
            )
            edges = select_prerequisites(
                source_id=str(concept.id),
                assessments=assessments,
                threshold=self._threshold,
                reachable_by=self._reachable_by(candidates),
            )
            updated = replace(concept, body=add_prerequisite_links(concept.body, edges))
            if updated.body == concept.body:
                continue

            if not dry_run:
                self._concept_repository.save(updated)
                self._index_concept.run(updated)
            outcomes.append(BackfillOutcome(concept_id=str(concept.id), edges=list(edges)))
            logger.info(
                "prerequisites: %s -> %s",
                concept.id,
                {str(e.target_id): e.relation_type for e in edges},
            )
        return outcomes

    def _candidates_for(self, concept: Concept) -> list[PrerequisiteCandidate]:
        """Domain-unscoped, like the ingest path: a prerequisite routinely
        lives outside the dependent's domain, or carries none at all."""
        vector = self._embedding.embed(concept.body)
        candidates = []
        for match in self._vector_search.query(vector, k=self._candidate_k, where=None):
            if str(match.concept_id) == str(concept.id):
                continue  # its own nearest neighbour is itself
            other = self._concept_repository.load(ConceptId(str(match.concept_id)))
            if other.frontmatter.type in NON_CONTENT_TYPES:
                continue
            candidates.append(
                PrerequisiteCandidate(
                    concept_id=other.id,
                    title=other.frontmatter.title,
                    description=other.frontmatter.description,
                )
            )
        return candidates

    def _reachable_by(
        self, candidates: list[PrerequisiteCandidate]
    ) -> dict[str, set[str]]:
        """What each candidate can already reach by following `requires::`.

        `select_prerequisites` uses this to demote an edge that would close a
        cycle. Only the `requires::` tier is walked — `may_require::` is inert,
        and a cycle through edges nothing reads is not a cycle anyone hits.
        Bounded by `cycle_max_hops`, since the graph may already contain one
        from a hand edit."""
        reachable: dict[str, set[str]] = {}
        for candidate in candidates:
            target = str(candidate.concept_id)
            paths = self._metadata_repository.trace_lineage(
                target,
                relation_type=PrerequisiteTier.REQUIRES.value,
                direction="outgoing",
                max_hops=self._cycle_max_hops,
            )
            reachable[target] = {
                _normalize(link.to_id) for path in paths for link in path
            }
        return reachable


def _as_draft(concept: Concept) -> DraftConcept:
    """The skill judges drafts; an existing concept is one that already
    happens to be written."""
    return DraftConcept(
        frontmatter=concept.frontmatter, body=concept.body, source_raw_id=str(concept.id)
    )


def _already_has_edges(body: str) -> bool:
    return any(
        f"{tier.value}:: [[" in body for tier in PrerequisiteTier
    )


def _normalize(raw_target: str) -> str:
    """`[[/id]]` and `[[id.md]]` both name the same concept — the same
    normalization `SqliteMetadataRepository` does when it walks the graph."""
    target = raw_target[1:] if raw_target.startswith("/") else raw_target
    return target[: -len(".md")] if target.endswith(".md") else target
