"""IntakeRepositoryPort backed by stdlib sqlite3 — the single source of truth for
what the pipeline knows about a file (or a chunk derived from one)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from pipeline.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _row_to_item(row: sqlite3.Row) -> IntakeItem:
    return IntakeItem(
        id=row["id"],
        kind=IntakeKind(row["kind"]),
        state=IntakeState(row["state"]),
        path=row["path"],
        content=row["content"],
        parent_id=row["parent_id"],
        error_message=row["error_message"],
        discovered_at=datetime.fromisoformat(row["discovered_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SqliteIntakeRepository:
    def __init__(self, db_path: Path) -> None:
        self._pool = ThreadLocalSqliteConnection(db_path, _SCHEMA_PATH, row_factory=sqlite3.Row)

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def find_by_path(self, path: str) -> IntakeItem | None:
        row = self._connection.execute(
            "SELECT * FROM intake_items WHERE path = ? ORDER BY discovered_at DESC LIMIT 1",
            (path,),
        ).fetchone()
        return _row_to_item(row) if row else None

    def get(self, item_id: str) -> IntakeItem | None:
        row = self._connection.execute(
            "SELECT * FROM intake_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _row_to_item(row) if row else None

    def upsert(self, item: IntakeItem) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO intake_items
                    (id, path, content, kind, state, parent_id, error_message, discovered_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    path=excluded.path, content=excluded.content, kind=excluded.kind,
                    state=excluded.state, parent_id=excluded.parent_id,
                    error_message=excluded.error_message, updated_at=excluded.updated_at
                """,
                (
                    item.id,
                    item.path,
                    item.content,
                    item.kind.value,
                    item.state.value,
                    item.parent_id,
                    item.error_message,
                    item.discovered_at.isoformat() if item.discovered_at else None,
                    item.updated_at.isoformat() if item.updated_at else None,
                ),
            )

    def list_by_state(
        self, state: IntakeState, kind: IntakeKind | None = None
    ) -> list[IntakeItem]:
        if kind is not None:
            rows = self._connection.execute(
                "SELECT * FROM intake_items WHERE state = ? AND kind = ? ORDER BY discovered_at",
                (state.value, kind.value),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM intake_items WHERE state = ? ORDER BY discovered_at",
                (state.value,),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def list_children(self, parent_id: str) -> list[IntakeItem]:
        rows = self._connection.execute(
            "SELECT * FROM intake_items WHERE parent_id = ? ORDER BY discovered_at",
            (parent_id,),
        ).fetchall()
        return [_row_to_item(row) for row in rows]

    def link_concept(self, item_id: str, concept_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO intake_item_concepts (intake_item_id, concept_id) VALUES (?, ?)",
                (item_id, concept_id),
            )

    def list_concepts_for(self, item_id: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT concept_id FROM intake_item_concepts WHERE intake_item_id = ?",
            (item_id,),
        ).fetchall()
        return [row["concept_id"] for row in rows]

    def delete(self, item_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM intake_items WHERE id = ?", (item_id,))
            self._connection.execute(
                "DELETE FROM intake_item_concepts WHERE intake_item_id = ?", (item_id,)
            )

    def list_stale_duplicates(self) -> list[IntakeItem]:
        rows = self._connection.execute(
            """
            SELECT * FROM intake_items t1
            WHERE t1.path IS NOT NULL
              AND t1.state IN ('discovered', 'error')
              AND EXISTS (
                  SELECT 1 FROM intake_items t2
                  WHERE t2.path = t1.path AND t2.discovered_at > t1.discovered_at
              )
            ORDER BY t1.discovered_at
            """
        ).fetchall()
        return [_row_to_item(row) for row in rows]

    def close(self) -> None:
        self._pool.close()
