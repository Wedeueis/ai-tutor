"""Backfilling prerequisite edges onto concepts that predate the feature."""

import pytest

from pipeline.application.use_cases.backfill_prerequisites import BackfillPrerequisites
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import Concept, ConceptId, Frontmatter, TypedLink
from pipeline.domain.eval import Rubric, RubricContent, RubricScore
from tests.application.fakes import (
    FakeConceptRepository,
    FakeEmbedding,
    FakeEvalRubricsRepository,
    FakeMetadataRepository,
    FakePrerequisiteJudgementSkill,
    FakeVectorSearch,
)

RUBRIC = Rubric("blocks", RubricContent("Must be required."))
PASSING = [RubricScore("blocks", 0.9, "cannot follow without it")]
FAILING = [RubricScore("blocks", 0.2, "merely related")]


def _concept(concept_id: str, concept_type: str = "Playbook", body: str = "Body.") -> Concept:
    return Concept(
        id=ConceptId(concept_id),
        frontmatter=Frontmatter(type=concept_type, title=concept_id),
        body=body,
    )


def _build(
    concepts,
    assessments_by_target,
    candidates=None,
    rubrics=(RUBRIC,),
    lineage_paths=None,
):
    repository = FakeConceptRepository()
    metadata = FakeMetadataRepository(lineage_paths=lineage_paths or [])
    for concept in concepts:
        repository.save(concept)
        metadata.upsert(concept)

    vector_search = FakeVectorSearch(candidates=candidates or [])
    use_case = BackfillPrerequisites(
        concept_repository=repository,
        metadata_repository=metadata,
        embedding=FakeEmbedding(),
        vector_search=vector_search,
        prerequisite_judgement=FakePrerequisiteJudgementSkill(assessments_by_target),
        eval_rubrics_repository=FakeEvalRubricsRepository(
            named_rubrics={"prerequisites": list(rubrics)}
        ),
        index_concept=IndexConcept(FakeEmbedding(), vector_search, metadata),
    )
    return use_case, repository


# --- the happy path ------------------------------------------------------


def test_a_confident_edge_is_written_onto_the_dependent_concept():
    """ADR 0002: the edge lives on the concept that depends, pointing at what
    must be understood first."""
    use_case, repository = _build(
        concepts=[_concept("multi-head-attention"), _concept("scaled-dot-product-attention")],
        candidates=[CandidateMatch(ConceptId("scaled-dot-product-attention"), 0.8)],
        assessments_by_target={"scaled-dot-product-attention": PASSING},
    )

    outcomes = use_case.run()

    # Only the dependent gains an edge: the prerequisite's sole candidate is
    # itself, which is skipped.
    assert [o.concept_id for o in outcomes] == ["multi-head-attention"]
    body = repository.load(ConceptId("multi-head-attention")).body
    assert "requires:: [[/scaled-dot-product-attention]]" in body
    assert "requires::" not in repository.load(
        ConceptId("scaled-dot-product-attention")
    ).body


def test_an_uncertain_edge_lands_in_the_inert_tier():
    use_case, repository = _build(
        concepts=[_concept("cold-brew"), _concept("pour-over")],
        candidates=[CandidateMatch(ConceptId("pour-over"), 0.8)],
        assessments_by_target={"pour-over": FAILING},
    )

    use_case.run()

    body = repository.load(ConceptId("cold-brew")).body
    assert "may_require:: [[/pour-over]]" in body
    assert "requires:: [[/pour-over]]" not in body


# --- what it skips -------------------------------------------------------


def test_a_domainless_concept_is_not_skipped():
    """The one place this deliberately diverges from `CategorizeConcepts`,
    which skips them because a Category vocabulary is domain-scoped. Most of
    this vault has no `domain:`, so skipping would skip the backfill."""
    dependent = _concept("multi-head-attention")
    assert dependent.frontmatter.domain is None

    use_case, repository = _build(
        concepts=[dependent, _concept("scaled-dot-product-attention")],
        candidates=[CandidateMatch(ConceptId("scaled-dot-product-attention"), 0.8)],
        assessments_by_target={"scaled-dot-product-attention": PASSING},
    )

    use_case.run()

    assert "requires::" in repository.load(ConceptId("multi-head-attention")).body


def test_structural_concepts_are_neither_judged_nor_offered():
    """Nothing requires a Category or a MOC, and neither requires anything."""
    use_case, repository = _build(
        concepts=[
            _concept("brewing-methods", "Category"),
            _concept("home", "MOC"),
            _concept("cold-brew"),
        ],
        candidates=[
            CandidateMatch(ConceptId("brewing-methods"), 0.9),
            CandidateMatch(ConceptId("home"), 0.8),
        ],
        assessments_by_target={"brewing-methods": PASSING, "home": PASSING},
    )

    assert use_case.run() == []
    assert "requires::" not in repository.load(ConceptId("brewing-methods")).body
    assert "requires::" not in repository.load(ConceptId("cold-brew")).body


