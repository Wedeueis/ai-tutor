from __future__ import annotations

from typing import Protocol

from pipeline.domain.raw_material import RawItem


class RawMaterialRepositoryPort(Protocol):
    """Reads ingestible capture items (raw notes and parsed chunks, tracked in the
    intake DB — see IntakeRepositoryPort) and records their outcome."""

    def list_unprocessed(self) -> list[RawItem]: ...

    def mark_processed(self, raw_id: str) -> None: ...

    def mark_rejected(self, raw_id: str, reason: str) -> None: ...

    def link_concept(self, raw_id: str, concept_id: str) -> None: ...
