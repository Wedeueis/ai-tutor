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


def test_search_concepts_stage0_returns_structured_hits_directly():
    vector_search = FakeVectorSearch(candidates=[])
    metadata_repository = FakeMetadataRepository(structured_ids=["a", "b", "c"])
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository)

    results = use_case.run("query", type="Decision")

    assert [r.concept_id for r in results] == [ConceptId("a"), ConceptId("b"), ConceptId("c")]
    assert all(r.score == 1.0 for r in results)


def test_search_concepts_falls_back_to_hybrid_when_structured_hits_are_too_few():
    semantic_hit = CandidateMatch(concept_id=ConceptId("semantic-hit"), score=0.9)
    vector_search = FakeVectorSearch(candidates=[semantic_hit])
    metadata_repository = FakeMetadataRepository(structured_ids=["a"])  # below default min of 3
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository)

    results = use_case.run("query", type="Decision")

    assert ConceptId("semantic-hit") in [r.concept_id for r in results]


def test_search_concepts_ranks_semantic_hit_first():
    candidate = CandidateMatch(concept_id=ConceptId("a"), score=0.9)
    vector_search = FakeVectorSearch(candidates=[candidate])
    use_case = SearchConcepts(FakeEmbedding(), vector_search, FakeMetadataRepository())

    results = use_case.run("query")

    assert [r.concept_id for r in results] == [ConceptId("a")]


def test_search_concepts_surfaces_lexical_only_match():
    vector_search = FakeVectorSearch(candidates=[])
    lexical_hit = CandidateMatch(concept_id=ConceptId("lexical-only"), score=1.0)
    metadata_repository = FakeMetadataRepository(fts_candidates=[lexical_hit])
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository)

    results = use_case.run("query")

    assert ConceptId("lexical-only") in [r.concept_id for r in results]


def test_search_concepts_surfaces_graph_only_match():
    vector_search = FakeVectorSearch(candidates=[CandidateMatch(concept_id=ConceptId("a"), score=0.9)])
    metadata_repository = FakeMetadataRepository(neighbors={"graph-neighbor": 0.4})
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository)

    results = use_case.run("query")

    assert ConceptId("graph-neighbor") in [r.concept_id for r in results]


def test_search_concepts_boosts_a_fused_hit_thats_also_graph_connected():
    # "b" ranks second in the semantic leg (so it's part of stage 1's fused
    # output but, with graph_seed_k=1, isn't itself a graph-expansion seed —
    # seeds are excluded from expand_neighbors, so only a non-seed fused hit
    # can also show up in the graph leg).
    vector_search = FakeVectorSearch(
        candidates=[
            CandidateMatch(concept_id=ConceptId("a"), score=0.9),
            CandidateMatch(concept_id=ConceptId("b"), score=0.1),
        ]
    )
    fused_only = SearchConcepts(
        FakeEmbedding(), vector_search, FakeMetadataRepository(), graph_seed_k=1
    ).run("query")
    fused_only_score_b = next(r.score for r in fused_only if r.concept_id == ConceptId("b"))

    metadata_repository = FakeMetadataRepository(neighbors={"b": 0.4})
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository, graph_seed_k=1)

    results = use_case.run("query")

    result_b = next(r for r in results if r.concept_id == ConceptId("b"))
    # Boosted multiplicatively (bounded to at most 2x, at graph_score=1.0),
    # never just replaced by the graph-decay score outright — RRF and
    # hop-decay scores are on very different scales, so naively taking
    # max() would let graph expansion dominate the whole ranking instead of
    # reranking within it.
    assert result_b.score == fused_only_score_b * 1.4


def test_search_concepts_graph_only_hit_never_outranks_a_fused_hit():
    vector_search = FakeVectorSearch(candidates=[CandidateMatch(concept_id=ConceptId("a"), score=0.9)])
    # A large decay score (bigger than any RRF score) that would previously
    # have let this graph-only concept rank #1 via max().
    metadata_repository = FakeMetadataRepository(neighbors={"graph-neighbor": 0.9})
    use_case = SearchConcepts(FakeEmbedding(), vector_search, metadata_repository)

    results = use_case.run("query")

    assert [r.concept_id for r in results] == [ConceptId("a"), ConceptId("graph-neighbor")]
