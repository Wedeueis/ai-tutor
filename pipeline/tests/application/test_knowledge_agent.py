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
    FakeConceptRepository,
    FakeDomainClassificationSkill,
    FakeEmbedding,
    FakeEntityDisambiguationSkill,
    FakeEvalRubricsRepository,
    FakeExtractionSkill,
    FakeMetadataRepository,
    FakeQualityEvalSkill,
    FakeTypeClassificationSkill,
    FakeVectorSearch,
)

RUBRIC = Rubric("traceable", RubricContent("Claims must be grounded in the source."))
PASSING_SCORES = [RubricScore("traceable", 0.9, "grounded")]
FAILING_SCORES = [RubricScore("traceable", 0.1, "not grounded in the source")]
NO_DOMAIN = DomainClassificationVerdict(domain=None, confidence=0.0)


def _draft(raw_id: str) -> DraftConcept:
    return DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso extraction"),
        body="Notes about espresso extraction ratios.",
        source_raw_id=raw_id,
    )


def _agent(
    drafts_by_raw_id,
    disambiguation_verdict,
    candidates=None,
    domain_verdict=NO_DOMAIN,
    scores=PASSING_SCORES,
    known_types=None,
    domain_ids=None,
    concept_repository=None,
    eval_rubrics_repository=None,
):
    return KnowledgeAgent(
        extraction=FakeExtractionSkill(drafts_by_raw_id),
        embedding=FakeEmbedding(),
        vector_search=FakeVectorSearch(candidates=candidates or []),
        disambiguation=FakeEntityDisambiguationSkill(disambiguation_verdict),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(domain_verdict),
        quality_eval=FakeQualityEvalSkill(scores),
        eval_rubrics_repository=eval_rubrics_repository or FakeEvalRubricsRepository(
            base_rubrics=[RUBRIC]
        ),
        metadata_repository=FakeMetadataRepository(
            known_types=known_types or ["Playbook"], domain_ids=domain_ids or []
        ),
        concept_repository=concept_repository or FakeConceptRepository(),
    )


def test_no_candidates_creates_new_concept():
    raw = RawItem(id="r1", content="...")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
    )

    result = agent.run(raw)

    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision.concept.frontmatter.type == "Playbook"


def test_high_confidence_match_merges_instead_of_creating():
    raw = RawItem(id="r1", content="...")
    existing_id = ConceptId("coffee/espresso")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=existing_id, confidence=0.95),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
    )

    result = agent.run(raw)

    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision.into == existing_id


def test_low_confidence_match_still_creates_new_concept():
    raw = RawItem(id="r1", content="...")
    existing_id = ConceptId("coffee/espresso")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=existing_id, confidence=0.3),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.4)],
    )

    result = agent.run(raw)

    assert len(result.decisions) == 1
    assert hasattr(result.decisions[0], "concept")


def test_failing_eval_on_new_draft_still_creates_but_withholds_domain():
    raw = RawItem(id="r1", content="garbled nonsense")
    domain_id = ConceptId("domains/coffee")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=domain_id, frontmatter=Frontmatter(type="Domain", title="Coffee"), body="")
    )
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
        domain_verdict=DomainClassificationVerdict(domain=domain_id, confidence=0.95),
        domain_ids=[str(domain_id)],
        concept_repository=concept_repository,
        scores=FAILING_SCORES,
    )

    result = agent.run(raw)

    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert hasattr(decision, "concept")  # still a CreateDecision, not a reject
    assert decision.concept.frontmatter.domain is None
    assert decision.concept.frontmatter.eval.passed is False
    assert decision.concept.frontmatter.type == "Playbook"  # type unaffected


def test_passing_eval_on_new_draft_keeps_domain_and_stamps_eval():
    raw = RawItem(id="r1", content="...")
    domain_id = ConceptId("domains/coffee")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=domain_id, frontmatter=Frontmatter(type="Domain", title="Coffee"), body="")
    )
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
        domain_verdict=DomainClassificationVerdict(domain=domain_id, confidence=0.95),
        domain_ids=[str(domain_id)],
        concept_repository=concept_repository,
        scores=PASSING_SCORES,
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert decision.concept.frontmatter.domain == str(domain_id)
    assert decision.concept.frontmatter.eval.passed is True


def test_failing_eval_on_merge_still_rejects_the_addition():
    raw = RawItem(id="r1", content="...")
    existing_id = ConceptId("coffee/espresso")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=existing_id, confidence=0.95),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
        scores=FAILING_SCORES,
    )

    result = agent.run(raw)

    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision.source_raw_id == "r1"


def test_low_confidence_domain_leaves_domain_unset():
    raw = RawItem(id="r1", content="...")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
        domain_verdict=DomainClassificationVerdict(domain=None, confidence=0.1),
    )

    result = agent.run(raw)

    assert result.decisions[0].concept.frontmatter.domain is None


def test_eval_rubrics_fall_back_to_base_when_domain_has_none():
    raw = RawItem(id="r1", content="...")
    domain_id = ConceptId("domains/coffee")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=domain_id, frontmatter=Frontmatter(type="Domain", title="Coffee"), body="")
    )

    captured = {}

    class CapturingQualityEval:
        def evaluate(self, draft, rubrics, raw_content):
            captured["rubrics"] = rubrics
            return PASSING_SCORES

    base_rubric = Rubric("base", RubricContent("Base rubric."))
    agent = KnowledgeAgent(
        extraction=FakeExtractionSkill({"r1": [_draft("r1")]}),
        embedding=FakeEmbedding(),
        vector_search=FakeVectorSearch(),
        disambiguation=FakeEntityDisambiguationSkill(
            DisambiguationVerdict(same_as=None, confidence=0.0)
        ),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(
            DomainClassificationVerdict(domain=domain_id, confidence=0.9)
        ),
        quality_eval=CapturingQualityEval(),
        eval_rubrics_repository=FakeEvalRubricsRepository(base_rubrics=[base_rubric]),
        metadata_repository=FakeMetadataRepository(domain_ids=[str(domain_id)]),
        concept_repository=concept_repository,
    )

    agent.run(raw)

    assert captured["rubrics"] == [base_rubric]


def test_eval_rubrics_use_domain_specific_file_when_present():
    raw = RawItem(id="r1", content="...")
    domain_id = ConceptId("domains/coffee")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=domain_id, frontmatter=Frontmatter(type="Domain", title="Coffee"), body="")
    )

    captured = {}

    class CapturingQualityEval:
        def evaluate(self, draft, rubrics, raw_content):
            captured["rubrics"] = rubrics
            return PASSING_SCORES

    domain_rubric = Rubric("coffee_specific", RubricContent("Domain-specific rubric."))
    agent = KnowledgeAgent(
        extraction=FakeExtractionSkill({"r1": [_draft("r1")]}),
        embedding=FakeEmbedding(),
        vector_search=FakeVectorSearch(),
        disambiguation=FakeEntityDisambiguationSkill(
            DisambiguationVerdict(same_as=None, confidence=0.0)
        ),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(
            DomainClassificationVerdict(domain=domain_id, confidence=0.9)
        ),
        quality_eval=CapturingQualityEval(),
        eval_rubrics_repository=FakeEvalRubricsRepository(
            rubrics_by_domain={str(domain_id): [domain_rubric]}
        ),
        metadata_repository=FakeMetadataRepository(domain_ids=[str(domain_id)]),
        concept_repository=concept_repository,
    )

    agent.run(raw)

    assert captured["rubrics"] == [domain_rubric]
