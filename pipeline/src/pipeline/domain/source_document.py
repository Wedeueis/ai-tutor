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
class ParsedDocument:
    text: str
    images: list[ParsedImage] = field(default_factory=list)
