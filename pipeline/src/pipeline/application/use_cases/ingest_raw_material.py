"""Drives every unprocessed vault/raw/ item through the KnowledgeAgent, then applies
its create/merge decisions to the bundle and indexes whatever changed. Also
writes reciprocal relatedness backlinks into existing concepts a new concept
was judged related to (see `_write_reciprocal_backlinks`), and — for concepts
derived from a parsed source document — stamps §5.1 `sources[]` provenance
back at that document's `references/` hub and updates the hub's own
"## Derived concepts" list (see `_update_source_hub`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.raw_material_repository import (
    RawMaterialRepositoryPort,
)
from pipeline.application.use_cases.category_materializer import CategoryMaterializer
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import CreateDecision, MergeDecision, RejectDecision, RelatedConcept
from pipeline.domain.concept import Concept, ConceptId, Frontmatter, Source
from pipeline.domain.linking import (
    add_footnote,
    add_link_section,
    add_related_links,
    cite,
    cite_body,
    insert_before_related,
)
from pipeline.domain.prerequisites import PrerequisiteEdge
from pipeline.domain.raw_material import RawItem
from pipeline.domain.slug import slugify

_DERIVED_CONCEPTS_HEADING = "## Derived concepts"

logger = logging.getLogger(__name__)


def _source_id(source_concept_id: str, raw: RawItem) -> str:
    """A stable §5.1 `sources[].id` — and therefore a footnote label.

    `<document-slug>-p<ordinal>` reads as something a person can act on, which
    a content hash does not. The ordinal is the chunk's position in the parsed
    document; a chunk written before that column existed falls back to a short
    hash prefix, which is ugly but still stable and still unique."""
    slug = source_concept_id.rsplit("/", 1)[-1]
    if raw.ordinal is not None:
        return f"{slug}-p{raw.ordinal}"
    return f"{slug}-{raw.id[:8]}"


def _locator(raw: RawItem) -> str | None:
    """Where in the document, in display text (§5.1, v0.3).

    `passage N` rather than a page number, because the chunker works over
    exported markdown and page provenance is not carried through it yet. The
    field is opaque by design, so tightening this to `p. 42` later changes
    what readers see without changing the schema or the spec."""
    return None if raw.ordinal is None else f"passage {raw.ordinal}"


def _add_source(
    frontmatter: Frontmatter,
    source_concept_id: str,
    hub: Concept | None,
    raw: RawItem,
) -> tuple[Frontmatter, str]:
    """Adds a §5.1 `sources[]` entry for **one contributing passage**, and
    returns the entry's `id` so the body can cite it.

    Deduped by `(resource, id)` rather than by `resource` alone. That is the
    whole change: a concept merged from four chunks of one book used to
    collapse into a single entry saying only "this came from the book
    somewhere", and now carries four, each naming its passage. §5.1 permits a
    repeated `resource`, and `id` is the field it defines for exactly this —
    *"a stable key used to attribute individual claims"*.

    Carries the hub's own credibility signals (`author`, `last_modified`)
    onto the entry, so a consumer judging this concept can see them without
    following the link. They were read from the document at parse time and
    cannot be recovered later (ADR 0001). Whatever the hub doesn't have stays
    `None`: absent means *unknown*, which is neutral, never low."""
    resource = f"/{source_concept_id}.md"
    entry_id = _source_id(source_concept_id, raw)
    if any(s.resource == resource and s.id == entry_id for s in frontmatter.sources):
        return frontmatter, entry_id

    author, last_modified = _credibility_signals(hub)
    return (
        replace(
            frontmatter,
            sources=[
                *frontmatter.sources,
                Source(
                    resource=resource,
                    id=entry_id,
                    title=hub.frontmatter.title if hub else None,
                    author=author,
                    last_modified=last_modified,
                    locator=_locator(raw),
                ),
            ],
        ),
        entry_id,
    )


def _footnote_text(hub: Concept | None, source_concept_id: str, raw: RawItem) -> str:
    """The human-facing half of a footnote.

    §5.1 is explicit that consumers resolve attribution through the matching
    `sources` entry and *not* by parsing this prose, so it is free to be
    readable rather than structured."""
    title = (hub.frontmatter.title if hub else None) or source_concept_id
    locator = _locator(raw)
    return f"{title} — {locator}" if locator else title


def _credibility_signals(hub: Concept | None) -> tuple[str | None, str | None]:
    """The hub records the document's signals on its own `sources[]` entry
    (see `ParseSourceDocuments._ensure_source_hub`). A hub predating that —
    or one whose document declared nothing — yields empty signals."""
    if hub is None or not hub.frontmatter.sources:
        return None, None
    origin = hub.frontmatter.sources[0]
    return origin.author, origin.last_modified


@dataclass(frozen=True)
class IngestOutcome:
    raw_id: str
    created: list[ConceptId] = field(default_factory=list)
    merged_into: list[ConceptId] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    errored: str | None = None
    """Set when an unexpected exception interrupted this item (Ollama down,
    an unparsable skill response, ...) rather than a considered rejection.
    The item is left retryable via `pipeline retry <item-id>` and every other
    item in the batch still gets processed — see `run()`."""


class IngestRawMaterial:
    def __init__(
        self,
        raw_material_repository: RawMaterialRepositoryPort,
        knowledge_agent: KnowledgeAgent,
        concept_repository: ConceptRepositoryPort,
        index_concept: IndexConcept,
        bundle_log: BundleLogPort,
    ) -> None:
        self._raw_material_repository = raw_material_repository
        self._knowledge_agent = knowledge_agent
        self._concept_repository = concept_repository
        self._index_concept = index_concept
        self._bundle_log = bundle_log
        self._category_materializer = CategoryMaterializer(
            concept_repository, index_concept, bundle_log
        )

    def run(self) -> list[IngestOutcome]:
        unprocessed = self._raw_material_repository.list_unprocessed()
        logger.info("ingest: %d unprocessed item(s)", len(unprocessed))
        outcomes: list[IngestOutcome] = []
        for raw in unprocessed:
            try:
                outcome = self._ingest_one(raw)
            except Exception as exc:  # noqa: BLE001 - isolate one bad item, keep the batch going
                logger.exception("ingest: raw/%s failed unexpectedly, marking as error", raw.id)
                self._raw_material_repository.mark_error(raw.id, str(exc))
                outcomes.append(IngestOutcome(raw_id=raw.id, errored=str(exc)))
                continue

            outcomes.append(outcome)
            if outcome.rejected and not (outcome.created or outcome.merged_into):
                self._raw_material_repository.mark_rejected(
                    raw.id, "; ".join(outcome.rejected)
                )
            else:
                self._raw_material_repository.mark_processed(raw.id)
            logger.info(
                "ingest: raw/%s -> created=%d merged=%d rejected=%d",
                raw.id,
                len(outcome.created),
                len(outcome.merged_into),
                len(outcome.rejected),
            )
        return outcomes

    def _ingest_one(self, raw: RawItem) -> IngestOutcome:
        agent_result = self._knowledge_agent.run(raw)
        source_concept_id = (
            self._raw_material_repository.find_source_concept(raw.source_id)
            if raw.source_id
            else None
        )
        # Loaded once per raw item, not per decision: its credibility signals
        # are the same for every concept derived from this source.
        source_hub = (
            self._concept_repository.load(ConceptId(source_concept_id))
            if source_concept_id
            else None
        )

        created: list[ConceptId] = []
        merged_into: list[ConceptId] = []
        rejected: list[str] = []

        for decision in agent_result.decisions:
            if isinstance(decision, CreateDecision):
                concept = self._materialize(decision)
                concept = self._category_materializer.link_new_categories(
                    concept, decision.new_categories, raw.id
                )
                if source_concept_id:
                    frontmatter, entry_id = _add_source(
                        concept.frontmatter, source_concept_id, source_hub, raw
                    )
                    # Cited on create as well as on merge, so every body is
                    # attributed by the same rule. A concept that later merges
                    # a second passage then needs no retro-marking of the text
                    # that was already there — one code path, no special case.
                    concept = replace(
                        concept,
                        frontmatter=frontmatter,
                        body=add_footnote(
                            cite_body(concept.body, entry_id),
                            entry_id,
                            _footnote_text(source_hub, source_concept_id, raw),
                        ),
                    )
                self._concept_repository.save(concept)
                self._index_concept.run(concept)
                self._bundle_log.append(
                    action="create",
                    concept_id=str(concept.id),
                    raw_id=raw.id,
                    message=f"Added {concept.frontmatter.title or concept.id}, drafted from raw/{raw.id}.",
                )
                created.append(concept.id)
                self._raw_material_repository.link_concept(raw.id, str(concept.id))
                self._log_prerequisites(concept, decision.prerequisites, raw.id)
                self._write_reciprocal_backlinks(concept, decision.related, raw.id)
                if source_concept_id:
                    self._update_source_hub(concept, source_concept_id, raw.id)
            elif isinstance(decision, MergeDecision):
                existing = self._concept_repository.load(decision.into)
                addition = decision.addition
                merged_frontmatter = existing.frontmatter
                merged_body = existing.body
                if source_concept_id:
                    merged_frontmatter, entry_id = _add_source(
                        existing.frontmatter, source_concept_id, source_hub, raw
                    )
                    # A merged body now mixes text from two different passages,
                    # which is precisely when concept-level attribution stops
                    # being enough and the footnote starts carrying meaning.
                    addition = cite(addition, entry_id)
                    merged_body = add_footnote(
                        merged_body,
                        entry_id,
                        _footnote_text(source_hub, source_concept_id, raw),
                    )
                merged = replace(
                    existing,
                    frontmatter=merged_frontmatter,
                    body=insert_before_related(merged_body, addition),
                )
                self._concept_repository.save(merged)
                self._index_concept.run(merged)
                self._bundle_log.append(
                    action="merge",
                    concept_id=str(merged.id),
                    raw_id=raw.id,
                    message=f"Merged raw/{raw.id} into {merged.frontmatter.title or merged.id}.",
                )
                merged_into.append(decision.into)
                self._raw_material_repository.link_concept(raw.id, str(decision.into))
                if source_concept_id:
                    self._update_source_hub(merged, source_concept_id, raw.id)
            elif isinstance(decision, RejectDecision):
                self._bundle_log.append(
                    action="reject",
                    concept_id=None,
                    raw_id=raw.id,
                    message=decision.rationale,
                )
                rejected.append(decision.rationale)

        return IngestOutcome(
            raw_id=raw.id, created=created, merged_into=merged_into, rejected=rejected
        )

    def _log_prerequisites(
        self, concept: Concept, prerequisites: list[PrerequisiteEdge], raw_id: str
    ) -> None:
        """Records each emitted edge in the bundle log. The edge itself is
        already in `concept.body` (KnowledgeAgent wove it in) and needs no
        write here — but the *rationale* does: it is the only place a human
        reviewing a `may_require::` edge can find out why the gate demoted it,
        since the body deliberately carries the bare line and nothing else."""
        for edge in prerequisites:
            self._bundle_log.append(
                action="require",
                concept_id=str(concept.id),
                raw_id=raw_id,
                message=(
                    f"{edge.relation_type}: {concept.frontmatter.title or concept.id} -> "
                    f"{edge.target_id} (score {edge.eval.average_score:.2f})"
                    + (f" — {edge.rationale}" if edge.rationale else "")
                ),
            )

    def _write_reciprocal_backlinks(
        self, concept: Concept, related: list[RelatedConcept], raw_id: str
    ) -> None:
        """A new concept's forward links to related concepts are already in
        its own body (KnowledgeAgent wove them in). This writes the reverse
        edge into each existing related concept's body too, bounded to the
        few candidates already judged related — the fix for relatedness
        otherwise being one-directional and order-dependent (an old concept
        could never gain a link to something genuinely related created after
        it)."""
        for link in related:
            existing = self._concept_repository.load(link.concept_id)
            back_link = replace(link, concept_id=concept.id, title=concept.frontmatter.title)
            new_body = add_related_links(existing.body, [back_link])
            if new_body == existing.body:
                continue  # already linked — dedup no-op

            updated = replace(existing, body=new_body)
            self._concept_repository.save(updated)
            self._index_concept.run(updated)
            self._bundle_log.append(
                action="relate",
                concept_id=str(updated.id),
                raw_id=raw_id,
                message=f"Linked back to {concept.frontmatter.title or concept.id} as related.",
            )

    def _update_source_hub(self, concept: Concept, source_concept_id: str, raw_id: str) -> None:
        """The concept's own `sources[]` (already stamped by the caller)
        points forward at the hub; this writes the reverse edge into the
        hub's own body, bounded to one hub per raw item — same shape as
        `_write_reciprocal_backlinks`, just for source-document provenance
        instead of semantic relatedness."""
        hub = self._concept_repository.load(ConceptId(source_concept_id))
        link = RelatedConcept(concept_id=concept.id, title=concept.frontmatter.title)
        new_body = add_link_section(hub.body, _DERIVED_CONCEPTS_HEADING, [link])
        if new_body == hub.body:
            return  # already listed — dedup no-op

        updated = replace(hub, body=new_body)
        self._concept_repository.save(updated)
        self._index_concept.run(updated)
        self._bundle_log.append(
            action="derive",
            concept_id=str(updated.id),
            raw_id=raw_id,
            message=f"Added {concept.frontmatter.title or concept.id} as derived from {hub.frontmatter.title or hub.id}.",
        )

    def _materialize(self, decision: CreateDecision) -> Concept:
        draft = decision.concept
        base = slugify(draft.frontmatter.title or draft.source_raw_id)
        concept_id = ConceptId(base)
        suffix = 2
        while self._concept_repository.exists(concept_id):
            concept_id = ConceptId(f"{base}-{suffix}")
            suffix += 1
        return Concept(id=concept_id, frontmatter=draft.frontmatter, body=draft.body)
