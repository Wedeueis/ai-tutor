"""Adapter test for FilesystemRawMaterialRepository, exercised together with the
real SqliteIntakeRepository/FilesystemScanner/ScanIntake it's built on — no
Ollama/Chroma involved, so this runs offline like the other adapter tests."""

from datetime import UTC

from pipeline.adapters.filesystem.filesystem_scanner import FilesystemScanner
from pipeline.adapters.filesystem.raw_material_repository import FilesystemRawMaterialRepository
from pipeline.adapters.sqlite.sqlite_intake_repository import SqliteIntakeRepository
from pipeline.application.use_cases.scan_intake import ScanIntake
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState


def _setup(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    intake_repository = SqliteIntakeRepository(tmp_path / "intake.db")
    scanner = FilesystemScanner()
    scan = ScanIntake(scanner, intake_repository)
    repo = FilesystemRawMaterialRepository(intake_repository, scanner)
    return raw_dir, intake_repository, scan, repo


def test_lists_discovered_raw_notes_after_scan(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    (raw_dir / "note1.md").write_text("content one", encoding="utf-8")
    (raw_dir / "README.md").write_text("inbox docs", encoding="utf-8")

    scan.run(str(raw_dir))
    items = repo.list_unprocessed()

    assert len(items) == 1
    assert items[0].content == "content one"


def test_mark_processed_removes_item_from_unprocessed(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    (raw_dir / "note1.md").write_text("content one", encoding="utf-8")
    scan.run(str(raw_dir))
    raw_id = repo.list_unprocessed()[0].id

    repo.mark_processed(raw_id)

    assert repo.list_unprocessed() == []
    assert intake_repository.get(raw_id).state is IntakeState.INGESTED


def test_mark_rejected_records_reason(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    (raw_dir / "note1.md").write_text("garbled", encoding="utf-8")
    scan.run(str(raw_dir))
    raw_id = repo.list_unprocessed()[0].id

    repo.mark_rejected(raw_id, "not grounded in the source")

    assert repo.list_unprocessed() == []
    item = intake_repository.get(raw_id)
    assert item.state is IntakeState.REJECTED
    assert item.error_message == "not grounded in the source"


def test_link_concept_is_queryable_afterwards(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    (raw_dir / "note1.md").write_text("content", encoding="utf-8")
    scan.run(str(raw_dir))
    raw_id = repo.list_unprocessed()[0].id

    repo.link_concept(raw_id, "espresso-ratio")

    assert intake_repository.list_concepts_for(raw_id) == ["espresso-ratio"]


def test_lists_db_only_chunk_content_without_touching_filesystem(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    now = None
    from datetime import datetime

    now = datetime.now(UTC)
    intake_repository.upsert(
        IntakeItem(
            id="chunk-1",
            kind=IntakeKind.CHUNK,
            state=IntakeState.DISCOVERED,
            path=None,
            content="chunk text from a parsed PDF",
            parent_id="source-1",
            discovered_at=now,
            updated_at=now,
        )
    )

    items = repo.list_unprocessed()

    assert len(items) == 1
    assert items[0].content == "chunk text from a parsed PDF"
    assert items[0].source_id == "source-1"


def test_raw_note_has_no_source_id(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)
    (raw_dir / "note1.md").write_text("content", encoding="utf-8")
    scan.run(str(raw_dir))

    assert repo.list_unprocessed()[0].source_id is None


def test_find_source_concept_resolves_via_intake_link_concept(tmp_path):
    raw_dir, intake_repository, scan, repo = _setup(tmp_path)

    assert repo.find_source_concept("source-1") is None

    intake_repository.link_concept("source-1", "references/some-paper")

    assert repo.find_source_concept("source-1") == "references/some-paper"
