"""Hand-written in-memory fakes for every port, used to test use cases without any
real Ollama/Chroma/SQLite/filesystem dependency."""

from __future__ import annotations

from pipeline.application.ports.filesystem_scanner import ScannedFile
from pipeline.domain.agent import (
    CandidateMatch,
    CategoryClassificationVerdict,
    DisambiguationVerdict,
    DomainClassificationVerdict,
    DraftConcept,
    QualityAuditVerdict,
    RelatednessVerdict,
    TypeClassificationVerdict,
)
from pipeline.domain.computation import Receipt, Verdict
from pipeline.domain.concept import Concept, ConceptId, LinkGraph
from pipeline.domain.eval import Rubric, RubricScore
from pipeline.domain.intake import IntakeItem, IntakeKind, IntakeState
from pipeline.domain.prerequisites import PrerequisiteAssessment
from pipeline.domain.raw_material import RawItem
from pipeline.domain.relevance import RelevanceEvidence
from pipeline.domain.source_document import ParsedDocument


class FakeConceptRepository:
    def __init__(self) -> None:
        self.concepts: dict[str, Concept] = {}

    def load(self, concept_id: ConceptId) -> Concept:
        return self.concepts[str(concept_id)]

    def save(self, concept: Concept) -> None:
        self.concepts[str(concept.id)] = concept

    def list(self) -> list[ConceptId]:
        return [ConceptId(cid) for cid in self.concepts]

    def exists(self, concept_id: ConceptId) -> bool:
        return str(concept_id) in self.concepts

    def delete(self, concept_id: ConceptId) -> None:
        self.concepts.pop(str(concept_id), None)


class FakeRawMaterialRepository:
    def __init__(
        self,
        items: list[RawItem] | None = None,
        source_concepts: dict[str, str] | None = None,
    ) -> None:
        self.items = list(items or [])
        self.processed: list[str] = []
        self.rejected: dict[str, str] = {}
        self.errored: dict[str, str] = {}
        self.concept_links: dict[str, list[str]] = {}
        self._source_concepts = source_concepts or {}

    def list_unprocessed(self) -> list[RawItem]:
        return [
            item
            for item in self.items
            if item.id not in self.processed
            and item.id not in self.rejected
            and item.id not in self.errored
        ]

    def mark_processed(self, raw_id: str) -> None:
        self.processed.append(raw_id)

    def mark_rejected(self, raw_id: str, reason: str) -> None:
        self.rejected[raw_id] = reason

    def mark_error(self, raw_id: str, message: str) -> None:
        self.errored[raw_id] = message

    def link_concept(self, raw_id: str, concept_id: str) -> None:
        self.concept_links.setdefault(raw_id, []).append(concept_id)

    def find_source_concept(self, source_id: str) -> str | None:
        return self._source_concepts.get(source_id)


class FakeIntakeRepository:
    def __init__(self, items: list[IntakeItem] | None = None) -> None:
        self.items: dict[str, IntakeItem] = {item.id: item for item in (items or [])}
        self.concept_links: dict[str, list[str]] = {}

    def find_by_path(self, path: str) -> IntakeItem | None:
        matches = [item for item in self.items.values() if item.path == path]
        return max(matches, key=lambda item: item.discovered_at) if matches else None

    def upsert(self, item: IntakeItem) -> None:
        self.items[item.id] = item

    def get(self, item_id: str) -> IntakeItem | None:
        return self.items.get(item_id)

    def list_by_state(self, state: IntakeState, kind: IntakeKind | None = None) -> list[IntakeItem]:
        return [
            item
            for item in self.items.values()
            if item.state == state and (kind is None or item.kind == kind)
        ]

    def list_children(self, parent_id: str) -> list[IntakeItem]:
        return [item for item in self.items.values() if item.parent_id == parent_id]

    def link_concept(self, item_id: str, concept_id: str) -> None:
        self.concept_links.setdefault(item_id, [])
        if concept_id not in self.concept_links[item_id]:
            self.concept_links[item_id].append(concept_id)

    def list_concepts_for(self, item_id: str) -> list[str]:
        return self.concept_links.get(item_id, [])

    def delete(self, item_id: str) -> None:
        self.items.pop(item_id, None)
        self.concept_links.pop(item_id, None)

    def list_stale_duplicates(self) -> list[IntakeItem]:
        latest_by_path: dict[str, IntakeItem] = {}
        for item in self.items.values():
            if item.path is None:
                continue
            current = latest_by_path.get(item.path)
            if current is None or item.discovered_at > current.discovered_at:
                latest_by_path[item.path] = item

        return sorted(
            (
                item
                for item in self.items.values()
                if item.path is not None
                and item.state in (IntakeState.DISCOVERED, IntakeState.ERROR)
                and item is not latest_by_path.get(item.path)
            ),
            key=lambda item: item.discovered_at,
        )


class FakeFileSystemScanner:
    def __init__(
        self, files: list[ScannedFile] | None = None, contents: dict[str, str] | None = None
    ) -> None:
        self.files = files or []
        self.contents = contents or {}

    def scan(self, root: str) -> list[ScannedFile]:
        return self.files

    def read_text(self, path: str) -> str:
        return self.contents[path]


