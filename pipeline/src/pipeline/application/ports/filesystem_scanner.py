from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ScannedFile:
    path: str
    content_hash: str


class FileSystemScannerPort(Protocol):
    """Enumerates files under a root and hashes their content; separately reads a
    file's text back out for items whose content isn't cached in the DB."""

    def scan(self, root: str) -> list[ScannedFile]: ...

    def read_text(self, path: str) -> str: ...
