"""What a DocumentParsingPort adapter hands back. Pure domain — no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedImage:
    """One image extracted from a source document, with a placeholder token
    (`anchor`) marking its position in the parsed text, to be replaced with a
    caption."""

    id: str
    path: str
    anchor: str


@dataclass(frozen=True)
class DocumentMetadata:
    """The §5.1 credibility signals a source document carries about itself.

    Both are optional and routinely absent — two of the four PDFs in this
    vault declare no author at all. Absent means *unknown*, which ADR 0001
    requires consumers to treat as neutral, never as low. `last_modified` is
    `YYYY-MM-DD` per §5.1."""

    author: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    images: list[ParsedImage] = field(default_factory=list)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)
