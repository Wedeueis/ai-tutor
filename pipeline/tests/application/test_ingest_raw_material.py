from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.ingest_raw_material import IngestRawMaterial
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import (
    CandidateMatch,
    DisambiguationVerdict,
    DomainClassificationVerdict,
    DraftConcept,
    TypeClassificationVerdict,
)
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.eval import Rubric, RubricContent, RubricScore
from pipeline.domain.raw_material import RawItem
from tests.application.fakes import (
    FakeBundleLog,
    FakeConceptRepository,
    FakeDomainClassificationSkill,
    FakeEmbedding,
    FakeEntityDisambiguationSkill,
    FakeEvalRubricsRepository,
    FakeExtractionSkill,
    FakeMetadataRepository,
    FakeQualityEvalSkill,
    FakeRawMaterialRepository,
    FakeTypeClassificationSkill,
    FakeVectorSearch,
)

RUBRIC = Rubric("traceable", RubricContent("Claims must be grounded in the source."))
PASSING_SCORES = [RubricScore("traceable", 0.9, "grounded")]
FAILING_SCORES = [RubricScore("traceable", 0.1, "not grounded in the source")]


def _build(
    raw_items,
    drafts_by_raw_id,
    existing_concepts=None,
    scores=PASSING_SCORES,
    disambiguation_verdict=None,
    candidates=None,
):
    concept_repository = FakeConceptRepository()
    for concept in existing_concepts or []:
        concept_repository.save(concept)

    metadata_repository = FakeMetadataRepository(known_types=["Playbook"])
    vector_search = FakeVectorSearch(candidates=candidates or [])
    embedding = FakeEmbedding()
    index_concept = IndexConcept(embedding, vector_search, metadata_repository)

    agent = KnowledgeAgent(
        extraction=FakeExtractionSkill(drafts_by_raw_id),
        embedding=embedding,
        vector_search=vector_search,
        disambiguation=FakeEntityDisambiguationSkill(
            disambiguation_verdict or DisambiguationVerdict(same_as=None, confidence=0.0)
        ),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(
            DomainClassificationVerdict(domain=None, confidence=0.0)
        ),
        quality_eval=FakeQualityEvalSkill(scores),
        eval_rubrics_repository=FakeEvalRubricsRepository(base_rubrics=[RUBRIC]),
        metadata_repository=metadata_repository,
        concept_repository=concept_repository,
    )

    raw_material_repository = FakeRawMaterialRepository(raw_items)
    bundle_log = FakeBundleLog()

    use_case = IngestRawMaterial(
        raw_material_repository=raw_material_repository,
        knowledge_agent=agent,
        concept_repository=concept_repository,
        index_concept=index_concept,
        bundle_log=bundle_log,
    )
    return use_case, concept_repository, raw_material_repository, bundle_log


def test_ingest_creates_a_new_draft_concept_and_marks_raw_processed():
    raw = RawItem(id="raw-1", content="Espresso ratio is 1:2.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso Ratio"),
        body="Espresso ratio is 1:2.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, raw_material_repository, bundle_log = _build(
        [raw], {"raw-1": [draft]}
    )

    outcomes = use_case.run()

    assert len(outcomes) == 1
    assert outcomes[0].created == [ConceptId("espresso-ratio")]
    saved = concept_repository.load(ConceptId("espresso-ratio"))
    assert saved.frontmatter.status is None or saved.frontmatter.type == "Playbook"
    assert saved.frontmatter.type == "Playbook"
    assert raw_material_repository.processed == ["raw-1"]
    assert len(bundle_log.entries) == 1
    assert "Creation" in bundle_log.entries[0]


def test_ingest_avoids_id_collision():
    existing = Concept(
        id=ConceptId("espresso-ratio"),
        frontmatter=Frontmatter(type="Playbook", title="Espresso Ratio"),
        body="existing",
    )
    raw = RawItem(id="raw-1", content="Espresso ratio is 1:2.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso Ratio"),
        body="new content",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw], {"raw-1": [draft]}, existing_concepts=[existing]
    )

    outcomes = use_case.run()

    assert outcomes[0].created == [ConceptId("espresso-ratio-2")]
    assert concept_repository.exists(ConceptId("espresso-ratio"))
    assert concept_repository.exists(ConceptId("espresso-ratio-2"))


def test_failing_eval_on_new_draft_still_creates_it_domainless_and_marks_processed():
    raw = RawItem(id="raw-1", content="garbled nonsense")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Garbled"),
        body="garbled nonsense",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, raw_material_repository, bundle_log = _build(
        [raw], {"raw-1": [draft]}, scores=FAILING_SCORES
    )

    outcomes = use_case.run()

    assert outcomes[0].created == [ConceptId("garbled")]
    assert outcomes[0].rejected == []
    saved = concept_repository.load(ConceptId("garbled"))
    assert saved.frontmatter.domain is None
    assert saved.frontmatter.eval.passed is False
    assert raw_material_repository.processed == ["raw-1"]
    assert raw_material_repository.rejected == {}
    assert any("Creation" in entry for entry in bundle_log.entries)


def test_failing_eval_on_merge_rejects_and_moves_raw_item_to_rejected():
    existing_id = ConceptId("coffee/espresso")
    existing = Concept(
        id=existing_id, frontmatter=Frontmatter(type="Playbook", title="Espresso"), body="existing"
    )
    raw = RawItem(id="raw-1", content="garbled nonsense")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Garbled"),
        body="garbled nonsense",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, raw_material_repository, bundle_log = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[existing],
        scores=FAILING_SCORES,
        disambiguation_verdict=DisambiguationVerdict(same_as=existing_id, confidence=0.95),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
    )

    outcomes = use_case.run()

    assert outcomes[0].created == []
    assert outcomes[0].merged_into == []
    assert outcomes[0].rejected != []
    assert raw_material_repository.processed == []
    assert raw_material_repository.rejected != {}
    assert any("Rejected" in entry for entry in bundle_log.entries)


def test_nothing_extracted_still_marks_processed_not_rejected():
    raw = RawItem(id="raw-1", content="nothing useful here")
    use_case, _, raw_material_repository, bundle_log = _build([raw], {"raw-1": []})

    outcomes = use_case.run()

    assert outcomes[0].created == []
    assert outcomes[0].rejected == []
    assert raw_material_repository.processed == ["raw-1"]
    assert raw_material_repository.rejected == {}
    assert bundle_log.entries == []
