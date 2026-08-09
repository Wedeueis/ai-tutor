"""Intake tracking: the DB-backed state every file dropped into vault/raw/ (and
every chunk derived from one) moves through. Pure domain — no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import PurePath

_RAW_NOTE_EXTENSIONS = {".md", ".txt"}
_SOURCE_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".pptx",
    ".docx",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
}


class IntakeState(str, Enum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    INGESTED = "ingested"
    REJECTED = "rejected"
    ERROR = "error"


class IntakeKind(str, Enum):
    RAW_NOTE = "raw_note"
    SOURCE_DOCUMENT = "source_document"
    CHUNK = "chunk"


def classify_kind(path: str) -> IntakeKind | None:
    """Extension-based classification. Returns None for unrecognized files, which
    the scanner should skip rather than track."""
    suffix = PurePath(path).suffix.lower()
    if suffix in _RAW_NOTE_EXTENSIONS:
        return IntakeKind.RAW_NOTE
    if suffix in _SOURCE_DOCUMENT_EXTENSIONS:
        return IntakeKind.SOURCE_DOCUMENT
    return None


@dataclass
class IntakeItem:
    """One tracked file (or chunk derived from one) and its pipeline state."""

    id: str  # content hash — stable identity
    kind: IntakeKind
    state: IntakeState
    path: str | None = None  # set for file-backed items (raw notes, source documents)
    content: str | None = None  # set for DB-only items (chunks)
    parent_id: str | None = None  # source document's id, for chunks
    error_message: str | None = None
    discovered_at: datetime | None = None
    updated_at: datetime | None = None
