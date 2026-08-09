"""ExecutorPort stub (WIKI_SPEC.md §10.2). No Attested Computation concept exists
in the vault yet, so there is nothing real to run. Swap for a real adapter (e.g. a
BigQuery/dbt/python runner) once one does."""

from __future__ import annotations

from pipeline.domain.computation import Receipt


class NotImplementedExecutor:
    def run(self, computation: str, parameters: dict) -> Receipt:
        raise NotImplementedError(
            "no Executor adapter is wired up yet — see WIKI_SPEC.md §10.2 and "
            "adapters/stubs/not_implemented_executor.py"
        )
