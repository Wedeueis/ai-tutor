from __future__ import annotations

from typing import Protocol

from pipeline.domain.computation import Receipt


class ExecutorPort(Protocol):
    """(Stub, WIKI_SPEC.md §10.2) Runs a bound computation and returns a Receipt.
    No real adapter exists yet — see adapters/stubs/."""

    def run(self, computation: str, parameters: dict) -> Receipt: ...
