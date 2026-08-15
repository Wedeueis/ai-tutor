"""A `sqlite3.Connection` is only safe to use from the thread that created it
(`check_same_thread`, on by default). The store is built once and then called
from wherever it is wired — including, once the ADK agent lands, a worker-
thread pool where a different thread can run each tool call. A single
connection opened at construction time would raise `sqlite3.ProgrammingError`
the first time a call arrived on another thread.

Deliberately a copy of `pipeline`'s equivalent rather than an import of it:
`tutor` reaches `pipeline` only over MCP (PRD v3 §2, rule 1), and forty lines
of SQLite plumbing is a much smaller cost than a shared package the two
deployables would then have to version together."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class ThreadLocalSqliteConnection:
    def __init__(self, db_path: Path, schema_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._schema_sql = schema_path.read_text(encoding="utf-8")
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._db_path)
            connection.row_factory = sqlite3.Row
            connection.executescript(self._schema_sql)
            connection.commit()
            self._local.connection = connection
        return connection

    def close(self) -> None:
        """Closes the connection for the *calling* thread only — there is no
        general way to reach into another thread's connection."""
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None
