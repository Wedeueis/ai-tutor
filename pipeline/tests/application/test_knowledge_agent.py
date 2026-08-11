from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import (
    CandidateMatch,
    CategoryClassificationVerdict,
    DisambiguationVerdict,
    DomainClassificationVerdict,
    DraftConcept,
    TypeClassificationVerdict,
)
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.eval import Rubric, RubricContent, RubricScore
from pipeline.domain.raw_material import RawItem
from tests.application.fakes import (
    FakeCategoryClassificationSkill,
    FakeConceptRepository,
    FakeDomainClassificationSkill,
    FakeEmbedding,
    FakeEntityDisambiguationSkill,
    FakeEvalRubricsRepository,
    FakeExtractionSkill,
    FakeMetadataRepository,
    FakeQualityEvalSkill,
    FakeRelatednessSkill,
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
    category_ids=None,
    concept_repository=None,
    eval_rubrics_repository=None,
    relatedness_verdict=None,
    relatedness_min_score=None,
    category_verdict=None,
):
    kwargs = {}
    if relatedness_min_score is not None:
        kwargs["relatedness_min_score"] = relatedness_min_score
    return KnowledgeAgent(
        extraction=FakeExtractionSkill(drafts_by_raw_id),
        embedding=FakeEmbedding(),
        vector_search=FakeVectorSearch(candidates=candidates or []),
        disambiguation=FakeEntityDisambiguationSkill(disambiguation_verdict),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(domain_verdict),
        category_classification=FakeCategoryClassificationSkill(category_verdict),
        quality_eval=FakeQualityEvalSkill(scores),
        relatedness=FakeRelatednessSkill(relatedness_verdict),
        eval_rubrics_repository=eval_rubrics_repository or FakeEvalRubricsRepository(
            base_rubrics=[RUBRIC]
        ),
        metadata_repository=FakeMetadataRepository(
            known_types=known_types or ["Playbook"],
            domain_ids=domain_ids or [],
            category_ids=category_ids or [],
        ),
        concept_repository=concept_repository or FakeConceptRepository(),
        **kwargs,
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
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=existing_id, frontmatter=Frontmatter(type="Playbook", title="Espresso"), body="")
    )
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=existing_id, confidence=0.3),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.4)],
        concept_repository=concept_repository,
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


def test_related_but_not_merged_candidate_gets_linked_into_body():
    from pipeline.domain.agent import RelatedConcept, RelatednessVerdict

    raw = RawItem(id="r1", content="...")
    other_id = ConceptId("qubits")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=other_id, frontmatter=Frontmatter(type="Metric", title="Qubits"), body="")
    )
    agent = KnowledgeAgent(
        extraction=FakeExtractionSkill({"r1": [_draft("r1")]}),
        embedding=FakeEmbedding(),
        vector_search=FakeVectorSearch(candidates=[CandidateMatch(concept_id=other_id, score=0.6)]),
        disambiguation=FakeEntityDisambiguationSkill(
            DisambiguationVerdict(same_as=None, confidence=0.1)
        ),
        type_classification=FakeTypeClassificationSkill(
            TypeClassificationVerdict(resolved_type="Playbook", is_new_type=False)
        ),
        domain_classification=FakeDomainClassificationSkill(NO_DOMAIN),
        category_classification=FakeCategoryClassificationSkill(),
        quality_eval=FakeQualityEvalSkill(PASSING_SCORES),
        relatedness=FakeRelatednessSkill(
            RelatednessVerdict(
                related=[RelatedConcept(concept_id=other_id, title="Qubits", reason="same field")]
            )
        ),
        eval_rubrics_repository=FakeEvalRubricsRepository(base_rubrics=[RUBRIC]),
        metadata_repository=FakeMetadataRepository(known_types=["Playbook"]),
        concept_repository=concept_repository,
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert "## Related" in decision.concept.body
    assert "[Qubits](/qubits.md)" in decision.concept.body
    assert "same field" in decision.concept.body
    assert decision.related == [
        RelatedConcept(concept_id=other_id, title="Qubits", reason="same field")
    ]


def test_no_related_candidates_leaves_body_unchanged():
    raw = RawItem(id="r1", content="...")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
    )

    result = agent.run(raw)

    assert "## Related" not in result.decisions[0].concept.body
    assert result.decisions[0].related == []