class FakeBundleLog:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, action, concept_id, raw_id, message) -> None:
        self.entries.append(
            {"action": action, "concept_id": concept_id, "raw_id": raw_id, "message": message}
        )

    def list_entries(self):
        return list(reversed(self.entries))

    def clear(self) -> int:
        dropped = len(self.entries)
        self.entries.clear()
        return dropped


class FakeExtractionSkill:
    def __init__(self, drafts_by_raw_id: dict[str, list[DraftConcept]]) -> None:
        self._drafts_by_raw_id = drafts_by_raw_id

    def extract(self, raw: RawItem) -> list[DraftConcept]:
        return self._drafts_by_raw_id.get(raw.id, [])


class FakeEntityDisambiguationSkill:
    def __init__(self, verdict: DisambiguationVerdict) -> None:
        self._verdict = verdict

    def disambiguate(self, draft, candidates) -> DisambiguationVerdict:
        return self._verdict


class FakeTypeClassificationSkill:
    def __init__(self, verdict: TypeClassificationVerdict) -> None:
        self._verdict = verdict

    def classify(self, draft, known_types) -> TypeClassificationVerdict:
        return self._verdict


class FakeDomainClassificationSkill:
    def __init__(self, verdict: DomainClassificationVerdict) -> None:
        self._verdict = verdict

    def classify(self, draft, candidates) -> DomainClassificationVerdict:
        return self._verdict


class FakeCategoryClassificationSkill:
    def __init__(self, verdict: CategoryClassificationVerdict | None = None) -> None:
        self._verdict = verdict or CategoryClassificationVerdict()

    def classify(self, draft, known_categories) -> CategoryClassificationVerdict:
        return self._verdict


class FakeQualityEvalSkill:
    def __init__(self, scores: list[RubricScore]) -> None:
        self._scores = scores

    def evaluate(self, draft, rubrics, raw_content) -> list[RubricScore]:
        return self._scores


class FakePrerequisiteJudgementSkill:
    """Canned per-target rubric scores. `assessments_by_target` maps a target
    concept id to the scores the skill "returned" for it; a candidate with no
    entry is omitted from the result, which is how the real skill signals
    "plainly not a prerequisite"."""

    def __init__(self, assessments_by_target: dict[str, list[RubricScore]] | None = None) -> None:
        self._by_target = assessments_by_target or {}
        self.calls: list[tuple[str, list[str]]] = []

    def judge(self, draft, candidates, rubrics) -> list[PrerequisiteAssessment]:
        self.calls.append(
            (draft.frontmatter.title or "", [str(c.concept_id) for c in candidates])
        )
        assessments = []
        for candidate in candidates:
            scores = self._by_target.get(str(candidate.concept_id))
            if scores is None:
                continue
            assessments.append(
                PrerequisiteAssessment(
                    target_id=ConceptId(str(candidate.concept_id)),
                    scores=scores,
                    # Same rollup the real adapter does, so a test asserting on
                    # the logged rationale isn't asserting on fake-only behaviour.
                    rationale="; ".join(s.rationale for s in scores if s.rationale),
                )
            )
        return assessments


class FakeRelatednessSkill:
    def __init__(self, verdict: RelatednessVerdict | None = None) -> None:
        self._verdict = verdict or RelatednessVerdict(related=[])

    def judge(self, draft, candidates) -> RelatednessVerdict:
        return self._verdict


class FakeQualityAuditSkill:
    def __init__(self, verdicts_by_id: dict[str, QualityAuditVerdict] | None = None) -> None:
        self._verdicts_by_id = verdicts_by_id or {}
        self._default = QualityAuditVerdict(standalone_quality=True)

    def judge(self, concept) -> QualityAuditVerdict:
        return self._verdicts_by_id.get(str(concept.id), self._default)


class FakeEvalRubricsRepository:
    def __init__(
        self,
        rubrics_by_domain: dict[str, list[Rubric]] | None = None,
        base_rubrics: list[Rubric] | None = None,
        named_rubrics: dict[str, list[Rubric]] | None = None,
    ) -> None:
        self._rubrics_by_domain = rubrics_by_domain or {}
        self._base_rubrics = base_rubrics or []
        self._named_rubrics = named_rubrics or {}

    def load_for_domain(self, domain_id: str | None) -> list[Rubric]:
        if domain_id is not None and domain_id in self._rubrics_by_domain:
            return self._rubrics_by_domain[domain_id]
        return self._base_rubrics

    def load_named(self, name: str) -> list[Rubric]:
        return self._named_rubrics.get(name, [])


class FakeEmbedding:
    """Distinguishable vectors per side, on purpose.

    A document and a query of the same text embed to *different* vectors here,
    so a call site that asks for the wrong one fails a test instead of quietly
    degrading retrieval — which is exactly how the missing prefixes went
    unnoticed under the old single-verb port."""

    def __init__(self) -> None:
        self.documents: list[str] = []
        self.queries: list[tuple[str, str | None]] = []

    def embed_document(self, text: str) -> list[float]:
        self.documents.append(text)
        return [float(len(text))]

    def embed_query(self, text: str, task: str | None = None) -> list[float]:
        self.queries.append((text, task))
        return [-float(len(text))]


