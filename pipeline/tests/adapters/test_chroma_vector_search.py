from pipeline.adapters.chroma.chroma_vector_search import ChromaVectorSearch
from pipeline.domain.concept import ConceptId


def test_query_on_empty_collection_returns_no_matches(tmp_path):
    store = ChromaVectorSearch(tmp_path)
    assert store.query([0.1, 0.2, 0.3]) == []


def test_upsert_then_query_returns_the_match(tmp_path):
    store = ChromaVectorSearch(tmp_path)
    store.upsert("a", [1.0, 0.0, 0.0], metadata={"type": "Playbook"})
    store.upsert("b", [0.0, 1.0, 0.0], metadata={"type": "Metric"})

    matches = store.query([1.0, 0.0, 0.0], k=1)

    assert len(matches) == 1
    assert matches[0].concept_id == ConceptId("a")


def test_query_with_where_filter_scopes_results(tmp_path):
    store = ChromaVectorSearch(tmp_path)
    store.upsert("a", [1.0, 0.0, 0.0], metadata={"domain": "domains/coffee"})
    store.upsert("b", [1.0, 0.0, 0.0], metadata={"domain": "domains/finance"})

    matches = store.query([1.0, 0.0, 0.0], k=5, where={"domain": "domains/coffee"})

    assert [m.concept_id for m in matches] == [ConceptId("a")]


def test_delete_removes_from_results(tmp_path):
    store = ChromaVectorSearch(tmp_path)
    store.upsert("a", [1.0, 0.0, 0.0], metadata={})
    store.delete("a")

    assert store.query([1.0, 0.0, 0.0]) == []
