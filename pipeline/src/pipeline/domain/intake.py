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

_EXCLUDED_DIRECTORY = "inquiries"
"""`vault/raw/inquiries/` holds *questions about* the knowledge — coverage gaps
and contradictions the tutor notices while teaching — not material to distil.
Ingesting one would produce a concept describing the gap rather than one
filling it, so it is excluded here by path, which is the single rule that
folder's README promises. Answering an inquiry needs a research-and-synthesise
flow this pipeline does not have yet (issue #15)."""


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
    if _EXCLUDED_DIRECTORY in PurePath(path).parts:
        return None
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
    ordinal: int | None = None
    """Position in the parent document, 0-based. Set for chunks, `None` for
    file-backed items, which have no position in anything.

    Stored rather than derived because it was previously *only* baked into the
    id hash: every chunk of a document shares one `discovered_at`, so ordering
    was unrecoverable. It is what makes a §5.1 `sources[].id` legible
    (`the-paper-p17` rather than a hex digest) and what lets a passage be
    located within its document."""
    error_message: str | None = None
    discovered_at: datetime | None = None
    updated_at: datetime | None = None
