from datetime import UTC, datetime

from pipeline.application.use_cases.parse_source_documents import ParseSourceDocuments
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from pipeline.domain.source_document import ParsedDocument, ParsedImage
from tests.application.fakes import FakeDocumentParsing, FakeImageCaptioning, FakeIntakeRepository


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


def test_parses_and_chunks_a_source_document():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    parsing = FakeDocumentParsing(
        {"raw/report.pdf": ParsedDocument(text="# Report\n\nSome findings.")}
    )
    use_case = ParseSourceDocuments(intake_repository, parsing, FakeImageCaptioning())

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
    use_case = ParseSourceDocuments(intake_repository, parsing, image_captioning)

    outcomes = use_case.run()

    chunk = intake_repository.get(outcomes[0].chunk_ids[0])
    assert "[image: a bar chart of Q1 revenue]" in chunk.content
    assert "{{image:0}}" not in chunk.content


def test_long_document_produces_multiple_chunks():
    source = _source_item()
    intake_repository = FakeIntakeRepository(items=[source])
    text = "# One\n\nfirst\n\n# Two\n\nsecond"
    parsing = FakeDocumentParsing({"raw/report.pdf": ParsedDocument(text=text)})
    use_case = ParseSourceDocuments(intake_repository, parsing, FakeImageCaptioning())

    outcomes = use_case.run()

    assert len(outcomes[0].chunk_ids) == 2


def test_no_discovered_source_documents_yields_no_outcomes():
    intake_repository = FakeIntakeRepository()
    use_case = ParseSourceDocuments(intake_repository, FakeDocumentParsing({}), FakeImageCaptioning())

    assert use_case.run() == []
