"""The ONLY way `tutor` reaches the vault: MCP-backed and read-only.

`tutor` never writes the OKF bundle (PRD v3 §2.1, decided in #8). It may write
to the inbox (`vault/raw/`), which is explicitly not part of the bundle, but
that is a filesystem concern and does not belong on this port.

Nothing here is modelled as local state. `Concept`, `Domain`, `Category` and
`requires::` edges are read through this port every time they are needed —
duplicating them into `learner.db` would make the vault's copy and ours drift,
and the vault is authoritative for all of it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Concept:
    """A vault concept, as `tutor` needs to see it. A read-through view, not a
    stored entity — deliberately missing the provenance and lifecycle fields
    `pipeline` owns, because nothing in teaching reads them."""

    concept_id: str
    title: str | None = None
    description: str | None = None
    body: str = ""
    domain: str | None = None
    """Selects the pedagogy, deterministically and before the model is ever
    invoked. `tutor` never classifies — `pipeline` owns classification
    (decided in #5). Most concepts have none, which is why the generic
    pedagogy is the default path rather than a fallback (RF2.6)."""
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConceptMatch:
    concept_id: str
    score: float


@dataclass(frozen=True)
class Edge:
    """One typed relation from the vault's link graph."""

    from_id: str
    to_id: str
    relation_type: str


class VaultPort(Protocol):
    def get_concept(self, concept_id: str) -> Concept: ...

    def search(self, query: str, k: int = 5) -> list[ConceptMatch]: ...

    def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        """Walks `requires::` edges via the existing `trace_lineage` MCP tool —
        no new tool needed (RF3.1).

        Reads the `requires::` tier **only**. `may_require::` is recorded by
        `pipeline` for human review and is inert by design: nothing here may
        start reading it without that being a deliberate decision.

        `max_hops` bounds the walk. The emitter avoids introducing cycles, but
        consumers must tolerate them regardless — a backfilled or
        hand-edited graph can still contain one."""
        ...
