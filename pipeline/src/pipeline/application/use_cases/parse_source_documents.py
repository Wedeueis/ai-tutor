"""Turns discovered binary source documents into chunks the existing ingestion
pipeline can consume, with no changes needed to KnowledgeAgent/IngestRawMaterial:
a chunk is just another DB-only IntakeItem in state `discovered`."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.application.ports.parsing import DocumentParsingPort
from pipeline.application.ports.skills.image_captioning import ImageCaptioningSkillPort
from pipeline.domain.chunking import DEFAULT_MAX_CHARS, chunk_markdown
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState


@dataclass(frozen=True)
class ParseOutcome:
    source_id: str
    chunk_ids: list[str] = field(default_factory=list)


class ParseSourceDocuments:
    def __init__(
        self,
        intake_repository: IntakeRepositoryPort,
        parsing: DocumentParsingPort,
        image_captioning: ImageCaptioningSkillPort,
        max_chunk_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._intake_repository = intake_repository
        self._parsing = parsing
        self._image_captioning = image_captioning
        self._max_chunk_chars = max_chunk_chars

    def run(self) -> list[ParseOutcome]:
        sources = self._intake_repository.list_by_state(
            IntakeState.DISCOVERED, kind=IntakeKind.SOURCE_DOCUMENT
        )
        return [self._parse_one(source) for source in sources]

    def _parse_one(self, source: IntakeItem) -> ParseOutcome:
        parsed = self._parsing.parse(source.path)

        text = parsed.text
        for image in parsed.images:
            caption = self._image_captioning.caption(image)
            text = text.replace(image.anchor, f"[image: {caption}]")

        now = datetime.now(timezone.utc)
        chunk_ids = []
        for index, chunk_text in enumerate(chunk_markdown(text, self._max_chunk_chars)):
            chunk_id = hashlib.sha256(f"{source.id}:{index}:{chunk_text}".encode()).hexdigest()
            self._intake_repository.upsert(
                IntakeItem(
                    id=chunk_id,
                    kind=IntakeKind.CHUNK,
                    state=IntakeState.DISCOVERED,
                    path=None,
                    content=chunk_text,
                    parent_id=source.id,
                    discovered_at=now,
                    updated_at=now,
                )
            )
            chunk_ids.append(chunk_id)

        source.state = IntakeState.PARSED
        source.updated_at = now
        self._intake_repository.upsert(source)

        return ParseOutcome(source_id=source.id, chunk_ids=chunk_ids)
