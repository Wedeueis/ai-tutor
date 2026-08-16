from datetime import UTC, datetime

from pipeline.application.use_cases.clear_bundle import ClearBundle
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from tests.application.fakes import (
    FakeBundleLog,
    FakeConceptRepository,
    FakeIntakeRepository,
    FakeMetadataRepository,
    FakeVectorSearch,
)


def _concept(concept_id: str, title: str = "A concept") -> Concept:
    return Concept(
        id=ConceptId(concept_id),
        frontmatter=Frontmatter(type="Concept", title=title),
        body="body",
    )


def _item(item_id: str, state: IntakeState = IntakeState.INGESTED) -> IntakeItem:
    now = datetime.now(UTC)
    return IntakeItem(
        id=item_id,
        kind=IntakeKind.RAW_NOTE,
        state=state,
        path=f"raw/{item_id}.md",
        discovered_at=now,
        updated_at=now,
    )


def _build(concepts: list[Concept], items: list[IntakeItem] | None = None):
    concept_repository = FakeConceptRepository()
    metadata_repository = FakeMetadataRepository()
    vector_search = FakeVectorSearch()
    for concept in concepts:
        concept_repository.save(concept)
        metadata_repository.upsert(concept)
        vector_search.upsert(str(concept.id), [1.0], {})
    intake_repository = FakeIntakeRepository(items=items or [])
    bundle_log = FakeBundleLog()
    use_case = ClearBundle(
        concept_repository=concept_repository,
        metadata_repository=metadata_repository,
        vector_search=vector_search,
        intake_repository=intake_repository,
        bundle_log=bundle_log,
    )
    return use_case, concept_repository, metadata_repository, vector_search, intake_repository, bundle_log


def test_removes_every_concept_from_all_three_stores():
    use_case, concepts, metadata, vectors, _, _ = _build(
        [_concept("alpha"), _concept("nested/beta")]
    )

    report = use_case.run()

    assert sorted(report.concept_ids) == ["alpha", "nested/beta"]
    assert concepts.list() == []
    assert metadata.upserted == {}
    assert vectors.upserted == {}


def test_records_one_audit_entry_per_removed_concept():
    use_case, _, _, _, _, bundle_log = _build([_concept("alpha", title="Alpha")])

    use_case.run()

    assert [(entry["action"], entry["concept_id"]) for entry in bundle_log.entries] == [
        ("delete", "alpha")
    ]
    assert "Alpha" in bundle_log.entries[0]["message"]


def test_leaves_intake_alone_by_default():
    use_case, _, _, _, intake, _ = _build([_concept("alpha")], items=[_item("raw-1")])

    report = use_case.run()

    assert report.intake_ids == []
    assert intake.get("raw-1") is not None


def test_reset_intake_forgets_every_tracked_item():
    items = [
        _item("raw-1", IntakeState.INGESTED),
        _item("raw-2", IntakeState.DISCOVERED),
        _item("raw-3", IntakeState.ERROR),
    ]
    use_case, _, _, _, intake, _ = _build([_concept("alpha")], items=items)

    report = use_case.run(reset_intake=True)

    assert sorted(report.intake_ids) == ["raw-1", "raw-2", "raw-3"]
    assert all(intake.get(item.id) is None for item in items)


def test_leaves_audit_log_alone_by_default():
    use_case, _, _, _, _, bundle_log = _build([_concept("alpha")])
    bundle_log.append(action="create", concept_id="alpha", raw_id=None, message="made it")

    report = use_case.run()

    assert report.log_entries == 0
    assert len(bundle_log.entries) == 2  # the pre-existing create, plus this delete


def test_reset_log_drops_the_trail_including_this_run_s_deletes():
    use_case, _, _, _, _, bundle_log = _build([_concept("alpha")])
    bundle_log.append(action="create", concept_id="alpha", raw_id=None, message="made it")

    report = use_case.run(reset_log=True)

    assert report.log_entries == 2
    assert bundle_log.entries == []


def test_reset_log_on_an_already_empty_bundle_is_not_a_no_op():
    """A vault with no concepts can still carry history worth resetting, so
    `is_empty` has to account for the log rather than only the vault."""
    use_case, _, _, _, _, bundle_log = _build([])
    bundle_log.append(action="reject", concept_id=None, raw_id="raw-1", message="nope")

    assert not use_case.plan(reset_log=True).is_empty
    assert use_case.run(reset_log=True).log_entries == 1
    assert bundle_log.entries == []


def test_plan_changes_nothing():
    use_case, concepts, metadata, vectors, intake, bundle_log = _build(
        [_concept("alpha")], items=[_item("raw-1")]
    )

    bundle_log.append(action="create", concept_id="alpha", raw_id=None, message="made it")

    report = use_case.plan(reset_intake=True, reset_log=True)

    assert report.concept_ids == ["alpha"]
    assert report.intake_ids == ["raw-1"]
    assert report.log_entries == 1
    assert concepts.list() == [ConceptId("alpha")]
    assert metadata.upserted != {}
    assert vectors.upserted != {}
    assert intake.get("raw-1") is not None
    assert len(bundle_log.entries) == 1


def test_empty_bundle_reports_nothing_to_do():
    use_case, _, _, _, _, _ = _build([])

    assert use_case.plan().is_empty
    assert use_case.run().is_empty
