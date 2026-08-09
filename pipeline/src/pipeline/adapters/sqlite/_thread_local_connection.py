"""A `sqlite3.Connection` is only safe to use from the thread that created it
(`check_same_thread`, on by default). Both SQLite adapters are built once and
then called from wherever their `Container` is used — including, for the MCP
server, an `anyio` worker-thread pool where a different thread can run each
tool call. A single connection opened at construction time would raise
`sqlite3.ProgrammingError` the first time a call landed on a thread other than
the one that built the `Container`.

`ThreadLocalSqliteConnection` lazily opens (and schema-initializes) one
connection per thread instead, keyed by `threading.local()`. Each adapter
exposes it as a `_connection` property, so call sites that already read
`self._connection.execute(...)` need no other change."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class ThreadLocalSqliteConnection:
    def __init__(
        self,
        db_path: Path,
        schema_path: Path,
        row_factory: type[sqlite3.Row] | None = None,
    ) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._schema_sql = schema_path.read_text(encoding="utf-8")
        self._row_factory = row_factory
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._db_path)
            if self._row_factory is not None:
                connection.row_factory = self._row_factory
            connection.executescript(self._schema_sql)
            connection.commit()
            self._local.connection = connection
        return connection

    def close(self) -> None:
        """Closes the connection for the *calling* thread only — there is no
        general way to reach into another thread's connection. Callers that
        only ever use one thread (every current caller does) see the same
        behavior as a single shared connection."""
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None
