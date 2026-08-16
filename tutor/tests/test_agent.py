"""The ADK wiring.

Almost every test here is a wiring assertion, because that is all this module
is: the decisions were made in Phase 3 and Phase 4, and the way they get lost
is someone hardcoding a model string or dropping a `tool_filter`.

The one test that is not an assertion about wiring is the tool-calling probe at
the bottom. It is an integration test and it **samples** — a single passing run
proves nothing about a nondeterministic property (NFR3), and the single-sample
A/B in #12 that first suggested the failure mode turned out to be partly luck.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from tutor.agent import AGENT_NAME, UNBOUND_CONCEPT, build_agent
from tutor.application.harness import GENERIC_PEDAGOGY, VAULT_TOOLS
from tutor.application.invariants import INVARIANTS
from tutor.application.ports.outbound.vault import Concept
from tutor.config import DEFAULT_CHAT_MODEL, KNOWN_BAD_TOOL_CALLERS, Settings

TUTOR_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        ollama_host="http://localhost:11434",
        chat_model=DEFAULT_CHAT_MODEL,
        pipeline_mcp_url="http://127.0.0.1:8000/mcp",
        learner_db_path=tmp_path / "learner.db",
        session_db_url=f"sqlite:///{tmp_path / 'sessions.db'}",
    )


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


# --- the model is configuration, not a constant ---------------------------


def test_the_model_comes_from_settings(settings):
    agent = build_agent(settings=settings)

    assert agent.model.model == f"ollama_chat/{DEFAULT_CHAT_MODEL}"


def test_the_default_model_is_not_the_one_measured_to_fail(settings):
    """NFR2. `llama3.1:8b` is the default in both `agent/` and `pipeline`, and
    `tutor` must not inherit it — 0/6 real tool calls once the system prompt
    mentions tools (#12), and every teaching turn is a tool-calling path."""
    assert DEFAULT_CHAT_MODEL not in KNOWN_BAD_TOOL_CALLERS
    assert "llama3.1:8b" not in build_agent(settings=settings).model.model


def test_a_hosted_provider_needs_no_code_change(settings):
    """NFR1's whole obligation: #19's swap is a model string, not an edit.
    A name that already declares its provider passes straight through, and
    does not get pointed at localhost."""
    hosted = build_agent(
        settings=Settings(**{**vars(settings), "chat_model": "openrouter/deepseek/deepseek-chat"})
    )

    assert hosted.model.model == "openrouter/deepseek/deepseek-chat"
    assert hosted.model._additional_args.get("api_base") is None


def test_a_local_model_is_pointed_at_the_ollama_host(settings):
    agent = build_agent(settings=settings)

    assert agent.model._additional_args["api_base"] == settings.ollama_host


def test_a_known_bad_model_is_called_out_rather_than_silently_accepted(
    settings, caplog
):
    """The failure mode is a model *narrating* tool calls in prose, which reads
    like a bad session rather than a broken one. Configuring it stays the
    operator's call."""
    bad = Settings(**{**vars(settings), "chat_model": "llama3.1:8b"})

    with caplog.at_level(logging.WARNING):
        build_agent(settings=bad)

    assert "0/6" in caplog.text


# --- the instruction ------------------------------------------------------


def test_the_invariants_are_last_in_what_the_agent_is_given(settings):
    """RF2.3, checked at the point it actually reaches a model. The order is
    the enforcement: a pedagogy is a markdown file anyone can edit, and
    anything it could come after would be advisory."""
    instruction = build_agent(settings=settings).instruction(None)

    assert instruction.endswith(INVARIANTS)


def test_an_unbound_agent_gets_the_generic_pedagogy(settings):
    """The default path, not a fallback: most concepts carry no `domain:`
    (RF2.6), and neither does "no concept chosen yet"."""
    generic = (TUTOR_ROOT / "pedagogies" / GENERIC_PEDAGOGY / "SKILL.md").read_text()
    marker = "This is the **default path, not a fallback.**"
    assert marker in generic

    assert marker in build_agent(UNBOUND_CONCEPT, settings=settings).instruction(None)


def test_a_bound_domain_selects_its_pedagogy(settings):
    """Deterministic, by Domain, before the model is ever invoked (RF2.2)."""
    socratic = (TUTOR_ROOT / "pedagogies" / "socratic" / "SKILL.md").read_text()
    marker = "# Teaching by question"
    assert marker in socratic  # the binding below is only meaningful if it is real
    assert "domains/machine-learning" in socratic

    agent = build_agent(
        Concept(concept_id="c", domain="domains/machine-learning"), settings=settings
    )

    assert marker in agent.instruction(None)


def test_the_instruction_is_frozen_at_build_time(settings):
    """RF2.7: the volatile tier is composed once, at session start. A tutor
    that started treating a concept as mastered halfway through a conversation
    would be reacting to the learner's last answer rather than their record."""
    agent = build_agent(settings=settings)

    assert agent.instruction(None) == agent.instruction(None)


# --- tools ----------------------------------------------------------------


def test_the_toolset_points_at_the_configured_mcp_server(settings):
    toolset = build_agent(settings=settings).tools[0]

    assert toolset._connection_params.url == settings.pipeline_mcp_url


def test_the_pedagogys_predicate_is_what_filters_the_tools(settings):
    """RF2.5 applied at the only place tools enter the agent, so a pedagogy
    cannot acquire one by another route."""
    predicate = build_agent(settings=settings).tools[0].tool_filter

    assert callable(predicate)
    assert predicate(FakeTool("get_concept"), None)


def test_a_pedagogy_cannot_add_a_tool_the_shared_surface_lacks(settings):
    """`allowed-tools` narrows, never extends. Code execution and diagram tools
    are deliberately absent from `VAULT_TOOLS` — a capability decision must not
    be able to ride in on a pedagogy file."""
    predicate = build_agent(settings=settings).tools[0].tool_filter

    assert not predicate(FakeTool("execute_code"), None)
    assert not predicate(FakeTool("write_concept"), None)
    for name in ("execute_code", "write_concept"):
        assert name not in VAULT_TOOLS


def test_the_agent_has_exactly_one_toolset(settings):
    """Every tool the tutor can reach comes from `pipeline`'s read-only MCP
    surface. A second toolset would be a second, unfiltered door."""
    assert len(build_agent(settings=settings).tools) == 1


def test_the_agent_is_named_for_the_deployable(settings):
    assert build_agent(settings=settings).name == AGENT_NAME


# --- sessions -------------------------------------------------------------


def test_sessions_do_not_live_in_learner_db(settings):
    """§7: ADK's session schema will churn; the review history is the one thing
    here that cannot be regenerated, so the two are separate files."""
    assert str(settings.learner_db_path) not in settings.session_db_url


# --- the sampled probe ----------------------------------------------------

SAMPLES = int(os.environ.get("TUTOR_PROBE_SAMPLES", "6"))
REQUIRED_RATE = float(os.environ.get("TUTOR_PROBE_RATE", "0.8"))


@pytest.mark.integration
@pytest.mark.anyio
async def test_the_configured_model_actually_calls_tools():
    """NFR3: tool calling is a per-model property, verified by **sampling**.

    Needs Ollama and `pipeline`'s MCP server running. It asks a question that
    cannot be answered without reading the vault, and counts how many of the
    runs produce a real function call rather than prose describing one — the
    exact failure #12 measured, which does not raise and does not look like an
    error in the transcript.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from tutor.agent import build_agent

    settings = Settings.from_env()
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="tutor-probe",
        agent=build_agent(settings=settings),
        session_service=session_service,
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text="Search the vault for 'attention' and tell me what you find.")],
    )

    called = 0
    for sample in range(SAMPLES):
        session = await session_service.create_session(
            app_name="tutor-probe", user_id="probe", session_id=f"probe-{sample}"
        )
        async for event in runner.run_async(
            user_id="probe", session_id=session.id, new_message=message
        ):
            if event.get_function_calls():
                called += 1
                break

    rate = called / SAMPLES
    assert rate >= REQUIRED_RATE, (
        f"{settings.chat_model} made a real tool call in {called}/{SAMPLES} runs "
        f"({rate:.0%} < {REQUIRED_RATE:.0%}). A model that narrates tool calls "
        f"instead of making them cannot teach from the vault (#12)."
    )
