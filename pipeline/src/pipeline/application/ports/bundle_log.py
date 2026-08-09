from __future__ import annotations

from typing import Protocol


class BundleLogPort(Protocol):
    """Appends an entry to the bundle's log.md (WIKI_SPEC.md §9)."""

    def append(self, message: str) -> None: ...
