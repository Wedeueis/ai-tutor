from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    """Turns text into a vector embedding."""

    def embed(self, text: str) -> list[float]: ...