def test_candidate_below_min_score_never_reaches_relatedness_skill():
    from pipeline.domain.agent import RelatedConcept, RelatednessVerdict

    raw = RawItem(id="r1", content="...")
    other_id = ConceptId("qubits")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=other_id, frontmatter=Frontmatter(type="Metric", title="Qubits"), body="")
    )
    # The fake would report this as related if it were ever asked — the
    # candidate's score (0.3) is below the 0.5 min-score cutoff, so the
    # relatedness skill should never even be consulted.
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.1),
        candidates=[CandidateMatch(concept_id=other_id, score=0.3)],
        concept_repository=concept_repository,
        relatedness_verdict=RelatednessVerdict(
            related=[RelatedConcept(concept_id=other_id, title="Qubits", reason="same field")]
        ),
        relatedness_min_score=0.5,
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert decision.related == []
    assert "## Related" not in decision.concept.body


def test_low_confidence_domain_leaves_domain_unset():
    raw = RawItem(id="r1", content="...")
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
        domain_verdict=DomainClassificationVerdict(domain=None, confidence=0.1),
    )

    result = agent.run(raw)

    assert result.decisions[0].concept.frontmatter.domain is None


def test_existing_category_assignment_gets_linked_into_body():
    raw = RawItem(id="r1", content="...")
    domain_id = ConceptId("domains/coffee")
    category_id = ConceptId("categories/brewing-methods")
    concept_repository = FakeConceptRepository()
    concept_repository.save(
        Concept(id=domain_id, frontmatter=Frontmatter(type="Domain", title="Coffee"), body="")
    )
    concept_repository.save(
        Concept(
            id=category_id,
            frontmatter=Frontmatter(type="Category", title="Brewing Methods"),
            body="",
        )
    )
    agent = _agent(
        {"r1": [_draft("r1")]},
        DisambiguationVerdict(same_as=None, confidence=0.0),
        domain_verdict=DomainClassificationVerdict(domain=domain_id, confidence=0.95),
        domain_ids=[str(domain_id)],
        category_ids=[str(category_id)],
        concept_repository=concept_repository,
        category_verdict=CategoryClassificationVerdict(
            categories=[category_id], confidence=0.9
        ),
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert "## Categories" in decision.concept.body
    assert "[Brewing Methods](/categories/brewing-methods.md)" in decision.concept.body
    assert decision.new_categories == []


def test_proposed_new_category_carried_on_create_decision():
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
        category_verdict=CategoryClassificationVerdict(
            new_categories=["Extraction Ratios"], confidence=0.9
        ),
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert decision.new_categories == ["Extraction Ratios"]
    # not yet a real concept — KnowledgeAgent never writes; IngestRawMaterial
    # materializes it and links the body itself.
    assert "## Categories" not in decision.concept.body


def test_category_below_confidence_threshold_is_ignored():
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
        category_verdict=CategoryClassificationVerdict(
            new_categories=["Extraction Ratios"], confidence=0.1
        ),
    )

    result = agent.run(raw)

    decision = result.decisions[0]
    assert decision.new_categories == []
    assert "## Categories" not in decision.concept.body


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
        category_classification=FakeCategoryClassificationSkill(),
        quality_eval=CapturingQualityEval(),
        relatedness=FakeRelatednessSkill(),
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
        category_classification=FakeCategoryClassificationSkill(),
        quality_eval=CapturingQualityEval(),
        relatedness=FakeRelatednessSkill(),
        eval_rubrics_repository=FakeEvalRubricsRepository(
            rubrics_by_domain={str(domain_id): [domain_rubric]}
        ),
        metadata_repository=FakeMetadataRepository(domain_ids=[str(domain_id)]),
        concept_repository=concept_repository,
    )

    agent.run(raw)

    assert captured["rubrics"] == [domain_rubric]
