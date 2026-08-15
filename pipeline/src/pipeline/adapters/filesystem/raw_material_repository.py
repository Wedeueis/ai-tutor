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
                # An intake row is either DB-only (content set, e.g. a chunk) or
                # file-backed (path set). Neither means a malformed row, and
                # reading it as empty content would ingest a blank concept.
                if item.content is not None:
                    content = item.content
                elif item.path is not None:
                    content = self._scanner.read_text(item.path)
                else:
                    raise ValueError(f"intake item {item.id} has neither content nor path")
                raw_items.append(RawItem(id=item.id, content=content, source_id=item.parent_id))
        return raw_items

    def mark_processed(self, raw_id: str) -> None:
        self._transition(raw_id, IntakeState.INGESTED)

    def mark_rejected(self, raw_id: str, reason: str) -> None:
        self._transition(raw_id, IntakeState.REJECTED, error_message=reason)

    def mark_error(self, raw_id: str, message: str) -> None:
        self._transition(raw_id, IntakeState.ERROR, error_message=message)

    def link_concept(self, raw_id: str, concept_id: str) -> None:
        self._intake_repository.link_concept(raw_id, concept_id)

    def find_source_concept(self, source_id: str) -> str | None:
        concepts = self._intake_repository.list_concepts_for(source_id)
        return concepts[0] if concepts else None

    def _transition(self, raw_id: str, state: IntakeState, error_message: str | None = None) -> None:
        item = self._intake_repository.get(raw_id)
        if item is None:
            raise ValueError(f"no intake item with id {raw_id!r} — was it discovered by `pipeline scan`?")
        item.state = state
        item.error_message = error_message
        item.updated_at = datetime.now(UTC)
        self._intake_repository.upsert(item)
