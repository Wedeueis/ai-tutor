"""Unprocessed capture-inbox material (vault/raw/ — not part of the OKF bundle)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawItem:
    id: str
    content: str
    source_id: str | None = None
    """The parent source document's intake-item id, for a chunk parsed out of
    a larger document (see parse_source_documents.py). `None` for raw notes
    and anything else. Read only by IngestRawMaterial, purely for §5.1
    provenance stamping — KnowledgeAgent's decision-making never looks at
    this, chunks and raw notes are still judged identically."""

    ordinal: int | None = None
    """Position in the parent document, 0-based — carried alongside
    `source_id` for the same reason and read by the same caller: it is half of
    the §5.1 `sources[].id` this chunk earns on the concept it produces."""
