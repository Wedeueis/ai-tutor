from pipeline.application.use_cases.categorize_concepts import CategorizeConcepts
from pipeline.application.use_cases.category_materializer import CategoryMaterializer
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.agent import CategoryClassificationVerdict
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from tests.application.fakes import (
    FakeBundleLog,
    FakeCategoryClassificationSkill,
    FakeConceptRepository,
    FakeEmbedding,
    FakeMetadataRepository,
    FakeVectorSearch,
)


def _use_case(concept_repository, category_verdict, category_ids=None):
    metadata_repository = FakeMetadataRepository(category_ids=category_ids or [])
    index_concept = IndexConcept(FakeEmbedding(), FakeVectorSearch(), metadata_repository)
    materializer = CategoryMaterializer(concept_repository, index_concept, FakeBundleLog())
    return CategorizeConcepts(
        concept_repository=concept_repository,
        metadata_repository=metadata_repository,
        category_classification=FakeCategoryClassificationSkill(category_verdict),
        category_materializer=materializer,
        index_concept=index_concept,
    )


def test_categorizes_domain_scoped_concepts_lacking_categories():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(
            id=ConceptId("a"),
            frontmatter=Frontmatter(type="Playbook", domain="domains/coffee"),
            body="content",
        )
    )
    use_case = _use_case(
        concept_repository,
        CategoryClassificationVerdict(new_categories=["Brewing Methods"], confidence=0.9),
    )

    count = use_case.run()

    assert count == 1
    updated = concept_repository.load(ConceptId("a"))
    assert "[Brewing Methods](/categories/brewing-methods.md)" in updated.body
    assert concept_repository.exists(ConceptId("categories/brewing-methods"))


def test_skips_concepts_without_a_domain():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="content")
    )
    use_case = _use_case(
        concept_repository,
        CategoryClassificationVerdict(new_categories=["Brewing Methods"], confidence=0.9),
    )

    assert use_case.run() == 0
    assert "## Categories" not in concept_repository.load(ConceptId("a")).body


def test_skips_already_categorized_concepts():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(
            id=ConceptId("a"),
            frontmatter=Frontmatter(type="Playbook", domain="domains/coffee"),
            body="content\n\n## Categories\n\n- [x](/categories/x.md)\n",
        )
    )
    use_case = _use_case(
        concept_repository,
        CategoryClassificationVerdict(new_categories=["Brewing Methods"], confidence=0.9),
    )

    assert use_case.run() == 0


def test_skips_structural_types():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(
            id=ConceptId("domains/coffee"),
            frontmatter=Frontmatter(type="Domain", domain="domains/coffee"),
            body="hub",
        )
    )
    use_case = _use_case(
        concept_repository,
        CategoryClassificationVerdict(new_categories=["Brewing Methods"], confidence=0.9),
    )

    assert use_case.run() == 0


def test_below_threshold_verdict_leaves_concept_unchanged():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(
            id=ConceptId("a"),
            frontmatter=Frontmatter(type="Playbook", domain="domains/coffee"),
            body="content",
        )
    )
    use_case = _use_case(
        concept_repository,
        CategoryClassificationVerdict(new_categories=["Brewing Methods"], confidence=0.1),
    )

    assert use_case.run() == 0
    assert "## Categories" not in concept_repository.load(ConceptId("a")).body
