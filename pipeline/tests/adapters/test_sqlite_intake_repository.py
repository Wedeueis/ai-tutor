from datetime import UTC, datetime

from pipeline.adapters.sqlite.sqlite_intake_repository import SqliteIntakeRepository
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState


def _item(**overrides) -> IntakeItem:
    now = datetime.now(UTC)
    defaults = dict(
        id="hash1",
        kind=IntakeKind.RAW_NOTE,
        state=IntakeState.DISCOVERED,
        path="raw/note.md",
        discovered_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return IntakeItem(**defaults)


def test_upsert_then_get(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    repo.upsert(_item())

    item = repo.get("hash1")
    assert item.path == "raw/note.md"
    assert item.state is IntakeState.DISCOVERED
    repo.close()


def test_find_by_path_returns_latest(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    now = datetime.now(UTC)
    repo.upsert(_item(id="hash-old", discovered_at=now, updated_at=now))
    later = datetime.now(UTC).replace(microsecond=999999)
    repo.upsert(_item(id="hash-new", discovered_at=later, updated_at=later))

    found = repo.find_by_path("raw/note.md")
    assert found.id == "hash-new"
    repo.close()


def test_upsert_updates_state_in_place(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    item = _item()
    repo.upsert(item)
    item.state = IntakeState.INGESTED
    repo.upsert(item)

    assert repo.get("hash1").state is IntakeState.INGESTED
    repo.close()


def test_list_by_state_and_kind(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    repo.upsert(_item(id="a", kind=IntakeKind.RAW_NOTE, state=IntakeState.DISCOVERED))
    repo.upsert(_item(id="b", kind=IntakeKind.SOURCE_DOCUMENT, state=IntakeState.DISCOVERED, path="raw/doc.pdf"))
    repo.upsert(_item(id="c", kind=IntakeKind.RAW_NOTE, state=IntakeState.INGESTED, path="raw/other.md"))

    discovered = repo.list_by_state(IntakeState.DISCOVERED)
    assert {item.id for item in discovered} == {"a", "b"}

    discovered_notes = repo.list_by_state(IntakeState.DISCOVERED, kind=IntakeKind.RAW_NOTE)
    assert [item.id for item in discovered_notes] == ["a"]
    repo.close()


def test_list_children_by_parent(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    repo.upsert(_item(id="source", kind=IntakeKind.SOURCE_DOCUMENT, path="raw/doc.pdf"))
    repo.upsert(_item(id="chunk-0", kind=IntakeKind.CHUNK, path=None, content="chunk text", parent_id="source"))

    children = repo.list_children("source")
    assert [c.id for c in children] == ["chunk-0"]
    assert children[0].content == "chunk text"
    repo.close()


def test_delete_removes_item_and_its_concept_links(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    repo.upsert(_item())
    repo.link_concept("hash1", "espresso-ratio")

    repo.delete("hash1")

    assert repo.get("hash1") is None
    assert repo.list_concepts_for("hash1") == []
    repo.close()


def test_list_stale_duplicates_finds_superseded_never_processed_items(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    now = datetime.now(UTC)
    later = datetime.now(UTC).replace(microsecond=999999)
    repo.upsert(_item(id="old", state=IntakeState.DISCOVERED, discovered_at=now, updated_at=now))
    repo.upsert(_item(id="new", discovered_at=later, updated_at=later))

    stale = repo.list_stale_duplicates()

    assert [item.id for item in stale] == ["old"]
    repo.close()


def test_list_stale_duplicates_excludes_already_processed_items(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    now = datetime.now(UTC)
    later = datetime.now(UTC).replace(microsecond=999999)
    repo.upsert(_item(id="old", state=IntakeState.INGESTED, discovered_at=now, updated_at=now))
    repo.upsert(_item(id="new", discovered_at=later, updated_at=later))

    assert repo.list_stale_duplicates() == []
    repo.close()


def test_link_and_list_concepts(tmp_path):
    repo = SqliteIntakeRepository(tmp_path / "intake.db")
    repo.upsert(_item())
    repo.link_concept("hash1", "espresso-ratio")
    repo.link_concept("hash1", "espresso-ratio")  # idempotent

    assert repo.list_concepts_for("hash1") == ["espresso-ratio"]
    repo.close()
