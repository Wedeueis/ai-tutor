"""Removes every concept from the bundle, keeping the three stores that
describe it (markdown files, metadata rows, vectors) consistent — the bulk
counterpart to deleting one concept at a time.

Deliberately *not* touched, ever: `vault/raw/` — the capture inbox is the
input, not derived state, so even a full reset keeps it (that's the material
you'd re-ingest from) — and reserved `index.md` files, which are never
concepts (`ConceptRepositoryPort.list()` skips them).

Two further layers are opt-in, because each is a real loss of history rather
than derived state that can be rebuilt from the vault:

- `reset_intake` — without it the tracker still says every raw file was
  already ingested, so a following `ingest` finds nothing to do and the bundle
  stays empty. With it, the raw material becomes re-ingestable from scratch,
  at the cost of forgetting which files errored or were rejected.
- `reset_log` — drops the pipeline's audit trail (including the delete entries
  this very run would otherwise leave behind), for when the goal is a bundle
  with no history at all rather than a bundle whose history records that it
  was emptied."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.intake_repository import IntakeRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.application.use_cases.ensure_index_fingerprint import (
    EnsureIndexFingerprint,
)
from pipeline.domain.intake import IntakeState


@dataclass(frozen=True)
class ClearReport:
    """What a clear removed — or, from `plan()`, what one would remove."""

    concept_ids: list[str]
    intake_ids: list[str]
    log_entries: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.concept_ids and not self.intake_ids and not self.log_entries


class ClearBundle:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        metadata_repository: MetadataRepositoryPort,
        vector_search: VectorSearchPort,
        intake_repository: IntakeRepositoryPort,
        bundle_log: BundleLogPort,
        fingerprint: EnsureIndexFingerprint | None = None,
    ) -> None:
        self._concept_repository = concept_repository
        self._metadata_repository = metadata_repository
        self._vector_search = vector_search
        self._intake_repository = intake_repository
        self._bundle_log = bundle_log
        self._fingerprint = fingerprint

    def plan(self, reset_intake: bool = False, reset_log: bool = False) -> ClearReport:
        """What `run()` with the same flags would remove, changing nothing —
        the whole point of a destructive bulk command having a dry run."""
        return ClearReport(
            concept_ids=[str(concept_id) for concept_id in self._concept_repository.list()],
            intake_ids=self._intake_ids() if reset_intake else [],
            log_entries=len(self._bundle_log.list_entries()) if reset_log else 0,
        )

    def run(self, reset_intake: bool = False, reset_log: bool = False) -> ClearReport:
        report = self.plan(reset_intake, reset_log)

        for concept_id in self._concept_repository.list():
            concept = self._concept_repository.load(concept_id)
            self._concept_repository.delete(concept_id)
            self._metadata_repository.delete(str(concept_id))
            self._vector_search.delete(str(concept_id))
            self._bundle_log.append(
                action="delete",
                concept_id=str(concept_id),
                raw_id=None,
                message=f"Cleared bundle — removed {concept.frontmatter.title or concept_id}.",
            )

        if report.concept_ids and self._fingerprint is not None:
            # Every vector just went away, so the record of what produced them
            # must too — otherwise the next index run is checked against a
            # fingerprint describing an index that no longer exists, and a
            # deliberate model change still looks like corruption.
            self._fingerprint.forget()

        for item_id in report.intake_ids:
            self._intake_repository.delete(item_id)

        if reset_log:
            # Last, so the delete entries appended just above go with it — the
            # end state is an empty trail, not one that opens by narrating its
            # own truncation.
            dropped = self._bundle_log.clear()
            return ClearReport(
                concept_ids=report.concept_ids,
                intake_ids=report.intake_ids,
                log_entries=dropped,
            )

        return report

    def _intake_ids(self) -> list[str]:
        """Every tracked item, in whatever state. The port exposes listing only
        per-state, so this is the union — deduped, because an implementation is
        free to return the same row under more than one query."""
        ids: dict[str, None] = {}
        for state in IntakeState:
            for item in self._intake_repository.list_by_state(state):
                ids[item.id] = None
        return list(ids)
