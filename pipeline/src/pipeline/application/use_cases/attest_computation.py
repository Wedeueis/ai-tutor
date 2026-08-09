"""(Stub orchestration, WIKI_SPEC.md §10.5) Executor -> Attester. Not wired to any
real computation yet — exists so the seam is in place once an Attested Computation
concept and real adapters show up."""

from __future__ import annotations

from pipeline.application.ports.attester import AttesterPort
from pipeline.application.ports.executor import ExecutorPort
from pipeline.domain.computation import Verdict


class AttestComputation:
    def __init__(self, executor: ExecutorPort, attester: AttesterPort) -> None:
        self._executor = executor
        self._attester = attester

    def run(self, computation: str, parameters: dict, contract: dict) -> Verdict:
        receipt = self._executor.run(computation, parameters)
        return self._attester.verify(receipt, contract)
