"""BundleLogPort backed by SQLite — a structured, queryable audit trail of
ingest decisions (create/merge/reject), replacing the old log.md prose file.
This is pipeline governance state, not part of the OKF bundle (WIKI_SPEC.md
§9's log.md remains valid spec — this pipeline simply doesn't populate it)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pipeline.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from pipeline.application.ports.bundle_log import LogEntry

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SqliteBundleLog:
    def __init__(
        self, db_path: Path, clock: Callable[[], datetime] = datetime.utcnow
    ) -> None:
        self._pool = ThreadLocalSqliteConnection(db_path, _SCHEMA_PATH)
        self._clock = clock

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def append(
        self, action: str, concept_id: str | None, raw_id: str | None, message: str
    ) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO bundle_log (ts, action, concept_id, raw_id, message) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._clock().isoformat(), action, concept_id, raw_id, message),
            )

    def list_entries(self) -> list[LogEntry]:
        rows = self._connection.execute(
            "SELECT ts, action, concept_id, raw_id, message FROM bundle_log ORDER BY id DESC"
        ).fetchall()
        return [
            LogEntry(
                action=row[1],
                concept_id=row[2],
                raw_id=row[3],
                message=row[4],
                at=datetime.fromisoformat(row[0]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._pool.close()
