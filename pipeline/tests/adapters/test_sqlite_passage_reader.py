"""`SqlitePassageReader` against a real database.

The joins are the whole adapter, so they are tested against SQLite rather than
a fake: an ordering clause or a `kind` filter that is subtly wrong is exactly
the kind of thing an in-memory stand-in would not reproduce.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipeline.adapters.sqlite.sqlite_intake_repository import SqliteIntakeRepository
from pipeline.adapters.sqlite.sqlite_passage_reader import SqlitePassageReader
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState

NOW = datetime(2026, 8, 17, tzinfo=UTC)
DOC = "doc-1"
HUB = "references/the-book"
CONCEPT = "scaled-dot-product-attention"


@pytest.fixture
def db(tmp_path):
    return tmp_path / "metadata.db"


@pytest.fixture
def intake(db):
    repository = SqliteIntakeRepository(db)
    repository.upsert(
        IntakeItem(
            id=DOC,
            kind=IntakeKind.SOURCE_DOCUMENT,
            state=IntakeState.PARSED,
            path="raw/the-book.pdf",
            discovered_at=NOW,
            updated_at=NOW,
        )
    )
    repository.link_concept(DOC, HUB)
    return repository


@pytest.fixture
def reader(db):
    return SqlitePassageReader(db)


def add_chunk(intake, ordinal: int, text: str | None = None, concept: str | None = None):
    chunk_id = f"chunk-{ordinal}"
    intake.upsert(
        IntakeItem(
            id=chunk_id,
            kind=IntakeKind.CHUNK,
            state=IntakeState.INGESTED,
            content=text or f"text {ordinal}",
            parent_id=DOC,
            ordinal=ordinal,
            discovered_at=NOW,
            updated_at=NOW,
        )
    )
    if concept:
        intake.link_concept(chunk_id, concept)
    return chunk_id


# --- for_concept -----------------------------------------------------------


def test_a_concept_with_no_passages_reads_empty(reader, intake):
    assert reader.for_concept(CONCEPT) == []


def test_passages_come_back_in_document_order(reader, intake):
    add_chunk(intake, 9, concept=CONCEPT)
    add_chunk(intake, 3, concept=CONCEPT)

    assert [p.ordinal for p in reader.for_concept(CONCEPT)] == [3, 9]


def test_a_passage_carries_its_documents_hub(reader, intake):
    """Which is what makes `source_id` derivable, and therefore what ties a
    passage back to the footnote label in the concept's body."""
    add_chunk(intake, 17, concept=CONCEPT)

    recalled = reader.for_concept(CONCEPT)[0]

    assert recalled.source_concept_id == HUB
    assert recalled.source_id == "the-book-p17"


def test_passages_of_other_concepts_are_not_returned(reader, intake):
    add_chunk(intake, 3, concept=CONCEPT)
    add_chunk(intake, 4, concept="something-else")

    assert [p.ordinal for p in reader.for_concept(CONCEPT)] == [3]


def test_the_source_document_itself_is_not_a_passage(reader, intake):
    """`DOC` is linked to `HUB` in the same table. A reader that ignored `kind`
    would hand back the document row as if it were text from the book."""
    assert reader.for_concept(HUB) == []


# --- neighbours ------------------------------------------------------------


def test_neighbours_exclude_the_passage_itself(reader, intake):
    for ordinal in (3, 4, 5):
        add_chunk(intake, ordinal, concept=CONCEPT)

    assert [p.ordinal for p in reader.neighbours("chunk-4", 1)] == [3, 5]


def test_a_wider_radius_reaches_further(reader, intake):
    for ordinal in range(6):
        add_chunk(intake, ordinal, concept=CONCEPT)

    assert [p.ordinal for p in reader.neighbours("chunk-3", 2)] == [1, 2, 4, 5]


def test_the_first_passage_has_nothing_before_it(reader, intake):
    add_chunk(intake, 0, concept=CONCEPT)
    add_chunk(intake, 1, concept=CONCEPT)

    assert [p.ordinal for p in reader.neighbours("chunk-0", 1)] == [1]


def test_a_gap_is_not_bridged(reader, intake):
    """Ordinals skip where a garbled chunk was dropped. Radius 1 from 23 must
    not silently return 26 as if the two were adjacent."""
    add_chunk(intake, 23, concept=CONCEPT)
    add_chunk(intake, 26, concept=CONCEPT)

    assert reader.neighbours("chunk-23", 1) == []
    assert [p.ordinal for p in reader.neighbours("chunk-23", 3)] == [26]


def test_neighbours_never_cross_into_another_document(reader, intake, db):
    add_chunk(intake, 5, concept=CONCEPT)
    intake.upsert(
        IntakeItem(
            id="other-doc-chunk",
            kind=IntakeKind.CHUNK,
            state=IntakeState.INGESTED,
            content="a different book",
            parent_id="doc-2",
            ordinal=6,
            discovered_at=NOW,
            updated_at=NOW,
        )
    )

    assert reader.neighbours("chunk-5", 1) == []


def test_an_unknown_passage_has_no_neighbours(reader, intake):
    assert reader.neighbours("nope", 1) == []
