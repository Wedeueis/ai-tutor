from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.ingest_raw_material import IngestRawMaterial
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import (
    AgentResult,
    CandidateMatch,
    CreateDecision,
    DisambiguationVerdict,
    DomainClassificationVerdict,
    DraftConcept,
    RelatedConcept,
    RelatednessVerdict,
    TypeClassificationVerdict,
)
from pipeline.domain.concept import Concept, ConceptId, Frontmatter, Source
from pipeline.domain.eval import Rubric, RubricContent, RubricScore
from pipeline.domain.raw_material import RawItem
from tests.application.fakes import (
    FakeBundleLog,
    FakeCategoryClassificationSkill,
    FakeConceptRepository,
    FakeDomainClassificationSkill,
    FakeEmbedding,
    FakeEntityDisambiguationSkill,
    FakeEvalRubricsRepository,
    FakeExtractionSkill,
    FakeMetadataRepository,
    FakePrerequisiteJudgementSkill,
    FakeQualityEvalSkill,
    FakeRawMaterialRepository,
    FakeRelatednessSkill,
    FakeRelevanceEvidence,
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
    relatedness_verdict=None,
    source_concepts=None,
    prerequisite_skill=None,
    prerequisite_rubrics=None,
    relevance_evidence=None,
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
        category_classification=FakeCategoryClassificationSkill(),
        quality_eval=FakeQualityEvalSkill(scores),
        relatedness=FakeRelatednessSkill(relatedness_verdict),
        prerequisite_judgement=prerequisite_skill or FakePrerequisiteJudgementSkill(),
        relevance_evidence=relevance_evidence or FakeRelevanceEvidence(),
        eval_rubrics_repository=FakeEvalRubricsRepository(
            base_rubrics=[RUBRIC],
            named_rubrics={"prerequisites": prerequisite_rubrics or []},
        ),
        metadata_repository=metadata_repository,
        concept_repository=concept_repository,
    )

    raw_material_repository = FakeRawMaterialRepository(raw_items, source_concepts=source_concepts)
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
    assert bundle_log.entries[0]["action"] == "create"


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


class _StubAgentWithNewCategories:
    """Bypasses KnowledgeAgent entirely to exercise IngestRawMaterial's
    new-category materialization in isolation, decoupled from any
    particular classification-skill wiring."""

    def __init__(self, draft: DraftConcept, new_categories: list[str]) -> None:
        self._draft = draft
        self._new_categories = new_categories

    def run(self, raw: RawItem) -> AgentResult:
        return AgentResult(
            decisions=[CreateDecision(concept=self._draft, new_categories=self._new_categories)]
        )


def test_new_category_gets_materialized_and_linked():
    raw = RawItem(id="raw-1", content="Espresso ratio is 1:2.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Playbook", title="Espresso Ratio", domain="domains/coffee"),
        body="Espresso ratio is 1:2.",
        source_raw_id="raw-1",
    )
    concept_repository = FakeConceptRepository()
    metadata_repository = FakeMetadataRepository()
    vector_search = FakeVectorSearch()
    embedding = FakeEmbedding()
    index_concept = IndexConcept(embedding, vector_search, metadata_repository)
    bundle_log = FakeBundleLog()
    use_case = IngestRawMaterial(
        raw_material_repository=FakeRawMaterialRepository([raw], source_concepts=None),
        knowledge_agent=_StubAgentWithNewCategories(draft, ["Extraction Ratios"]),
        concept_repository=concept_repository,
        index_concept=index_concept,
        bundle_log=bundle_log,
    )

    outcomes = use_case.run()

    assert outcomes[0].created == [ConceptId("espresso-ratio")]
    category = concept_repository.load(ConceptId("categories/extraction-ratios"))
    assert category.frontmatter.type == "Category"
    assert category.frontmatter.title == "Extraction Ratios"
    assert category.frontmatter.domain == "domains/coffee"

    concept = concept_repository.load(ConceptId("espresso-ratio"))
    assert "[Extraction Ratios](/categories/extraction-ratios.md)" in concept.body

    actions = [entry["action"] for entry in bundle_log.entries]
    assert actions.count("create") == 2  # the concept, and the new Category


