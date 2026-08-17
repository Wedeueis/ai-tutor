"""PRD v3 §2's component rules, made checkable rather than only documented.

These are the constraints most likely to be broken by a well-meaning later
change — an import added for convenience, a default copied from `agent/` — and
each would be silent without a test."""

import re
from pathlib import Path

import pytest

_TUTOR_ROOT = Path(__file__).resolve().parents[1]
_IMPORT_PIPELINE = re.compile(r"^\s*(from|import)\s+pipeline\b", re.MULTILINE)


_REQUIREMENT = re.compile(r'"([^"]+)"')


def _python_files():
    for directory in ("src", "tests"):
        yield from (_TUTOR_ROOT / directory).rglob("*.py")


def _pyproject() -> str:
    return (_TUTOR_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _runtime_dependencies() -> str:
    return _pyproject().split("dependencies = [", 1)[1].split("]", 1)[0]


def _dev_dependencies() -> str:
    return _pyproject().split("[dependency-groups]", 1)[1].split("dev = [", 1)[1].split("]", 1)[0]


def _requirement_names(block: str) -> set[str]:
    """Only the quoted requirement strings — the surrounding comments explain
    *why* each pin is what it is and routinely name other components, so a
    substring search over the raw block reports them as dependencies."""
    return {
        re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].strip().lower()
        for requirement in _REQUIREMENT.findall(block)
    }


def test_nothing_in_tutor_imports_pipeline():
    """Rule 1: `tutor` reaches `pipeline` solely over its MCP server. No Python
    import, no shared virtualenv, no shared SQLite file."""
    offenders = [
        str(path.relative_to(_TUTOR_ROOT))
        for path in _python_files()
        if _IMPORT_PIPELINE.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_pipeline_is_not_a_declared_dependency():
    """The import check above only sees code that exists today; this catches a
    dependency added in anticipation of one."""
    assert "pipeline" not in _requirement_names(_runtime_dependencies())


def test_fsrs_is_a_test_only_dependency():
    """RF4.2: FSRS's formulas are empirical, so `fsrs` (the PyPI name for what
    the PRD calls py-fsrs) is the differential oracle our own implementation is
    tested against — never something the runtime calls. A runtime dependency
    would let the oracle and the subject become the same code."""
    assert "fsrs" not in _requirement_names(_runtime_dependencies())
    assert "fsrs" in _requirement_names(_dev_dependencies())


def test_the_default_chat_model_is_not_llama31_8b():
    """NFR2. Measured at 0/6 real tool calls once the system prompt mentions
    tools (#12), and every teaching turn is a tool-calling path. It is still
    the default in `agent/` and `pipeline`; `tutor` must not inherit it."""
    from tutor.config import DEFAULT_CHAT_MODEL

    assert DEFAULT_CHAT_MODEL != "llama3.1:8b"


def test_the_learner_db_and_the_session_db_are_separate_files():
    """PRD v3 §7: ADK is pre-1.0 and its session schema will churn, while the
    review history is the one thing here that cannot be regenerated."""
    from tutor.config import Settings

    settings = Settings.from_env()

    assert str(settings.learner_db_path) not in settings.session_db_url


@pytest.mark.parametrize(
    "signature",
    [
        "append_review",
        "scheduler_state",
        "replay",
        "depth_target",
        "set_depth_target",
    ],
)
def test_no_port_method_takes_a_user_id(signature):
    """There is exactly one learner, so there is no `user_id` anywhere — the
    speculative multi-learner threading was cut deliberately (PRD v3 §1.3)."""
    import inspect

    from tutor.application.ports.outbound.learner_store import LearnerStorePort

    parameters = inspect.signature(getattr(LearnerStorePort, signature)).parameters

    assert "user_id" not in parameters


def test_nothing_leaving_tutor_can_describe_the_learner():
    """The semantic/episodic boundary, checked at every seam that crosses it
    (§2.1, NFR5).

    `ContributionPort` is the only way out, and `DiscoveryKind` is the only
    vocabulary that feeds it. Both are closed sets, and the enforcement is that
    neither has a member for a blindspot — a filter that inspects content and
    decides can be wrong, while a name that does not exist cannot be used.
    """
    import inspect

    from tutor.application.ports.outbound.contributions import ContributionPort
    from tutor.application.ports.outbound.discovery import DiscoveryKind

    verbs = {
        name
        for name, _ in inspect.getmembers(ContributionPort, inspect.isfunction)
        if not name.startswith("_")
    }
    kinds = {kind.value for kind in DiscoveryKind}

    assert verbs == {"record_inquiry", "propose_concept"}
    assert kinds == {"coverage_gap", "contradiction", "derived_concept"}
    assert not any("learner" in name or "blindspot" in name for name in verbs | kinds)
