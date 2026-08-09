"""AttesterPort stub (WIKI_SPEC.md §10.2). Swap for a real, deterministic (no-LLM)
adapter once a real computation + receipt shape exist to verify."""

from __future__ import annotations

from pipeline.domain.computation import Receipt, Verdict


class NotImplementedAttester:
    def verify(self, receipt: Receipt, contract: dict) -> Verdict:
        raise NotImplementedError(
            "no Attester adapter is wired up yet — see WIKI_SPEC.md §10.2 and "
            "adapters/stubs/not_implemented_attester.py"
        )
