"""RawMaterialRepositoryPort backed by the intake tracker — no more moving files
between folders; state lives in IntakeRepositoryPort, the DB is the source of
truth (see domain/intake.py)."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.application.ports.filesystem_scanner import FileSystemScannerPort
from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.domain.intake import IntakeKind, IntakeState
from pipeline.domain.raw_material import RawItem

_INGESTIBLE_KINDS = (IntakeKind.RAW_NOTE, IntakeKind.CHUNK)


class FilesystemRawMaterialRepository:
    def __init__(
        self, intake_repository: IntakeRepositoryPort, scanner: FileSystemScannerPort
    ) -> None:
        self._intake_repository = intake_repository
        self._scanner = scanner

    def list_unprocessed(self) -> list[RawItem]:
        raw_items = []
        for kind in _INGESTIBLE_KINDS:
            for item in self._intake_repository.list_by_state(IntakeState.DISCOVERED, kind=kind):
                content = (
                    item.content if item.content is not None else self._scanner.read_text(item.path)
                )
                raw_items.append(RawItem(id=item.id, content=content))
        return raw_items

    def mark_processed(self, raw_id: str) -> None:
        self._transition(raw_id, IntakeState.INGESTED)

    def mark_rejected(self, raw_id: str, reason: str) -> None:
        self._transition(raw_id, IntakeState.REJECTED, error_message=reason)

    def mark_error(self, raw_id: str, message: str) -> None:
        self._transition(raw_id, IntakeState.ERROR, error_message=message)

    def link_concept(self, raw_id: str, concept_id: str) -> None:
        self._intake_repository.link_concept(raw_id, concept_id)

    def _transition(self, raw_id: str, state: IntakeState, error_message: str | None = None) -> None:
        item = self._intake_repository.get(raw_id)
        if item is None:
            raise ValueError(f"no intake item with id {raw_id!r} — was it discovered by `pipeline scan`?")
        item.state = state
        item.error_message = error_message
        item.updated_at = datetime.now(UTC)
        self._intake_repository.upsert(item)
