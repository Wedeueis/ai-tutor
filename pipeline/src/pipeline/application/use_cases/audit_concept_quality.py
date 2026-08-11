"""Walks every content concept in the vault and flags ones that don't stand
alone as genuinely useful — either obviously (a garbled-table fragment,
caught for free via domain/text_quality.py before ever calling the LLM) or
via QualityAuditSkillPort's judgment. Purely a report: nothing is deleted
here, see `pipeline delete` for the actual cleanup action."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.skills.quality_audit import QualityAuditSkillPort
from pipeline.domain.concept import NON_CONTENT_TYPES, ConceptId
from pipeline.domain.text_quality import looks_like_garbled_table


@dataclass(frozen=True)
class QualityFlag:
    concept_id: ConceptId
    reason: str


class AuditConceptQuality:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        quality_audit: QualityAuditSkillPort,
    ) -> None:
        self._concept_repository = concept_repository
        self._quality_audit = quality_audit

    def run(self) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        for concept_id in self._concept_repository.list():
            concept = self._concept_repository.load(concept_id)
            if concept.frontmatter.type in NON_CONTENT_TYPES:
                continue  # structural/navigation, not knowledge to judge

            if looks_like_garbled_table(concept.body):
                flags.append(QualityFlag(concept_id, "looks like a garbled table"))
                continue

            verdict = self._quality_audit.judge(concept)
            if not verdict.standalone_quality:
                flags.append(QualityFlag(concept_id, verdict.reason))
        return flags
