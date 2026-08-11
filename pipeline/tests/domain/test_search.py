from pipeline.domain.concept import ConceptId
from pipeline.domain.search import reciprocal_rank_fusion


def test_rrf_ranks_single_list_by_position():
    results = reciprocal_rank_fusion([ConceptId("a"), ConceptId("b")])
    assert [r.concept_id for r in results] == [ConceptId("a"), ConceptId("b")]
    assert results[0].score > results[1].score


def test_rrf_boosts_concept_appearing_in_multiple_lists():
    results = reciprocal_rank_fusion(
        [ConceptId("a"), ConceptId("b")],
        [ConceptId("b"), ConceptId("a")],
    )
    # "a" is rank 1 in list one and rank 2 in list two; "b" is rank 2 then
    # rank 1 — symmetric, so both accumulate the same total score.
    assert results[0].score == results[1].score


def test_rrf_merges_disjoint_lists():
    results = reciprocal_rank_fusion([ConceptId("a")], [ConceptId("b")])
    assert {r.concept_id for r in results} == {ConceptId("a"), ConceptId("b")}


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion() == []
    assert reciprocal_rank_fusion([]) == []