def test_two_drafts_proposing_the_same_new_category_share_one_concept():
    raw1 = RawItem(id="raw-1", content="A")
    raw2 = RawItem(id="raw-2", content="B")
    draft1 = DraftConcept(
        frontmatter=Frontmatter(type="Playbook", title="Draft One", domain="domains/coffee"),
        body="A",
        source_raw_id="raw-1",
    )
    draft2 = DraftConcept(
        frontmatter=Frontmatter(type="Playbook", title="Draft Two", domain="domains/coffee"),
        body="B",
        source_raw_id="raw-2",
    )
    concept_repository = FakeConceptRepository()
    metadata_repository = FakeMetadataRepository()
    vector_search = FakeVectorSearch()
    embedding = FakeEmbedding()
    index_concept = IndexConcept(embedding, vector_search, metadata_repository)

    class _StubAgentSequence:
        def __init__(self, drafts: dict[str, DraftConcept]) -> None:
            self._drafts = drafts

        def run(self, raw: RawItem) -> AgentResult:
            return AgentResult(
                decisions=[
                    CreateDecision(concept=self._drafts[raw.id], new_categories=["Extraction Ratios"])
                ]
            )

    use_case = IngestRawMaterial(
        raw_material_repository=FakeRawMaterialRepository([raw1, raw2], source_concepts=None),
        knowledge_agent=_StubAgentSequence({"raw-1": draft1, "raw-2": draft2}),
        concept_repository=concept_repository,
        index_concept=index_concept,
        bundle_log=FakeBundleLog(),
    )

    use_case.run()

    assert concept_repository.exists(ConceptId("categories/extraction-ratios"))
    assert not concept_repository.exists(ConceptId("categories/extraction-ratios-2"))


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
    assert any(entry["action"] == "create" for entry in bundle_log.entries)


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
    assert any(entry["action"] == "reject" for entry in bundle_log.entries)


def test_nothing_extracted_still_marks_processed_not_rejected():
    raw = RawItem(id="raw-1", content="nothing useful here")
    use_case, _, raw_material_repository, bundle_log = _build([raw], {"raw-1": []})

    outcomes = use_case.run()

    assert outcomes[0].created == []
    assert outcomes[0].rejected == []
    assert raw_material_repository.processed == ["raw-1"]
    assert raw_material_repository.rejected == {}
    assert bundle_log.entries == []


def test_create_writes_reciprocal_backlink_into_related_existing_concept():
    existing_id = ConceptId("qubits")
    existing = Concept(
        id=existing_id, frontmatter=Frontmatter(type="Metric", title="Qubits"), body="About qubits."
    )
    raw = RawItem(id="raw-1", content="Quantum computers use qubits.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Quantum Computers"),
        body="Quantum computers are powerful.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, bundle_log = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[existing],
        disambiguation_verdict=DisambiguationVerdict(same_as=None, confidence=0.1),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
        relatedness_verdict=RelatednessVerdict(
            related=[RelatedConcept(concept_id=existing_id, title="Qubits", reason="Same field.")]
        ),
    )

    outcomes = use_case.run()

    new_concept_id = outcomes[0].created[0]
    updated_existing = concept_repository.load(existing_id)
    assert f"(/{new_concept_id}.md)" in updated_existing.body
    assert any(
        entry["action"] == "relate" and entry["concept_id"] == str(existing_id)
        for entry in bundle_log.entries
    )


