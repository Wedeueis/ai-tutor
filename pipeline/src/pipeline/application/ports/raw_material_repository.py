from __future__ import annotations

from typing import Protocol

from pipeline.domain.raw_material import RawItem


class RawMaterialRepositoryPort(Protocol):
    """Reads ingestible capture items (raw notes and parsed chunks, tracked in the
    intake DB — see IntakeRepositoryPort) and records their outcome."""

    def list_unprocessed(self) -> list[RawItem]: ...

    def mark_processed(self, raw_id: str) -> None: ...

    def mark_rejected(self, raw_id: str, reason: str) -> None: ...

    def mark_error(self, raw_id: str, message: str) -> None:
        """An unexpected failure (not a quality-eval rejection) interrupted
        processing — e.g. Ollama was unreachable, a skill's response couldn't
        be parsed. Distinct from `mark_rejected`: this is retryable via
        `pipeline retry <item-id>` once the underlying cause is fixed, whereas
        a rejection is a considered decision the KnowledgeAgent made."""
        ...

    def link_concept(self, raw_id: str, concept_id: str) -> None: ...

    def find_source_concept(self, source_id: str) -> str | None:
        """The reference-hub concept id representing the source document
        `source_id` (a chunk's `RawItem.source_id`), if one has been created
        for it yet — see ParseSourceDocuments. `None` for raw notes (which
        have no source document) or a source not yet parsed into a hub."""
        ...
