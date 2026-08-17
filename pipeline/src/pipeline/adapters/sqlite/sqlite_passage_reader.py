"""`PassageReaderPort` over the intake store.

Reads `intake_items` (chunk text + `ordinal`) joined through
`intake_item_concepts` (the concept↔chunk edge `IngestRawMaterial` writes) and
back out through the same table to find the document's `references/` hub.

Queries the tables directly rather than composing `IntakeRepositoryPort`,
because every question here is a join and the port exposes only single-row
lookups — assembling `for_concept` from `get()` calls would be one round trip
per passage to rebuild what one statement already answers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pipeline.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from pipeline.domain.passage import Passage

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_CHUNK = "chunk"

_FOR_CONCEPT = """
SELECT i.id, i.content, i.ordinal, i.parent_id
FROM intake_items i
JOIN intake_item_concepts l ON l.intake_item_id = i.id
WHERE l.concept_id = ? AND i.kind = ? AND i.content IS NOT NULL
ORDER BY i.parent_id, i.ordinal IS NULL, i.ordinal
"""

_NEIGHBOURS = """
SELECT id, content, ordinal, parent_id
FROM intake_items
WHERE parent_id = ? AND kind = ? AND id != ? AND content IS NOT NULL
  AND ordinal IS NOT NULL AND ordinal BETWEEN ? AND ?
ORDER BY ordinal
"""


class SqlitePassageReader:
    def __init__(self, db_path: Path) -> None:
        self._pool = ThreadLocalSqliteConnection(
            db_path, _SCHEMA_PATH, row_factory=sqlite3.Row
        )

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def for_concept(self, concept_id: str) -> list[Passage]:
        rows = self._connection.execute(_FOR_CONCEPT, (concept_id, _CHUNK)).fetchall()
        return [self._passage(row) for row in rows]

    def neighbours(self, passage_id: str, radius: int = 1) -> list[Passage]:
        row = self._connection.execute(
            "SELECT ordinal, parent_id FROM intake_items WHERE id = ?", (passage_id,)
        ).fetchone()
        if row is None or row["ordinal"] is None or row["parent_id"] is None:
            return []

        ordinal = row["ordinal"]
        rows = self._connection.execute(
            _NEIGHBOURS,
            (
                row["parent_id"],
                _CHUNK,
                passage_id,
                ordinal - max(radius, 0),
                ordinal + max(radius, 0),
            ),
        ).fetchall()
        return [self._passage(neighbour) for neighbour in rows]

    def _passage(self, row: sqlite3.Row) -> Passage:
        return Passage(
            id=row["id"],
            text=row["content"],
            ordinal=row["ordinal"],
            source_concept_id=self._hub_for(row["parent_id"]),
        )

    def _hub_for(self, parent_id: str | None) -> str | None:
        """The document's `references/` hub, via the same link table.

        A source document is linked to exactly one hub by
        `ParseSourceDocuments._ensure_source_hub`, so the first row is the
        answer; `None` means this passage came from a note rather than a
        parsed document."""
        if parent_id is None:
            return None
        row = self._connection.execute(
            "SELECT concept_id FROM intake_item_concepts WHERE intake_item_id = ? LIMIT 1",
            (parent_id,),
        ).fetchone()
        return row["concept_id"] if row else None
