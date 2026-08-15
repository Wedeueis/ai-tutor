"""Orchestrates every LLM-backed skill over one raw item: extract, classify
domain, find domain-scoped candidates, disambiguate, classify type, evaluate
quality, judge relatedness among non-merged candidates above a minimum
similarity score. Returns create/merge/reject decisions — it does not write
anything itself (see ingest_raw_material.py, which also applies the
resulting `CreateDecision.related` as reciprocal backlinks on the existing
concepts judged related)."""

from __future__ import annotations

import logging
from dataclasses import replace

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.eval_rubrics_repository import EvalRubricsRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.skills.category_classification import (
    CategoryClassificationSkillPort,
)
from pipeline.application.ports.skills.domain_classification import (
    DomainClassificationSkillPort,
)
from pipeline.application.ports.skills.entity_disambiguation import (
    EntityDisambiguationSkillPort,
)
from pipeline.application.ports.skills.extraction import ExtractionSkillPort
from pipeline.application.ports.skills.prerequisite_judgement import (
    PrerequisiteJudgementSkillPort,
)
from pipeline.application.ports.skills.quality_eval import QualityEvalSkillPort
from pipeline.application.ports.skills.relatedness import RelatednessSkillPort
from pipeline.application.ports.skills.type_classification import (
    TypeClassificationSkillPort,
)
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.domain.agent import (
    AgentResult,
    CandidateMatch,
    CategoryCandidate,
    CreateDecision,
    DomainCandidate,
    DraftConcept,
    MergeDecision,
    RejectDecision,
    RelatedConcept,
    RelatednessCandidate,
)
from pipeline.domain.concept import NON_CONTENT_TYPES, ConceptId
from pipeline.domain.eval import DEFAULT_EVAL_THRESHOLD, aggregate_scores
from pipeline.domain.linking import (
    add_category_links,
    add_prerequisite_links,
    add_related_links,
)
from pipeline.domain.prerequisites import (
    PrerequisiteCandidate,
    PrerequisiteEdge,
    select_prerequisites,
)
from pipeline.domain.raw_material import RawItem
from pipeline.domain.slug import slugify

