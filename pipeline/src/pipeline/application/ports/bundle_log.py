from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class LogEntry:
    """One ingest decision (create/merge/reject) recorded by BundleLogPort —
    the pipeline's audit trail, not vault content."""

    action: str
    concept_id: str | None
    raw_id: str | None
    message: str
    at: datetime


class BundleLogPort(Protocol):
    """Records and queries the pipeline's ingest audit trail (create/merge/
    reject decisions). This is pipeline governance state, not the OKF
    bundle's optional log.md (WIKI_SPEC.md §9) — see docs/architecture/
    ports-and-adapters.md for why."""

    def append(
        self, action: str, concept_id: str | None, raw_id: str | None, message: str
    ) -> None: ...

    def list_entries(self) -> list[LogEntry]: ...
