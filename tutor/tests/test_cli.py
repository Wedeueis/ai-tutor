"""The CLI — the thing that makes depth targets usable.

RF3.3 is explicit that a target the learner cannot set is not a feature. These
tests drive the real commands against a real `learner.db` under `tmp_path`; the
vault is faked, because `plan` and `session` would otherwise need `pipeline`'s
MCP server running.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from tutor.application.ports.outbound.vault import Concept, ConceptMatch, Edge
from tutor.cli import main as cli
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import ALGORITHM, PARAMETERS_ID, Rating

runner = CliRunner()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """`learner.db` in a temp directory. Set for every test here, so no command
    can reach the developer's real review history."""
    monkeypatch.setenv("TUTOR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LEARNER_DB_PATH", raising=False)
    return tmp_path


class FakeVault:
    def __init__(self, edges: list[Edge] | None = None) -> None:
        self.edges = edges or []
        self.closed = False

    async def get_concept(self, concept_id: str) -> Concept:
        return Concept(concept_id=concept_id)

    async def search(self, query: str, k: int = 5) -> list[ConceptMatch]:
        return []

    async def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]:
        return self.edges

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def vault(monkeypatch):
    fake = FakeVault()
    monkeypatch.setattr(cli.Container, "vault", lambda self: fake)
    return fake


def _invoke(*args: str):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


# --- depth targets --------------------------------------------------------


def test_setting_a_target_reports_what_it_asks_for():
    """A level name alone is not usable: "specialist" has to say what it will
    hold the learner to, or the number stays the tool's private business."""
    output = _invoke("depth", "set", "categories/graph-rag", "specialist")

    assert "categories/graph-rag: specialist" in output
    assert "180 days" in output
    assert "free-text" in output


def test_a_target_survives_the_process_that_set_it():
    _invoke("depth", "set", "categories/graph-rag", "working")

    assert "categories/graph-rag: working" in _invoke("depth", "show")


def test_setting_a_target_again_replaces_it():
    _invoke("depth", "set", "categories/x", "specialist")
    _invoke("depth", "set", "categories/x", "aware")

    output = _invoke("depth", "show")

    assert "categories/x: aware" in output
    assert "specialist" not in output


def test_showing_a_target_says_whether_it_was_ever_declared():
    """`aware` is both a real choice and what an untouched Category answers,
    and a learner has to be able to tell them apart (#20)."""
    _invoke("depth", "set", "categories/chosen", "aware")

    assert "(declared)" in _invoke("depth", "show", "categories/chosen")
    assert "(default, never set)" in _invoke("depth", "show", "categories/untouched")


def test_an_untouched_category_answers_aware_rather_than_failing():
    output = _invoke("depth", "show", "categories/never-heard-of-it")

    assert "aware" in output


def test_no_targets_at_all_says_so_rather_than_printing_nothing():
    assert "defaults to `aware`" in _invoke("depth", "show")


def test_an_unknown_level_is_rejected():
    result = runner.invoke(cli.app, ["depth", "set", "categories/x", "expert"])

    assert result.exit_code != 0


def test_a_target_may_be_set_for_a_category_the_vault_does_not_have_yet():
    """Deliberately unvalidated: ingest produces Categories over time, and a
    target for one that has not arrived is inert, not an error."""
    _invoke("depth", "set", "categories/not-ingested-yet", "working")

    assert "categories/not-ingested-yet: working" in _invoke("depth", "show")


# --- the plan and the session ---------------------------------------------


def test_plan_prints_prerequisites_before_what_depends_on_them(vault):
    vault.edges = [Edge("attention", "softmax", "requires")]

    lines = _invoke("plan", "attention").strip().splitlines()

    assert lines[0].startswith("softmax")
    assert "blocked by softmax" in lines[1]


def test_plan_closes_the_vault_connection(vault):
    _invoke("plan", "anything")

    assert vault.closed


def test_session_marks_overdue_work(vault, tmp_path):
    _review(tmp_path, "softmax", at=datetime.now(UTC) - timedelta(days=30))

    output = _invoke("session", "softmax")

    assert "overdue" in output


def test_nothing_to_study_is_said_plainly_rather_than_printed_as_emptiness(
    vault, tmp_path
):
    for _ in range(3):
        _review(tmp_path, "softmax", at=datetime.now(UTC), rating=Rating.EASY)

    assert "Nothing to study" in _invoke("plan", "softmax")


def _review(
    data_dir, concept_id: str, at: datetime, rating: Rating = Rating.AGAIN
) -> None:
    """Writes straight to the same `learner.db` the commands read."""
    from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
    from tutor.domain.scheduling import calculate_next_review

    store = SqliteLearnerStore(
        data_dir / "learner.db", calculate_next_review, ALGORITHM, PARAMETERS_ID
    )
    try:
        state = store.scheduler_state(concept_id)
        store.append_review(
            ReviewEvent(
                concept_id=concept_id,
                rating=rating,
                reviewed_at=state.due if state and state.due else at,
                algorithm=ALGORITHM,
                parameters=PARAMETERS_ID,
                question="q",
                rubric="r",
                answer="a",
                grade="g",
            )
        )
    finally:
        store.close()
