"""Drives every unprocessed vault/raw/ item through the KnowledgeAgent, then applies
its create/merge decisions to the bundle and indexes whatever changed."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.raw_material_repository import (
    RawMaterialRepositoryPort,
)
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import CreateDecision, MergeDecision, RejectDecision
from pipeline.domain.concept import Concept, ConceptId


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


@dataclass(frozen=True)
class IngestOutcome:
    raw_id: str
    created: list[ConceptId]
    merged_into: list[ConceptId]
    rejected: list[str]


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

    def run(self) -> list[IngestOutcome]:
        outcomes: list[IngestOutcome] = []
        for raw in self._raw_material_repository.list_unprocessed():
            outcome = self._ingest_one(raw)
            outcomes.append(outcome)
            if outcome.rejected and not (outcome.created or outcome.merged_into):
                self._raw_material_repository.mark_rejected(
                    raw.id, "; ".join(outcome.rejected)
                )
            else:
                self._raw_material_repository.mark_processed(raw.id)
        return outcomes

    def _ingest_one(self, raw) -> IngestOutcome:
        agent_result = self._knowledge_agent.run(raw)

        created: list[ConceptId] = []
        merged_into: list[ConceptId] = []
        rejected: list[str] = []

        for decision in agent_result.decisions:
            if isinstance(decision, CreateDecision):
                concept = self._materialize(decision)
                self._concept_repository.save(concept)
                self._index_concept.run(concept)
                self._bundle_log.append(
                    f"**Creation**: Added [{concept.frontmatter.title or concept.id}]"
                    f"({concept.id}.md), drafted from raw/{raw.id}."
                )
                created.append(concept.id)
                self._raw_material_repository.link_concept(raw.id, str(concept.id))
            elif isinstance(decision, MergeDecision):
                existing = self._concept_repository.load(decision.into)
                merged = replace(
                    existing, body=f"{existing.body}\n\n{decision.addition}"
                )
                self._concept_repository.save(merged)
                self._index_concept.run(merged)
                self._bundle_log.append(
                    f"**Update**: Merged raw/{raw.id} into "
                    f"[{merged.frontmatter.title or merged.id}]({merged.id}.md)."
                )
                merged_into.append(decision.into)
                self._raw_material_repository.link_concept(raw.id, str(decision.into))
            elif isinstance(decision, RejectDecision):
                self._bundle_log.append(
                    f"**Rejected**: raw/{raw.id} failed eval — {decision.rationale}"
                )
                rejected.append(decision.rationale)

        return IngestOutcome(
            raw_id=raw.id, created=created, merged_into=merged_into, rejected=rejected
        )

    def _materialize(self, decision: CreateDecision) -> Concept:
        draft = decision.concept
        base = _slugify(draft.frontmatter.title or draft.source_raw_id)
        concept_id = ConceptId(base)
        suffix = 2
        while self._concept_repository.exists(concept_id):
            concept_id = ConceptId(f"{base}-{suffix}")
            suffix += 1
        return Concept(id=concept_id, frontmatter=draft.frontmatter, body=draft.body)
