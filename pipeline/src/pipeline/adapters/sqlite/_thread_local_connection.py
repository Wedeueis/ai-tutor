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

_ADD_COLUMNS = (
    ("intake_items", "ordinal", "INTEGER"),
)
"""Columns added to tables that already existed in someone's database.

`schema.sql` is idempotent `CREATE TABLE IF NOT EXISTS` DDL, which is exactly
wrong for adding a column: the table exists, so the new definition is skipped
and the column silently never appears — every later query then fails with
`no such column` on a database that looks fine.

SQLite has no `ADD COLUMN IF NOT EXISTS`, so each entry here is attempted and
its "duplicate column name" refusal swallowed. This is deliberately not a
migration *framework*: there are no versions and no down-migrations, because
every table here except `bundle_log` is derived state that `pipeline index`
can rebuild. It exists so that adding a nullable column does not require
every developer to delete their database."""


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
            _add_missing_columns(connection)
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


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Idempotent, and narrow on purpose: only "duplicate column name" is
    swallowed. Any other `OperationalError` — a typo'd table, a bad type — is
    a real defect and must surface at startup rather than be mistaken for
    "already applied"."""
    for table, column, declared_type in _ADD_COLUMNS:
        try:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {declared_type}"
            )
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise
