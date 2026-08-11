"""Discovers new or changed files under a root and registers them in the intake
tracker. Doesn't parse or ingest anything — just makes them visible to the queue."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.application.ports.filesystem_scanner import FileSystemScannerPort
from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.domain.intake import IntakeItem, IntakeState, classify_kind

_STALE_STATES = (IntakeState.DISCOVERED, IntakeState.ERROR)
"""States it's safe to silently supersede when a path's content changes: nothing
was ever derived from that content (no chunks, no concepts), so the old row is
just noise, not history. PARSED/INGESTED/REJECTED items are left in place even
when their path's content later changes — they're the audit record of what was
actually parsed/ingested/rejected, not something to discard."""


class ScanIntake:
    def __init__(
        self, scanner: FileSystemScannerPort, intake_repository: IntakeRepositoryPort
    ) -> None:
        self._scanner = scanner
        self._intake_repository = intake_repository

    def run(self, root: str) -> list[IntakeItem]:
        new_items: list[IntakeItem] = []
        for scanned in self._scanner.scan(root):
            kind = classify_kind(scanned.path)
            if kind is None:
                continue

            existing = self._intake_repository.find_by_path(scanned.path)
            if existing is not None and existing.id == scanned.content_hash:
                continue  # unchanged, already tracked

            if existing is not None and existing.state in _STALE_STATES:
                self._intake_repository.delete(existing.id)

            now = datetime.now(UTC)
            item = IntakeItem(
                id=scanned.content_hash,
                kind=kind,
                state=IntakeState.DISCOVERED,
                path=scanned.path,
                discovered_at=now,
                updated_at=now,
            )
            self._intake_repository.upsert(item)
            new_items.append(item)
        return new_items