def test_merge_addition_is_inserted_before_related_section():
    existing_id = ConceptId("coffee/espresso")
    existing = Concept(
        id=existing_id,
        frontmatter=Frontmatter(type="Playbook", title="Espresso"),
        body="Existing body.\n\n## Related\n\n- [Other](/other.md)\n",
    )
    raw = RawItem(id="raw-1", content="Extra detail.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso"),
        body="Extra detail.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[existing],
        disambiguation_verdict=DisambiguationVerdict(same_as=existing_id, confidence=0.95),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
    )

    use_case.run()

    merged = concept_repository.load(existing_id)
    assert merged.body.index("Extra detail.") < merged.body.index("## Related")


def test_create_stamps_sources_and_updates_the_hub():
    hub_id = ConceptId("references/attention-is-all-you-need")
    hub = Concept(
        id=hub_id,
        frontmatter=Frontmatter(type="Source Document", title="Attention Is All You Need"),
        body="Source document parsed from `raw/Attention Is All You Need.pdf`.",
    )
    raw = RawItem(
        id="chunk-1", content="Adam is an optimizer.", source_id="source-1", ordinal=17
    )
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Adam Optimizer"),
        body="Adam is an optimizer.",
        source_raw_id="chunk-1",
    )
    use_case, concept_repository, _, bundle_log = _build(
        [raw],
        {"chunk-1": [draft]},
        existing_concepts=[hub],
        source_concepts={"source-1": str(hub_id)},
    )

    outcomes = use_case.run()

    new_id = outcomes[0].created[0]
    saved = concept_repository.load(new_id)
    assert saved.frontmatter.sources == [
        Source(
            resource=f"/{hub_id}.md",
            id="attention-is-all-you-need-p17",
            title="Attention Is All You Need",
            locator="passage 17",
        )
    ]
    # The id is a footnote label, and the body cites it (§5.1).
    assert "[^attention-is-all-you-need-p17]" in saved.body
    assert (
        "[^attention-is-all-you-need-p17]: Attention Is All You Need — passage 17"
        in saved.body
    )

    updated_hub = concept_repository.load(hub_id)
    assert f"(/{new_id}.md)" in updated_hub.body
    assert "## Derived concepts" in updated_hub.body
    assert any(
        entry["action"] == "derive" and entry["concept_id"] == str(hub_id)
        for entry in bundle_log.entries
    )


def test_merge_stamps_one_source_entry_per_contributing_passage():
    hub_id = ConceptId("references/attention-is-all-you-need")
    hub = Concept(
        id=hub_id, frontmatter=Frontmatter(type="Source Document", title="Attention"), body="Stub."
    )
    existing_id = ConceptId("coffee/espresso")
    existing = Concept(
        id=existing_id, frontmatter=Frontmatter(type="Playbook", title="Espresso"), body="existing"
    )
    raw1 = RawItem(id="chunk-1", content="More detail 1.", source_id="source-1", ordinal=3)
    raw2 = RawItem(id="chunk-2", content="More detail 2.", source_id="source-1", ordinal=9)
    draft1 = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso"),
        body="More detail 1.",
        source_raw_id="chunk-1",
    )
    draft2 = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso"),
        body="More detail 2.",
        source_raw_id="chunk-2",
    )
    use_case, concept_repository, _, _ = _build(
        [raw1, raw2],
        {"chunk-1": [draft1], "chunk-2": [draft2]},
        existing_concepts=[hub, existing],
        disambiguation_verdict=DisambiguationVerdict(same_as=existing_id, confidence=0.95),
        candidates=[CandidateMatch(concept_id=existing_id, score=0.9)],
        source_concepts={"source-1": str(hub_id)},
    )

    use_case.run()

    merged = concept_repository.load(existing_id)
    # Two passages of one document contributed, so there are two entries —
    # this is the point of keying on `(resource, id)` instead of `resource`.
    # The old behaviour collapsed both into "came from the book, somewhere".
    assert [source.id for source in merged.frontmatter.sources] == [
        "attention-is-all-you-need-p3",
        "attention-is-all-you-need-p9",
    ]
    assert {source.resource for source in merged.frontmatter.sources} == {
        f"/{hub_id}.md"
    }
    # And the body attributes each claim to the passage it came from.
    assert "More detail 1.[^attention-is-all-you-need-p3]" in merged.body
    assert "More detail 2.[^attention-is-all-you-need-p9]" in merged.body

    updated_hub = concept_repository.load(hub_id)
    # Merged twice from the same source into the same concept — the hub
    # should only list it once, not accumulate duplicate entries.
    assert updated_hub.body.count(f"(/{existing_id}.md)") == 1


