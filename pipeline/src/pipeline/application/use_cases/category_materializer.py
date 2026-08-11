"""Shared by `IngestRawMaterial` and `CategorizeConcepts`: turns a
classification skill's proposed-new-category titles into real `type:
Category` concepts and links a concept's body to them. Not a use case on its
own — a small collaborator, since both callers need the identical
find-or-create-by-slug + link + audit-log shape."""

from __future__ import annotations

from dataclasses import replace

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.agent import RelatedConcept
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.linking import add_category_links
from pipeline.domain.slug import slugify

_CATEGORY_TYPE = "Category"


class CategoryMaterializer:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        index_concept: IndexConcept,
        bundle_log: BundleLogPort,
    ) -> None:
        self._concept_repository = concept_repository
        self._index_concept = index_concept
        self._bundle_log = bundle_log

    def link_new_categories(
        self, concept: Concept, new_category_titles: list[str], raw_id: str | None
    ) -> Concept:
        if not new_category_titles:
            return concept
        links = [
            RelatedConcept(
                concept_id=self.find_or_create(title, concept.frontmatter.domain, raw_id),
                title=title,
            )
            for title in new_category_titles
        ]
        return replace(concept, body=add_category_links(concept.body, links))

    def find_or_create(self, title: str, domain: str | None, raw_id: str | None) -> ConceptId:
        base = slugify(title)
        category_id = ConceptId(f"categories/{base}")
        suffix = 2
        while self._concept_repository.exists(category_id):
            existing = self._concept_repository.load(category_id)
            if existing.frontmatter.title == title:
                return category_id
            category_id = ConceptId(f"categories/{base}-{suffix}")
            suffix += 1

        category = Concept(
            id=category_id,
            frontmatter=Frontmatter(type=_CATEGORY_TYPE, title=title, domain=domain),
            body=f"# {title}\n\n*(no concepts yet — links accumulate here as they're categorized)*\n",
        )
        self._concept_repository.save(category)
        self._index_concept.run(category)
        self._bundle_log.append(
            action="create",
            concept_id=str(category_id),
            raw_id=raw_id,
            message=f"Added Category {title}.",
        )
        return category_id
