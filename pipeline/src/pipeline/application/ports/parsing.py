from __future__ import annotations

from typing import Protocol

from pipeline.domain.source_document import ParsedDocument


class DocumentParsingPort(Protocol):
    """Turns a binary source file (PDF, PPTX, DOCX, XLSX, image...) into normalized
    markdown text plus any extracted images. The only thing that knows which
    concrete parsing library is in use — swap the adapter, keep this port."""

    def parse(self, path: str) -> ParsedDocument: ...