class FakeVectorSearch:
    def __init__(self, candidates: list[CandidateMatch] | None = None) -> None:
        self.candidates = candidates or []
        self.upserted: dict[str, tuple[list[float], dict]] = {}

    def upsert(self, concept_id: str, vector: list[float], metadata: dict) -> None:
        self.upserted[concept_id] = (vector, metadata)

    def query(
        self, vector: list[float], k: int = 5, where: dict | None = None
    ) -> list[CandidateMatch]:
        return self.candidates[:k]

    def delete(self, concept_id: str) -> None:
        self.upserted.pop(concept_id, None)


class FakeMetadataRepository:
    def __init__(
        self,
        known_types: list[str] | None = None,
        domain_ids: list[str] | None = None,
        category_ids: list[str] | None = None,
        fts_candidates: list[CandidateMatch] | None = None,
        neighbors: dict[str, float] | None = None,
        structured_ids: list[str] | None = None,
        relations: list | None = None,
        lineage_paths: list[list] | None = None,
    ) -> None:
        self.known_types = known_types or []
        self.domain_ids = domain_ids or []
        self.category_ids = category_ids or []
        self.upserted: dict[str, Concept] = {}
        self._fts_candidates = fts_candidates or []
        self._neighbors = neighbors or {}
        self._structured_ids = structured_ids or []
        self._relations = relations or []
        self._lineage_paths = lineage_paths or []

    def upsert(self, concept: Concept) -> None:
        self.upserted[str(concept.id)] = concept

    def list_distinct_types(self, domain: str | None = None) -> list[str]:
        return self.known_types

    def find_ids_by_type(self, concept_type: str, domain: str | None = None) -> list[str]:
        """The explicit `domain_ids`/`category_ids` a test declared, *plus*
        anything upserted with that type — the real index knows every concept's
        type, so special-casing two of them would hide a caller that asks about
        any other (MOC, Source Document) behind a silent empty list."""
        declared = {
            "Domain": self.domain_ids,
            "Category": self.category_ids,
        }.get(concept_type, [])
        upserted = [
            concept_id
            for concept_id, concept in self.upserted.items()
            if concept.frontmatter.type == concept_type
        ]
        return list(dict.fromkeys([*declared, *upserted]))

    def find_links(self, concept_id: str) -> LinkGraph:
        return LinkGraph(concept_id=concept_id)

    def find_by_type_and_date(self, concept_type: str, since=None, until=None) -> list[str]:
        return self._structured_ids

    def find_relations(self, concept_id: str, relation_type: str | None = None) -> list:
        return self._relations

    def trace_lineage(
        self, concept_id: str, relation_type, direction: str, max_hops: int
    ) -> list[list]:
        return self._lineage_paths

    def search_fts(self, query: str, k: int) -> list[CandidateMatch]:
        return self._fts_candidates[:k]

    def expand_neighbors(
        self,
        seed_ids: list[str],
        max_hops: int,
        decay: float,
        category_decay: float,
    ) -> dict[str, float]:
        return {
            concept_id: score for concept_id, score in self._neighbors.items()
            if concept_id not in seed_ids
        }

    def delete(self, concept_id: str) -> None:
        self.upserted.pop(concept_id, None)


class FakeSchemaRegistry:
    def __init__(self, schemas: dict[str, dict] | None = None) -> None:
        self._schemas = schemas or {}

    def get_schema(self, concept_type: str) -> dict | None:
        return self._schemas.get(concept_type)


class FakeExecutor:
    def __init__(self, receipt: Receipt) -> None:
        self._receipt = receipt

    def run(self, computation: str, parameters: dict) -> Receipt:
        return self._receipt


class FakeAttester:
    def __init__(self, verdict: Verdict) -> None:
        self._verdict = verdict

    def verify(self, receipt: Receipt, contract: dict) -> Verdict:
        return self._verdict


class FakeDocumentParsing:
    def __init__(self, parsed_by_path: dict[str, ParsedDocument]) -> None:
        self._parsed_by_path = parsed_by_path

    def parse(self, path: str) -> ParsedDocument:
        return self._parsed_by_path[path]


class FakeImageCaptioning:
    def __init__(self, captions_by_anchor: dict[str, str] | None = None) -> None:
        self._captions_by_anchor = captions_by_anchor or {}

    def caption(self, image) -> str:
        return self._captions_by_anchor.get(image.anchor, "a captioned image")


class FakeRelevanceEvidence:
    """Canned evidence. Defaults to a bundle too small for the topicality floor
    and no nearest match, i.e. "accept" — so a test that isn't about relevance
    doesn't have to think about it."""

    def __init__(self, evidence: RelevanceEvidence | None = None) -> None:
        self._evidence = evidence or RelevanceEvidence(bundle_size=0)
        self.calls: list[str | None] = []

    def gather(self, draft, candidates, source_id=None) -> RelevanceEvidence:
        self.calls.append(source_id)
        return self._evidence