def test_raw_note_without_source_id_gets_no_sources():
    raw = RawItem(id="raw-1", content="A manually written note.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Manual Note"),
        body="A manually written note.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, _ = _build([raw], {"raw-1": [draft]})

    outcomes = use_case.run()

    saved = concept_repository.load(outcomes[0].created[0])
    assert saved.frontmatter.sources == []


class _RaisingExtractionSkill:
    """Simulates an unexpected failure (e.g. Ollama unreachable, an unparsable
    skill response) on one specific raw item, to test that IngestRawMaterial
    isolates it rather than aborting the whole batch."""

    def __init__(self, drafts_by_raw_id, raises_for: str) -> None:
        self._drafts_by_raw_id = drafts_by_raw_id
        self._raises_for = raises_for

    def extract(self, raw):
        if raw.id == self._raises_for:
            raise RuntimeError("Ollama request to /api/generate failed after 4 attempt(s)")
        return self._drafts_by_raw_id.get(raw.id, [])


def test_one_item_failing_unexpectedly_does_not_abort_the_batch():
    good_draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Cold Brew"),
        body="Cold brew steeps for 12-24 hours.",
        source_raw_id="raw-good",
    )
    raw_bad = RawItem(id="raw-bad", content="whatever")
    raw_good = RawItem(id="raw-good", content="Cold brew steeps for 12-24 hours.")

    use_case, concept_repository, raw_material_repository, bundle_log = _build(
        [raw_bad, raw_good], {"raw-good": [good_draft]}
    )
    # Swap in a skill that blows up for raw-bad only, after _build already
    # wired the (working) fakes for everything else.
    use_case._knowledge_agent._extraction = _RaisingExtractionSkill(
        {"raw-good": [good_draft]}, raises_for="raw-bad"
    )

    outcomes = use_case.run()

    bad_outcome, good_outcome = outcomes
    assert bad_outcome.raw_id == "raw-bad"
    assert bad_outcome.errored is not None
    assert bad_outcome.created == []
    assert "raw-bad" in raw_material_repository.errored
    assert "raw-bad" not in raw_material_repository.processed

    # The item after the failing one was still processed — one bad item
    # doesn't take down the rest of the batch.
    assert good_outcome.raw_id == "raw-good"
    assert good_outcome.errored is None
    assert len(good_outcome.created) == 1
    assert "raw-good" in raw_material_repository.processed
    assert any(entry["action"] == "create" for entry in bundle_log.entries)


def test_emitted_prerequisites_are_recorded_in_the_bundle_log_with_their_rationale():
    """The body carries the bare `requires::` line and nothing else, so the
    log is the only place a human reviewing a demoted edge can see why."""
    from pipeline.domain.eval import RubricContent
    from tests.application.fakes import FakePrerequisiteJudgementSkill

    target_id = ConceptId("water-temperature")
    target = Concept(
        id=target_id,
        frontmatter=Frontmatter(type="Playbook", title="Water temperature"),
        body="About water temperature.",
    )
    raw = RawItem(id="raw-1", content="Espresso extraction depends on water temperature.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso extraction"),
        body="Espresso extraction notes.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, bundle_log = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[target],
        disambiguation_verdict=DisambiguationVerdict(same_as=None, confidence=0.1),
        candidates=[CandidateMatch(concept_id=target_id, score=0.6)],
        prerequisite_rubrics=[Rubric("blocks", RubricContent("Must be required."))],
        prerequisite_skill=FakePrerequisiteJudgementSkill(
            {"water-temperature": [RubricScore("blocks", 0.9, "cannot follow without it")]}
        ),
    )

    outcomes = use_case.run()

    new_id = outcomes[0].created[0]
    assert "requires:: [[/water-temperature]]" in concept_repository.load(new_id).body

    entries = [e for e in bundle_log.entries if e["action"] == "require"]
    assert len(entries) == 1
    assert entries[0]["concept_id"] == str(new_id)
    assert "water-temperature" in entries[0]["message"]
    assert "cannot follow without it" in entries[0]["message"]


