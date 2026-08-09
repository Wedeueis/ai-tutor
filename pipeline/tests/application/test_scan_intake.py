from datetime import UTC, datetime

from pipeline.application.ports.filesystem_scanner import ScannedFile
from pipeline.application.use_cases.scan_intake import ScanIntake
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from tests.application.fakes import FakeFileSystemScanner, FakeIntakeRepository


def test_new_file_gets_registered_as_discovered():
    scanner = FakeFileSystemScanner(files=[ScannedFile(path="raw/note.md", content_hash="h1")])
    intake_repository = FakeIntakeRepository()

    new_items = ScanIntake(scanner, intake_repository).run("raw")

    assert len(new_items) == 1
    item = intake_repository.get("h1")
    assert item.kind is IntakeKind.RAW_NOTE
    assert item.state is IntakeState.DISCOVERED
    assert item.path == "raw/note.md"


def test_unchanged_file_is_not_reregistered():
    now = datetime.now(UTC)
    existing = IntakeItem(
        id="h1", kind=IntakeKind.RAW_NOTE, state=IntakeState.INGESTED,
        path="raw/note.md", discovered_at=now, updated_at=now,
    )
    scanner = FakeFileSystemScanner(files=[ScannedFile(path="raw/note.md", content_hash="h1")])
    intake_repository = FakeIntakeRepository(items=[existing])

    new_items = ScanIntake(scanner, intake_repository).run("raw")

    assert new_items == []
    assert intake_repository.get("h1").state is IntakeState.INGESTED


def test_changed_content_registers_a_new_item_at_same_path():
    now = datetime.now(UTC)
    existing = IntakeItem(
        id="h1-old", kind=IntakeKind.RAW_NOTE, state=IntakeState.INGESTED,
        path="raw/note.md", discovered_at=now, updated_at=now,
    )
    scanner = FakeFileSystemScanner(files=[ScannedFile(path="raw/note.md", content_hash="h1-new")])
    intake_repository = FakeIntakeRepository(items=[existing])

    new_items = ScanIntake(scanner, intake_repository).run("raw")

    assert len(new_items) == 1
    assert new_items[0].id == "h1-new"
    assert new_items[0].state is IntakeState.DISCOVERED
    assert intake_repository.get("h1-old").state is IntakeState.INGESTED


def test_unrecognized_extension_is_skipped():
    scanner = FakeFileSystemScanner(files=[ScannedFile(path="raw/archive.zip", content_hash="h1")])
    intake_repository = FakeIntakeRepository()

    new_items = ScanIntake(scanner, intake_repository).run("raw")

    assert new_items == []
    assert intake_repository.get("h1") is None


def test_source_document_extension_classified_correctly():
    scanner = FakeFileSystemScanner(files=[ScannedFile(path="raw/report.pdf", content_hash="h1")])
    intake_repository = FakeIntakeRepository()

    ScanIntake(scanner, intake_repository).run("raw")

    assert intake_repository.get("h1").kind is IntakeKind.SOURCE_DOCUMENT
