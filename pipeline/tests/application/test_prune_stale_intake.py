from datetime import UTC, datetime, timedelta

from pipeline.application.use_cases.prune_stale_intake import PruneStaleIntake
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from tests.application.fakes import FakeIntakeRepository


def _item(**overrides) -> IntakeItem:
    now = datetime.now(UTC)
    defaults = dict(
        id="h",
        kind=IntakeKind.RAW_NOTE,
        state=IntakeState.DISCOVERED,
        path="raw/note.md",
        discovered_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return IntakeItem(**defaults)


def test_deletes_superseded_never_processed_item():
    now = datetime.now(UTC)
    old = _item(id="old", discovered_at=now, updated_at=now)
    new = _item(id="new", discovered_at=now + timedelta(seconds=1), updated_at=now + timedelta(seconds=1))
    repo = FakeIntakeRepository(items=[old, new])

    removed = PruneStaleIntake(repo).run()

    assert [item.id for item in removed] == ["old"]
    assert repo.get("old") is None
    assert repo.get("new") is not None


def test_keeps_superseded_item_that_was_already_ingested():
    now = datetime.now(UTC)
    old = _item(id="old", state=IntakeState.INGESTED, discovered_at=now, updated_at=now)
    new = _item(id="new", discovered_at=now + timedelta(seconds=1), updated_at=now + timedelta(seconds=1))
    repo = FakeIntakeRepository(items=[old, new])

    removed = PruneStaleIntake(repo).run()

    assert removed == []
    assert repo.get("old") is not None


def test_latest_item_at_a_path_is_never_pruned():
    now = datetime.now(UTC)
    only = _item(id="only", discovered_at=now, updated_at=now)
    repo = FakeIntakeRepository(items=[only])

    removed = PruneStaleIntake(repo).run()

    assert removed == []
    assert repo.get("only") is not None
