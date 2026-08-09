"""FileSystemScannerPort backed by the local filesystem — hashes file content for
stable identity and reads text back out on demand."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pipeline.application.ports.filesystem_scanner import ScannedFile

_IGNORED_NAMES = {"README.md"}


class FilesystemScanner:
    def scan(self, root: str) -> list[ScannedFile]:
        root_path = Path(root)
        if not root_path.exists():
            return []

        files = []
        for path in sorted(root_path.rglob("*")):
            if not path.is_file() or path.name in _IGNORED_NAMES:
                continue
            relative = path.relative_to(root_path)
            if any(part.startswith(".") for part in relative.parts):
                continue
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append(ScannedFile(path=str(path), content_hash=content_hash))
        return files

    def read_text(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")