def test_a_concept_is_not_offered_itself_as_a_prerequisite():
    use_case, repository = _build(
        concepts=[_concept("cold-brew")],
        candidates=[CandidateMatch(ConceptId("cold-brew"), 1.0)],
        assessments_by_target={"cold-brew": PASSING},
    )

    assert use_case.run() == []
    assert "requires::" not in repository.load(ConceptId("cold-brew")).body


# --- idempotence ---------------------------------------------------------


def test_a_second_run_changes_nothing():
    use_case, repository = _build(
        concepts=[_concept("multi-head-attention"), _concept("scaled-dot-product-attention")],
        candidates=[CandidateMatch(ConceptId("scaled-dot-product-attention"), 0.8)],
        assessments_by_target={"scaled-dot-product-attention": PASSING},
    )
    use_case.run()
    before = repository.load(ConceptId("multi-head-attention")).body

    assert use_case.run() == []
    assert repository.load(ConceptId("multi-head-attention")).body == before


def test_a_concept_that_already_carries_an_inert_edge_is_left_alone():
    """`may_require::` counts as already judged. Re-running must not quietly
    promote a human's reviewed decision."""
    existing = _concept(
        "cold-brew", body="Body.\n\n## Prerequisites\n\nmay_require:: [[/pour-over]]\n"
    )
    use_case, repository = _build(
        concepts=[existing, _concept("pour-over")],
        candidates=[CandidateMatch(ConceptId("pour-over"), 0.8)],
        assessments_by_target={"pour-over": PASSING},
    )

    use_case.run()

    body = repository.load(ConceptId("cold-brew")).body
    assert "requires:: [[/pour-over]]" not in body
    assert body.count("may_require:: [[/pour-over]]") == 1


# --- cycles --------------------------------------------------------------


def test_an_edge_that_would_close_a_cycle_is_demoted():
    """The case that cannot arise at ingest: these concepts already have
    neighbours, so the existing `requires::` graph has to be consulted."""
    use_case, repository = _build(
        concepts=[_concept("a"), _concept("b")],
        candidates=[CandidateMatch(ConceptId("b"), 0.9)],
        assessments_by_target={"b": PASSING},
        # b already requires a, so a requires b would close the loop.
        lineage_paths=[[TypedLink(from_id="b", to_id="/a", relation_type="requires")]],
    )

    use_case.run()

    assert "may_require:: [[/b]]" in repository.load(ConceptId("a")).body


# --- configuration -------------------------------------------------------


def test_missing_rubrics_stop_the_run_rather_than_silently_emitting_nothing():
    use_case, _ = _build(
        concepts=[_concept("a")], assessments_by_target={}, rubrics=()
    )

    with pytest.raises(ValueError, match="no 'prerequisites' rubrics"):
        use_case.run()


# --- limit and dry run ---------------------------------------------------


def test_a_dry_run_reports_the_edges_without_writing_them():
    """This writes into the graph the study plan walks, and on a cloud
    provider a full pass is hundreds of metered calls — being able to look
    first is the point."""
    use_case, repository = _build(
        concepts=[_concept("multi-head-attention"), _concept("scaled-dot-product-attention")],
        candidates=[CandidateMatch(ConceptId("scaled-dot-product-attention"), 0.8)],
        assessments_by_target={"scaled-dot-product-attention": PASSING},
    )

    outcomes = use_case.run(dry_run=True)

    assert [str(e.target_id) for e in outcomes[0].edges] == ["scaled-dot-product-attention"]
    assert "requires::" not in repository.load(ConceptId("multi-head-attention")).body


def test_a_limit_stops_after_that_many_concepts_gain_edges():
    use_case, repository = _build(
        concepts=[_concept("a"), _concept("b"), _concept("c")],
        candidates=[CandidateMatch(ConceptId("z"), 0.8)],
        assessments_by_target={"z": PASSING},
    )
    # `z` is a candidate the repository also holds, so every concept can gain one.
    repository.save(_concept("z"))

    assert len(use_case.run(limit=2)) == 2


def test_a_dry_run_is_repeatable_because_it_changes_nothing():
    use_case, _ = _build(
        concepts=[_concept("multi-head-attention"), _concept("scaled-dot-product-attention")],
        candidates=[CandidateMatch(ConceptId("scaled-dot-product-attention"), 0.8)],
        assessments_by_target={"scaled-dot-product-attention": PASSING},
    )

    assert use_case.run(dry_run=True) == use_case.run(dry_run=True)
