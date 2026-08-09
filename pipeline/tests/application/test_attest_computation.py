from pipeline.application.use_cases.attest_computation import AttestComputation
from pipeline.domain.computation import Receipt, Verdict
from tests.application.fakes import FakeAttester, FakeExecutor


def test_attest_computation_runs_executor_then_attester():
    receipt = Receipt(fields={"job_id": "123"})
    verdict = Verdict(passed=True, details="matched")
    use_case = AttestComputation(FakeExecutor(receipt), FakeAttester(verdict))

    result = use_case.run("SELECT 1", {"year": 2026}, contract={})

    assert result is verdict
