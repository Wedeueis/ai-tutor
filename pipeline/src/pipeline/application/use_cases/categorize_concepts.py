"""Backfills category links for concepts that predate the Category ontology
(`pipeline categorize`) — everything already in the vault before this
feature shipped. Same classify-then-link shape `KnowledgeAgent` runs at
ingest time, just walking the whole bundle instead of one fresh draft."""

from __future__ import annotations

from dataclasses import replace

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.skills.category_classification import (
    CategoryClassificationSkillPort,
)
from pipeline.application.use_cases.category_materializer import CategoryMaterializer
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.agent import CategoryCandidate, DraftConcept, RelatedConcept
from pipeline.domain.concept import NON_CONTENT_TYPES, ConceptId
from pipeline.domain.linking import add_category_links

DEFAULT_CATEGORY_CONFIDENCE_THRESHOLD = 0.6
_CATEGORIES_HEADING = "## Categories"
_CATEGORY_TYPE = "Category"


class CategorizeConcepts:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        metadata_repository: MetadataRepositoryPort,
        category_classification: CategoryClassificationSkillPort,
        category_materializer: CategoryMaterializer,
        index_concept: IndexConcept,
        category_confidence_threshold: float = DEFAULT_CATEGORY_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._concept_repository = concept_repository
        self._metadata_repository = metadata_repository
        self._category_classification = category_classification
        self._category_materializer = category_materializer
        self._index_concept = index_concept
        self._threshold = category_confidence_threshold

    def run(self) -> int:
        count = 0
        for concept_id in self._concept_repository.list():
            concept = self._concept_repository.load(concept_id)
            if concept.frontmatter.type in NON_CONTENT_TYPES:
                continue
            if concept.frontmatter.domain is None:
                continue  # no domain to scope a category vocabulary against
            if _CATEGORIES_HEADING in concept.body:
                continue  # already categorized

            domain = concept.frontmatter.domain
            candidates = self._known_categories(domain)
            draft = DraftConcept(
                frontmatter=concept.frontmatter, body=concept.body, source_raw_id=str(concept_id)
            )
            verdict = self._category_classification.classify(draft, candidates)
            if verdict.confidence < self._threshold:
                continue

            titles_by_id = {c.concept_id: c.title for c in candidates}
            links = [
                RelatedConcept(concept_id=cid, title=titles_by_id.get(cid))
                for cid in verdict.categories
            ]
            updated = replace(concept, body=add_category_links(concept.body, links))
            updated = self._category_materializer.link_new_categories(
                updated, verdict.new_categories, raw_id=None
            )
            if updated.body == concept.body:
                continue

            self._concept_repository.save(updated)
            self._index_concept.run(updated)
            count += 1
        return count

    def _known_categories(self, domain: str) -> list[CategoryCandidate]:
        known_category_ids = self._metadata_repository.find_ids_by_type(
            _CATEGORY_TYPE, domain=domain
        )
        candidates = []
        for cid in known_category_ids:
            concept = self._concept_repository.load(ConceptId(cid))
            candidates.append(CategoryCandidate(concept_id=concept.id, title=concept.frontmatter.title))
        return candidates