def test_a_prerequisite_gets_no_reciprocal_backlink():
    """Unlike relatedness, "A requires B" is a claim about A. Writing the
    reverse would assert a dependency nobody judged."""
    from pipeline.domain.eval import RubricContent
    from tests.application.fakes import FakePrerequisiteJudgementSkill

    target_id = ConceptId("water-temperature")
    target = Concept(
        id=target_id,
        frontmatter=Frontmatter(type="Playbook", title="Water temperature"),
        body="About water temperature.",
    )
    raw = RawItem(id="raw-1", content="...")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso extraction"),
        body="Espresso extraction notes.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[target],
        disambiguation_verdict=DisambiguationVerdict(same_as=None, confidence=0.1),
        candidates=[CandidateMatch(concept_id=target_id, score=0.6)],
        prerequisite_rubrics=[Rubric("blocks", RubricContent("Must be required."))],
        prerequisite_skill=FakePrerequisiteJudgementSkill(
            {"water-temperature": [RubricScore("blocks", 0.9, "required")]}
        ),
    )

    use_case.run()

    assert concept_repository.load(target_id).body == "About water temperature."


# --- credibility signals reaching derived concepts (RF1.5, ADR 0001) ------


def _hub_with_signals(author=None, last_modified=None) -> Concept:
    return Concept(
        id=ConceptId("references/attention-is-all-you-need"),
        frontmatter=Frontmatter(
            type="Source Document",
            title="Attention Is All You Need",
            sources=[
                Source(
                    resource="raw/Attention Is All You Need.pdf",
                    title="Attention Is All You Need",
                    author=author,
                    last_modified=last_modified,
                )
            ],
        ),
        body="Source document parsed from `raw/Attention Is All You Need.pdf`.",
    )


def test_a_derived_concept_carries_its_sources_credibility_signals():
    """A consumer judging this concept should see the signals without having
    to follow the link to the hub."""
    hub = _hub_with_signals(author="Vaswani et al.", last_modified="2024-04-10")
    raw = RawItem(id="chunk-1", content="Adam is an optimizer.", source_id="source-1")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Adam Optimizer"),
        body="Adam is an optimizer.",
        source_raw_id="chunk-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"chunk-1": [draft]},
        existing_concepts=[hub],
        source_concepts={"source-1": str(hub.id)},
    )

    outcomes = use_case.run()

    source = concept_repository.load(outcomes[0].created[0]).frontmatter.sources[0]
    assert source.resource == f"/{hub.id}.md"
    assert source.author == "Vaswani et al."
    assert source.last_modified == "2024-04-10"


def test_a_hub_with_no_signals_yields_a_concept_with_unknown_signals():
    """Absent means unknown, which ADR 0001 requires to stay neutral — never a
    fabricated author or date."""
    hub = _hub_with_signals()
    raw = RawItem(id="chunk-1", content="Adam is an optimizer.", source_id="source-1")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Adam Optimizer"),
        body="Adam is an optimizer.",
        source_raw_id="chunk-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"chunk-1": [draft]},
        existing_concepts=[hub],
        source_concepts={"source-1": str(hub.id)},
    )

    outcomes = use_case.run()

    source = concept_repository.load(outcomes[0].created[0]).frontmatter.sources[0]
    assert source.author is None
    assert source.last_modified is None