DEFAULT_DISAMBIGUATION_CONFIDENCE_THRESHOLD = 0.75
DEFAULT_RELATEDNESS_MIN_SCORE = 0.5
DEFAULT_CATEGORY_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_PREREQUISITE_THRESHOLD = 0.7
DEFAULT_PREREQUISITE_CANDIDATE_K = 5
PREREQUISITE_RUBRICS = "prerequisites"
DOMAIN_TYPE = "Domain"
CATEGORY_TYPE = "Category"

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    def __init__(
        self,
        extraction: ExtractionSkillPort,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        disambiguation: EntityDisambiguationSkillPort,
        type_classification: TypeClassificationSkillPort,
        domain_classification: DomainClassificationSkillPort,
        category_classification: CategoryClassificationSkillPort,
        quality_eval: QualityEvalSkillPort,
        relatedness: RelatednessSkillPort,
        prerequisite_judgement: PrerequisiteJudgementSkillPort,
        eval_rubrics_repository: EvalRubricsRepositoryPort,
        metadata_repository: MetadataRepositoryPort,
        concept_repository: ConceptRepositoryPort,
        disambiguation_confidence_threshold: float = DEFAULT_DISAMBIGUATION_CONFIDENCE_THRESHOLD,
        eval_threshold: float = DEFAULT_EVAL_THRESHOLD,
        relatedness_min_score: float = DEFAULT_RELATEDNESS_MIN_SCORE,
        category_confidence_threshold: float = DEFAULT_CATEGORY_CONFIDENCE_THRESHOLD,
        prerequisite_threshold: float = DEFAULT_PREREQUISITE_THRESHOLD,
        prerequisite_candidate_k: int = DEFAULT_PREREQUISITE_CANDIDATE_K,
    ) -> None:
        self._extraction = extraction
        self._embedding = embedding
        self._vector_search = vector_search
        self._disambiguation = disambiguation
        self._type_classification = type_classification
        self._domain_classification = domain_classification
        self._category_classification = category_classification
        self._quality_eval = quality_eval
        self._relatedness = relatedness
        self._prerequisite_judgement = prerequisite_judgement
        self._eval_rubrics_repository = eval_rubrics_repository
        self._metadata_repository = metadata_repository
        self._concept_repository = concept_repository
        self._threshold = disambiguation_confidence_threshold
        self._eval_threshold = eval_threshold
        self._relatedness_min_score = relatedness_min_score
        self._category_confidence_threshold = category_confidence_threshold
        self._prerequisite_threshold = prerequisite_threshold
        self._prerequisite_candidate_k = prerequisite_candidate_k

    def run(self, raw: RawItem) -> AgentResult:
        drafts = self._extraction.extract(raw)
        logger.debug("knowledge_agent: raw/%s -> %d draft(s)", raw.id, len(drafts))

        decisions: list[CreateDecision | MergeDecision | RejectDecision] = []
        for draft in drafts:
            domain = self._classify_domain(draft)

            vector = self._embedding.embed(draft.body)
            where = {"domain": str(domain)} if domain is not None else None
            candidates = self._vector_search.query(vector, k=5, where=where)

            merged_into: ConceptId | None = None
            if candidates:
                verdict = self._disambiguation.disambiguate(draft, candidates)
                logger.debug(
                    "knowledge_agent: disambiguation same_as=%s confidence=%.2f (threshold=%.2f)",
                    verdict.same_as,
                    verdict.confidence,
                    self._threshold,
                )
                if verdict.same_as is not None and verdict.confidence >= self._threshold:
                    merged_into = verdict.same_as

            rubrics = self._eval_rubrics_repository.load_for_domain(
                str(domain) if domain is not None else None
            )
            scores = self._quality_eval.evaluate(draft, rubrics, raw.content)
            eval_result = aggregate_scores(scores, threshold=self._eval_threshold)
            logger.debug(
                "knowledge_agent: eval average=%.2f passed=%s (threshold=%.2f)",
                eval_result.average_score,
                eval_result.passed,
                self._eval_threshold,
            )

            if merged_into is not None:
                if eval_result.passed:
                    decisions.append(MergeDecision(into=merged_into, addition=draft.body))
                else:
                    rationale = "; ".join(
                        s.rationale for s in eval_result.scores if s.rationale
                    ) or "quality eval below threshold"
                    decisions.append(RejectDecision(source_raw_id=raw.id, rationale=rationale))
                continue

            known_types = self._metadata_repository.list_distinct_types(
                domain=str(domain) if domain is not None else None
            )
            type_verdict = self._type_classification.classify(draft, known_types)

            # Quality-eval failure never blocks creation — it only withholds
            # domain acceptance, leaving the concept as an unvalidated,
            # domain-less node a future orphan-detection pass can find.
            final_domain = str(domain) if domain is not None and eval_result.passed else None
            related = self._judge_related(draft, candidates)
            body = add_related_links(draft.body, related)

            category_links, new_categories = self._classify_categories(draft, final_domain)
            body = add_category_links(body, category_links)

            prerequisites = self._judge_prerequisites(draft, vector)
            body = add_prerequisite_links(body, prerequisites)

            resolved_draft = replace(
                draft,
                body=body,
                frontmatter=replace(
                    draft.frontmatter,
                    type=type_verdict.resolved_type,
                    domain=final_domain,
                    eval=eval_result,
                ),
            )
            decisions.append(
                CreateDecision(
                    concept=resolved_draft,
                    related=related,
                    new_categories=new_categories,
                    prerequisites=prerequisites,
                )
            )

        return AgentResult(decisions=decisions)

    def _judge_prerequisites(
        self, draft: DraftConcept, vector: list[float]
    ) -> list[PrerequisiteEdge]:
        """Scores which existing concepts the draft genuinely depends on.

        Runs its **own, domain-unscoped** vector search rather than reusing the
        disambiguation candidates. Those are filtered by `domain` when the
        draft has one, but a prerequisite routinely lives outside the
        dependent's domain (linear algebra under a machine-learning concept) or
        carries no domain at all — RF1.1 requires this to work when `domain:`
        is absent, which is the common case in this vault. The embedding is
        reused, so this costs one more search, not one more embed.

        Structural concepts (Category, MOC, Domain, Source Document) are
        dropped: they organise knowledge rather than teach it, so nothing can
        require one.

        No cycle map is passed. A cycle needs an existing path back to the
        source, and a brand-new draft has no incoming edges yet — the backfill
        (`BackfillPrerequisites`), which walks concepts that *do*, supplies one.
        """
        rubrics = self._eval_rubrics_repository.load_named(PREREQUISITE_RUBRICS)
        if not rubrics:
            logger.warning(
                "knowledge_agent: no %s rubrics found; skipping prerequisite emission",
                PREREQUISITE_RUBRICS,
            )
            return []

        matches = self._vector_search.query(vector, k=self._prerequisite_candidate_k, where=None)
        candidates = []
        for match in matches:
            concept = self._concept_repository.load(match.concept_id)
            if concept.frontmatter.type in NON_CONTENT_TYPES:
                continue
            candidates.append(
                PrerequisiteCandidate(
                    concept_id=match.concept_id,
                    title=concept.frontmatter.title,
                    description=concept.frontmatter.description,
                )
            )
        if not candidates:
            return []

        assessments = self._prerequisite_judgement.judge(draft, candidates, rubrics)
        source_id = slugify(draft.frontmatter.title or draft.source_raw_id)
        edges = select_prerequisites(
            source_id=source_id,
            assessments=assessments,
            threshold=self._prerequisite_threshold,
        )
        logger.debug(
            "knowledge_agent: prerequisites %s",
            {str(e.target_id): e.relation_type for e in edges},
        )
        return edges

    def _judge_related(
        self, draft: DraftConcept, candidates: list[CandidateMatch]
    ) -> list[RelatedConcept]:
        """Judges which candidates (already ruled out as the same entity) are
        genuinely related and worth linking to — how clusters emerge in the
        link graph instead of relying on flat tags. Candidates below
        `relatedness_min_score` are filtered out before ever reaching the
        skill, so a sparsely-populated domain can't surface weak matches the
        model might otherwise rationalize post-hoc."""
        strong_candidates = [c for c in candidates if c.score >= self._relatedness_min_score]
        if not strong_candidates:
            return []

        enriched = [
            RelatednessCandidate(
                concept_id=c.concept_id,
                title=self._concept_repository.load(c.concept_id).frontmatter.title,
                score=c.score,
            )
            for c in strong_candidates
        ]
        return self._relatedness.judge(draft, enriched).related

    def _classify_categories(
        self, draft: DraftConcept, domain: str | None
    ) -> tuple[list[RelatedConcept], list[str]]:
        """Existing-category assignments (returned as `RelatedConcept`, ready
        for `add_category_links`) plus any newly-proposed category titles
        (left for `IngestRawMaterial` to materialize, since this use case
        never writes). No domain means no scoped category vocabulary to
        classify against, so categorization is skipped entirely."""
        if domain is None:
            return [], []

        known_category_ids = self._metadata_repository.find_ids_by_type(
            CATEGORY_TYPE, domain=domain
        )
        candidates = []
        for cid in known_category_ids:
            concept = self._concept_repository.load(ConceptId(cid))
            candidates.append(CategoryCandidate(concept_id=concept.id, title=concept.frontmatter.title))

        verdict = self._category_classification.classify(draft, candidates)
        if verdict.confidence < self._category_confidence_threshold:
            return [], []

        titles_by_id = {c.concept_id: c.title for c in candidates}
        links = [
            RelatedConcept(concept_id=cid, title=titles_by_id.get(cid))
            for cid in verdict.categories
        ]
        return links, verdict.new_categories

    def _classify_domain(self, draft: DraftConcept) -> ConceptId | None:
        domain_ids = self._metadata_repository.find_ids_by_type(DOMAIN_TYPE)
        if not domain_ids:
            return None

        candidates = []
        for domain_id in domain_ids:
            concept = self._concept_repository.load(ConceptId(domain_id))
            candidates.append(
                DomainCandidate(
                    concept_id=concept.id,
                    title=concept.frontmatter.title,
                    description=concept.frontmatter.description,
                )
            )

        verdict = self._domain_classification.classify(draft, candidates)
        return verdict.domain
