"""Turns discovered binary source documents into chunks the existing ingestion
pipeline can consume, with no changes needed to KnowledgeAgent/IngestRawMaterial:
a chunk is just another DB-only IntakeItem in state `discovered`. Also creates
a durable `references/` hub concept per source document (§5.1 provenance
target — see `_ensure_source_hub`) that `IngestRawMaterial` later points every
derived concept's `sources[]` at."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.application.ports.parsing import DocumentParsingPort
from pipeline.application.ports.skills.image_captioning import ImageCaptioningSkillPort
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.domain.chunking import DEFAULT_MAX_CHARS, chunk_markdown
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from pipeline.domain.slug import slugify
from pipeline.domain.text_quality import looks_like_garbled_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseOutcome:
    source_id: str
    chunk_ids: list[str] = field(default_factory=list)
    skipped: int = 0
    """Chunks that looked like a garbled table dump (`looks_like_garbled_table`)
    rather than prose — e.g. a Docling table-parse artifact — and so were
    never registered as an IntakeItem. Nothing is destroyed: the source
    document is untouched in vault/raw/, this just keeps parser noise from
    ever reaching extraction."""
    errored: str | None = None
    """Set when parsing this source document raised unexpectedly (Docling
    failure, captioning skill unreachable, ...). The source is marked
    `IntakeState.ERROR` (retryable via `pipeline retry <item-id>`) instead of
    `PARSED`, and every other source in the batch still gets processed."""


class ParseSourceDocuments:
    def __init__(
        self,
        intake_repository: IntakeRepositoryPort,
        parsing: DocumentParsingPort,
        image_captioning: ImageCaptioningSkillPort,
        concept_repository: ConceptRepositoryPort,
        index_concept: IndexConcept,
        bundle_log: BundleLogPort,
        max_chunk_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._intake_repository = intake_repository
        self._parsing = parsing
        self._image_captioning = image_captioning
        self._concept_repository = concept_repository
        self._index_concept = index_concept
        self._bundle_log = bundle_log
        self._max_chunk_chars = max_chunk_chars

    def run(self) -> list[ParseOutcome]:
        sources = self._intake_repository.list_by_state(
            IntakeState.DISCOVERED, kind=IntakeKind.SOURCE_DOCUMENT
        )
        logger.info("parse-sources: %d source document(s) to parse", len(sources))
        outcomes = []
        for source in sources:
            try:
                outcome = self._parse_one(source)
            except Exception as exc:  # noqa: BLE001 - isolate one bad document, keep the batch going
                logger.exception(
                    "parse-sources: %s failed unexpectedly, marking as error", source.id
                )
                source.state = IntakeState.ERROR
                source.error_message = str(exc)
                source.updated_at = datetime.now(UTC)
                self._intake_repository.upsert(source)
                outcome = ParseOutcome(source_id=source.id, errored=str(exc))
            else:
                logger.info(
                    "parse-sources: %s -> %d chunk(s), %d skipped as garbled",
                    source.id,
                    len(outcome.chunk_ids),
                    outcome.skipped,
                )
            outcomes.append(outcome)
        return outcomes

    def _parse_one(self, source: IntakeItem) -> ParseOutcome:
        if source.path is None:
            # SOURCE_DOCUMENT items are file-backed by construction (see
            # domain/intake.py's extension-based classification); a pathless one
            # is a malformed row, not something to parse as empty.
            raise ValueError(f"source document {source.id} has no path")
        self._ensure_source_hub(source)
        parsed = self._parsing.parse(source.path)

        text = parsed.text
        for image in parsed.images:
            caption = self._image_captioning.caption(image)
            text = text.replace(image.anchor, f"[image: {caption}]")

        now = datetime.now(UTC)
        chunk_ids = []
        skipped = 0
        for index, chunk_text in enumerate(chunk_markdown(text, self._max_chunk_chars)):
            if looks_like_garbled_table(chunk_text):
                skipped += 1
                continue
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

        return ParseOutcome(source_id=source.id, chunk_ids=chunk_ids, skipped=skipped)

    def _ensure_source_hub(self, source: IntakeItem) -> None:
        """Creates a durable `references/` stub concept representing this
        source document, the first time it's parsed — idempotent across
        re-parses (checked via the same intake_item_concepts link chunks use
        to point at their concepts, reused here for source->hub). Every
        concept later derived from this source's chunks points its §5.1
        `sources[]` back at it — see IngestRawMaterial."""
        if self._intake_repository.list_concepts_for(source.id):
            return

        filename = Path(source.path).name if source.path else source.id[:12]
        title = Path(source.path).stem if source.path else source.id[:12]
        base = slugify(title)
        hub_id = ConceptId(f"references/{base}")
        suffix = 2
        while self._concept_repository.exists(hub_id):
            hub_id = ConceptId(f"references/{base}-{suffix}")
            suffix += 1

        hub = Concept(
            id=hub_id,
            frontmatter=Frontmatter(
                type="Source Document",
                title=title,
                description=f"Source document ingested from raw/{filename}.",
            ),
            body=f"Source document parsed from `raw/{filename}`.",
        )
        self._concept_repository.save(hub)
        self._index_concept.run(hub)
        self._intake_repository.link_concept(source.id, str(hub_id))
        self._bundle_log.append(
            action="create",
            concept_id=str(hub_id),
            raw_id=source.id,
            message=f"Added source document hub for {title}.",
        )
