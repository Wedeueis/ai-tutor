"""Discovers new or changed files under a root and registers them in the intake
tracker. Doesn't parse or ingest anything — just makes them visible to the queue."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.application.ports.filesystem_scanner import FileSystemScannerPort
from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.domain.intake import IntakeItem, IntakeState, classify_kind


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
