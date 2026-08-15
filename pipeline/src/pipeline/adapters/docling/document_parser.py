"""DocumentParsingPort adapter backed by Docling — local-first, layout-aware
PDF/DOCX/PPTX/XLSX/image parsing. The only module in the codebase that knows
Docling exists; swapping backends later means writing one new adapter here."""

from __future__ import annotations

import hashlib
from pathlib import Path

from docling.document_converter import DocumentConverter
from pipeline.adapters.docling.source_metadata import read_document_metadata
from pipeline.domain.source_document import ParsedDocument, ParsedImage

_IMAGE_PLACEHOLDER = "<!-- image -->"


class DoclingDocumentParser:
    def __init__(self, image_output_dir: Path) -> None:
        self._image_output_dir = image_output_dir
        self._converter = DocumentConverter()

    def parse(self, path: str) -> ParsedDocument:
        result = self._converter.convert(path)
        document = result.document

        markdown = document.export_to_markdown(image_placeholder=_IMAGE_PLACEHOLDER)

        images: list[ParsedImage] = []
        source_stem = hashlib.sha256(path.encode()).hexdigest()[:12]
        for index, picture in enumerate(document.pictures):
            anchor = f"{{{{image:{index}}}}}"
            markdown = markdown.replace(_IMAGE_PLACEHOLDER, anchor, 1)

            pil_image = picture.get_image(document)
            if pil_image is None:
                continue
            self._image_output_dir.mkdir(parents=True, exist_ok=True)
            image_path = self._image_output_dir / f"{source_stem}-{index}.png"
            pil_image.save(image_path)
            images.append(ParsedImage(id=f"{source_stem}-{index}", path=str(image_path), anchor=anchor))

        # Captured here or not at all: the signals are cheap while the document
        # is open and expensive to reconstruct afterwards (ADR 0001).
        return ParsedDocument(
            text=markdown, images=images, metadata=read_document_metadata(path)
        )
