from __future__ import annotations

from typing import Protocol

from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState


class IntakeRepositoryPort(Protocol):
    """The single source of truth for what the pipeline knows about a file (or a
    chunk derived from one) and what state it's in."""

    def find_by_path(self, path: str) -> IntakeItem | None: ...

    def upsert(self, item: IntakeItem) -> None: ...

    def get(self, item_id: str) -> IntakeItem | None: ...

    def list_by_state(
        self, state: IntakeState, kind: IntakeKind | None = None
    ) -> list[IntakeItem]: ...

    def list_children(self, parent_id: str) -> list[IntakeItem]: ...

    def link_concept(self, item_id: str, concept_id: str) -> None: ...

    def list_concepts_for(self, item_id: str) -> list[str]: ...

    def delete(self, item_id: str) -> None: ...

    def list_stale_duplicates(self) -> list[IntakeItem]:
        """Items superseded at their own path by a later hash (content changed
        since they were tracked) that never got past `discovered`/`error` — i.e.
        nothing was ever derived from them. `ScanIntake` already prevents new
        ones from accumulating; this is for cleaning up ones that predate that,
        or that slipped through some other way."""
        ...
