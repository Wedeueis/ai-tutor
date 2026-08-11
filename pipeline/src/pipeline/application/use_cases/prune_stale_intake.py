"""Deletes intake items superseded by a later hash at the same path that never
got past `discovered`/`error` — orphaned rows nothing was ever derived from.
`ScanIntake` already prevents new ones from accumulating (see scan_intake.py);
this is for cleaning up ones that predate that, or that slipped through
another way (e.g. a manual DB edit)."""

from __future__ import annotations

from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.domain.intake import IntakeItem


class PruneStaleIntake:
    def __init__(self, intake_repository: IntakeRepositoryPort) -> None:
        self._intake_repository = intake_repository

    def run(self) -> list[IntakeItem]:
        stale = self._intake_repository.list_stale_duplicates()
        for item in stale:
            self._intake_repository.delete(item.id)
        return stale
