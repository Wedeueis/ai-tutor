from __future__ import annotations

from typing import Protocol

from pipeline.domain.computation import Receipt, Verdict


class AttesterPort(Protocol):
    """(Stub, WIKI_SPEC.md §10.2) Deterministic, no-LLM check of a Receipt against
    the sanctioned computation's contract. No real adapter exists yet — see
    adapters/stubs/. Distinct from the structural `validate_concept` use case:
    this attests a *run*, not a document's shape."""

    def verify(self, receipt: Receipt, contract: dict) -> Verdict: ...
