from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class IndexFingerprint:
    """What produced the vectors currently in the index.

    `dimensions` is recorded rather than configured because it is a property of
    the model's output, not a choice — and it is the one value that proves the
    stored vectors really came from the model the name claims."""

    embed_model: str
    dimensions: int
    query_instruction: str = ""


class IndexFingerprintPort(Protocol):
    def read(self) -> IndexFingerprint | None:
        """`None` means nothing has been indexed yet — a new index, not a
        mismatched one. The distinction matters: one is fine, the other is
        corruption."""
        ...

    def write(self, fingerprint: IndexFingerprint) -> None: ...

    def clear(self) -> None:
        """Called when the vectors go away, so the next index run records
        itself afresh instead of being compared against a ghost."""
        ...
