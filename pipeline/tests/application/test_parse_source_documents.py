from datetime import UTC, datetime

from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.parse_source_documents import ParseSourceDocuments
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from pipeline.domain.source_document import ParsedDocument, ParsedImage
from tests.application.fakes import (
    FakeBundleLog,
    FakeConceptRepository,
    FakeDocumentParsing,
    FakeEmbedding,
    FakeImageCaptioning,
    FakeIntakeRepository,
    FakeMetadataRepository,
    FakeVectorSearch,
)


def _source_item(path="raw/report.pdf") -> IntakeItem:
    now = datetime.now(UTC)
    return IntakeItem(
        id="source-1",
        kind=IntakeKind.SOURCE_DOCUMENT,
        state=IntakeState.DISCOVERED,
        path=path,
        discovered_at=now,
        updated_at=now,
    )


def _build(intake_repository, parsing, image_captioning=None):
    concept_repository = FakeConceptRepository()
    index_concept = IndexConcept(FakeEmbedding(), FakeVectorSearch(), FakeMetadataRepository())
    bundle_log = FakeBundleLog()
    use_case = ParseSourceDocuments(
        intake_repository,
        parsing,
        image_captioning or FakeImageCaptioning(),
        concept_repository,
        index_concept,
        bundle_log,
    )
    return use_case, concept_repository, bundle_log


def test_parses_and_chunks_a_source_document():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\nSome findings.")}
    )
    use_case, _, _ = _build(intake_repository, parsing)

    outcomes = use_case.run()

    assert len(outcomes) == 1
    assert len(outcomes[0].chunk_ids) == 1
    chunk = intake_repository.get(outcomes[0].chunk_ids[0])
    assert chunk.kind is IntakeKind.CHUNK
    assert chunk.parent_id == "source-1"
    assert chunk.content == "# Report\n\nSome findings."
    assert chunk.state is IntakeState.DISCOVERED

    assert intake_repository.get("source-1").state is IntakeState.PARSED


def test_image_anchors_are_replaced_with_captions():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    image = ParsedImage(id="img-1", path="/tmp/img-1.png", anchor="{{image:0}}")
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\n{{image:0}}\n\nMore text.", images=[image])}
    )
    image_captioning = FakeImageCaptioning({"{{image:0}}": "a bar chart of Q1 revenue"})
    use_case, _, _ = _build(intake_repository, parsing, image_captioning)

    outcomes = use_case.run()

    chunk = intake_repository.get(outcomes[0].chunk_ids[0])
    assert "[image: a bar chart of Q1 revenue]" in chunk.content
    assert "{{image:0}}" not in chunk.content


def test_long_document_produces_multiple_chunks():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    text = "# One\n\nfirst\n\n# Two\n\nsecond"
    parsing = FakeDocumentParsing({"raw/report.pdf": ParsedDocument(text=text)})
    use_case, _, _ = _build(intake_repository, parsing)

    outcomes = use_case.run()

    assert len(outcomes[0].chunk_ids) == 2


def test_garbled_table_chunk_is_skipped_not_registered():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    garbled = (
        "|      |                     |               |        6.11 |         23.7 | 36 |\n"
        "|      | 4                   |               |        5.19 |         25.3 | 50 |\n"
        "|      | 8                   |               |        4.88 |         25.5 | 80 |\n"
    )
    text = f"# Good\n\nSome real findings about the model.\n\n# Table\n\n{garbled}"
    parsing = FakeDocumentParsing({"raw/report.pdf": ParsedDocument(text=text)})
    use_case, _, _ = _build(intake_repository, parsing)

    outcomes = use_case.run()

    assert len(outcomes[0].chunk_ids) == 1
    assert outcomes[0].skipped == 1
    remaining = intake_repository.get(outcomes[0].chunk_ids[0])
    assert "Some real findings" in remaining.content


def test_no_discovered_source_documents_yields_no_outcomes():
    intake_repository = FakeIntakeRepository()
    use_case, _, _ = _build(intake_repository, FakeDocumentParsing({}))

    assert use_case.run() == []


def test_one_document_failing_unexpectedly_does_not_abort_the_batch():
    now = datetime.now(UTC)
    good = _source_item(path="raw/good.pdf")
    bad = IntakeItem(
        id="source-bad",
        kind=IntakeKind.SOURCE_DOCUMENT,
        state=IntakeState.DISCOVERED,
        path="raw/unregistered.pdf",  # not in `parsing`'s dict -> parse() raises KeyError
        discovered_at=now,
        updated_at=now,
    )
    intake_repository = FakeIntakeRepository(items=[bad, good])
    parsing = FakeDocumentParsing({"raw/good.pdf": ParsedDocument(text="# Report\n\nfindings.")})
    use_case, _, _ = _build(intake_repository, parsing)

    outcomes = use_case.run()

    bad_outcome, good_outcome = outcomes
    assert bad_outcome.source_id == "source-bad"
    assert bad_outcome.errored is not None
    assert bad_outcome.chunk_ids == []
    assert intake_repository.get("source-bad").state is IntakeState.ERROR
    assert intake_repository.get("source-bad").error_message

    # The document after the failing one was still parsed.
    assert good_outcome.source_id == "source-1"
    assert good_outcome.errored is None
    assert len(good_outcome.chunk_ids) == 1
    assert intake_repository.get("source-1").state is IntakeState.PARSED


def test_creates_a_reference_hub_for_a_new_source_document():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\nSome findings.")}
    )
    use_case, concept_repository, bundle_log = _build(intake_repository, parsing)

    use_case.run()

    hub_id = ConceptId("references/report")
    assert concept_repository.exists(hub_id)
    hub = concept_repository.load(hub_id)
    assert hub.frontmatter.type == "Source Document"
    assert hub.frontmatter.title == "report"
    assert intake_repository.list_concepts_for("source-1") == ["references/report"]
    assert any(e["action"] == "create" and e["concept_id"] == "references/report" for e in bundle_log.entries)


def test_hub_creation_is_idempotent_across_reparses():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\nSome findings.")}
    )
    use_case, concept_repository, bundle_log = _build(intake_repository, parsing)

    use_case.run()
    # Simulate a re-parse (e.g. after `pipeline retry`) of the same source.
    source.state = IntakeState.DISCOVERED
    intake_repository.upsert(source)
    use_case.run()

    hub_entries = [e for e in bundle_log.entries if e["action"] == "create" and "references/" in (e["concept_id"] or "")]
    assert len(hub_entries) == 1


def test_hub_id_avoids_collision_with_existing_concept():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\nSome findings.")}
    )
    use_case, concept_repository, _ = _build(intake_repository, parsing)
    concept_repository.save(
        Concept(id=ConceptId("references/report"), frontmatter=Frontmatter(type="Source Document"), body="")
    )

    use_case.run()

    assert concept_repository.exists(ConceptId("references/report-2"))
