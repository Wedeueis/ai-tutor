from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.rebuild_index import RebuildIndex
from pipeline.application.use_cases.search_concepts import SearchConcepts
from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from tests.application.fakes import (
    FakeConceptRepository,
    FakeEmbedding,
    FakeMetadataRepository,
    FakeVectorSearch,
)


def test_index_concept_upserts_vector_and_metadata():
    vector_search = FakeVectorSearch()
    metadata_repository = FakeMetadataRepository()
    use_case = IndexConcept(FakeEmbedding(), vector_search, metadata_repository)
    concept = Concept(
        id=ConceptId("notes/x"), frontmatter=Frontmatter(type="Playbook"), body="hi"
    )

    use_case.run(concept)

    assert "notes/x" in vector_search.upserted
    assert "notes/x" in metadata_repository.upserted


def test_index_concept_skips_vector_indexing_for_structural_types():
    vector_search = FakeVectorSearch()
    metadata_repository = FakeMetadataRepository()
    use_case = IndexConcept(FakeEmbedding(), vector_search, metadata_repository)

    moc = Concept(id=ConceptId("MOC"), frontmatter=Frontmatter(type="MOC"), body="hub")
    domain = Concept(
        id=ConceptId("domains/coffee"), frontmatter=Frontmatter(type="Domain"), body="hub"
    )
    use_case.run(moc)
    use_case.run(domain)

    # never surfaced as a merge candidate...
    assert "MOC" not in vector_search.upserted
    assert "domains/coffee" not in vector_search.upserted
    # ...but still tracked for domain classification's find_ids_by_type
    assert "MOC" in metadata_repository.upserted
    assert "domains/coffee" in metadata_repository.upserted


def test_rebuild_index_reindexes_every_concept():
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="")
    )
    concept_repository.save(
        Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Playbook"), body="")
    )
    vector_search = FakeVectorSearch()
    metadata_repository = FakeMetadataRepository()
    index_concept = IndexConcept(FakeEmbedding(), vector_search, metadata_repository)

    count = RebuildIndex(concept_repository, index_concept).run()

    assert count == 2
    assert set(vector_search.upserted) == {"a", "b"}


def test_search_concepts_delegates_to_vector_search():
    candidate = CandidateMatch(concept_id=ConceptId("a"), score=0.9)
    vector_search = FakeVectorSearch(candidates=[candidate])
    use_case = SearchConcepts(FakeEmbedding(), vector_search)

    results = use_case.run("query")

    assert results == [candidate]
