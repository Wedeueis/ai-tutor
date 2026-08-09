from __future__ import annotations

from typing import Protocol

from pipeline.domain.source_document import ParsedImage


class ImageCaptioningSkillPort(Protocol):
    """LLM-backed (vision): describes an extracted image in text, so its meaning
    survives once it's inlined into the parsed document as plain text."""

    def caption(self, image: ParsedImage) -> str: ...