def test_a_hub_predating_signal_capture_does_not_break_ingest():
    """Hubs created before RF1.5 have no `sources[]` of their own. They must
    still ingest — no later pass can recover their signals anyway."""
    hub = Concept(
        id=ConceptId("references/attention-is-all-you-need"),
        frontmatter=Frontmatter(type="Source Document", title="Attention Is All You Need"),
        body="Source document parsed from `raw/Attention Is All You Need.pdf`.",
    )
    raw = RawItem(id="chunk-1", content="Adam is an optimizer.", source_id="source-1")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Adam Optimizer"),
        body="Adam is an optimizer.",
        source_raw_id="chunk-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"chunk-1": [draft]},
        existing_concepts=[hub],
        source_concepts={"source-1": str(hub.id)},
    )

    outcomes = use_case.run()

    source = concept_repository.load(outcomes[0].created[0]).frontmatter.sources[0]
    assert source.resource == f"/{hub.id}.md"
    assert source.author is None and source.last_modified is None


def test_no_credibility_score_is_ever_written():
    """ADR 0001: the signals are recorded, a score never is. Guards against a
    later change quietly adding one to the frontmatter."""
    hub = _hub_with_signals(author="Vaswani et al.", last_modified="2024-04-10")
    raw = RawItem(id="chunk-1", content="Adam is an optimizer.", source_id="source-1")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Adam Optimizer"),
        body="Adam is an optimizer.",
        source_raw_id="chunk-1",
    )
    use_case, concept_repository, _, _ = _build(
        [raw],
        {"chunk-1": [draft]},
        existing_concepts=[hub],
        source_concepts={"source-1": str(hub.id)},
    )

    outcomes = use_case.run()

    source = concept_repository.load(outcomes[0].created[0]).frontmatter.sources[0]
    assert set(vars(source)) == {
        "resource",
        "id",
        "title",
        "author",
        "usage_count",
        "last_modified",
        "locator",
    }
    assert source.usage_count is None  # episodic; lives in `tutor`, never here
    # The guard is against a *score*, not against the field set growing: every
    # name above is a signal or a pointer, and none of them is a judgement.
    assert not any("score" in name or "rating" in name for name in vars(source))


def test_a_relevance_rejection_is_recorded_in_the_bundle_log():
    """The rationale is all that survives a rejected draft — the concept is
    never written, so the log is the only place a human can see what was
    dropped and disagree with it (RF1.6)."""
    from pipeline.domain.relevance import RelevanceEvidence
    from tests.application.fakes import FakeRelevanceEvidence

    existing = Concept(
        id=ConceptId("qubits"),
        frontmatter=Frontmatter(type="Metric", title="Qubits"),
        body="About qubits.",
    )
    raw = RawItem(id="raw-1", content="Quantum computers use qubits.")
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Qubits, again"),
        body="Quantum computers use qubits.",
        source_raw_id="raw-1",
    )
    use_case, concept_repository, _, bundle_log = _build(
        [raw],
        {"raw-1": [draft]},
        existing_concepts=[existing],
        disambiguation_verdict=DisambiguationVerdict(same_as=None, confidence=0.1),
        relevance_evidence=FakeRelevanceEvidence(
            RelevanceEvidence(
                bundle_size=50, nearest_similarity=0.99, nearest_concept_id="qubits"
            )
        ),
    )

    outcomes = use_case.run()

    assert outcomes[0].created == []
    assert "already covered by qubits" in outcomes[0].rejected[0]
    assert any(
        entry["action"] == "reject" and "already covered by qubits" in entry["message"]
        for entry in bundle_log.entries
    )
    # The draft was not written, and no score reached the vault.
    assert list(concept_repository.concepts) == ["qubits"]
