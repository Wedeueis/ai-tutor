"""`IndexFingerprintPort` backed by SQLite.

Lives in `metadata.db` rather than in Chroma's own collection metadata for one
reason: Chroma sets collection metadata at creation and this value has to be
writable afterwards, on the first vector of a rebuild. The Chroma collection
also carries a copy (see `ChromaVectorSearch`), so the record survives either
store being deleted independently — they are checked against each other, not
trusted individually.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from pipeline.application.ports.index_fingerprint import IndexFingerprint

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> datetime:
    return datetime.now(UTC)


class SqliteIndexFingerprint:
    def __init__(
        self, db_path: Path, clock: Callable[[], datetime] = _now
    ) -> None:
        self._pool = ThreadLocalSqliteConnection(
            db_path, _SCHEMA_PATH, row_factory=sqlite3.Row
        )
        self._clock = clock

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def read(self) -> IndexFingerprint | None:
        row = self._connection.execute(
            "SELECT embed_model, dimensions, query_instruction "
            "FROM index_fingerprint WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return IndexFingerprint(
            embed_model=row["embed_model"],
            dimensions=row["dimensions"],
            query_instruction=row["query_instruction"],
        )

    def write(self, fingerprint: IndexFingerprint) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO index_fingerprint "
                "(id, embed_model, dimensions, query_instruction, recorded_at) "
                "VALUES (1, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "embed_model=excluded.embed_model, "
                "dimensions=excluded.dimensions, "
                "query_instruction=excluded.query_instruction, "
                "recorded_at=excluded.recorded_at",
                (
                    fingerprint.embed_model,
                    fingerprint.dimensions,
                    fingerprint.query_instruction,
                    self._clock().isoformat(),
                ),
            )

    def clear(self) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM index_fingerprint")
