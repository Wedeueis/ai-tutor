"""The ADK agent, assembled from the pieces the earlier phases built.

Nothing is decided here. The instruction comes from
`HermesDomainOrchestrator.for_concept` (soul, then pedagogy, then invariants —
in that order, always); the tools are `pipeline`'s read-only MCP surface,
narrowed by the same call's predicate; the model is whatever `Settings` names.
This module's only job is to hold them together, which is why it is short and
why almost everything in it is a wiring assertion in the tests.

**Composed once, per concept** (RF2.7). `build_agent` runs at the start of a
session and the instruction is a closure over a string that was already
composed — so mastery that changes during the session surfaces in the *next*
one, never mid-dialogue. That is a pedagogical choice, not an optimisation:
a tutor that started treating a concept as mastered halfway through a
conversation would be reacting to the learner's last answer rather than to
their record.

**Still not `SkillToolset`** (RF2.1, #12). The `SKILL.md` parser is reused; the
runtime discovery is not. The toolset injects its own long tool-describing
system instruction that cannot be removed — precisely the trigger measured to
take `llama3.1:8b` from 5/6 real tool calls to 0/6 — and discovery solves a
problem `tutor` does not have, since the pedagogy set is known at startup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

from tutor.application.harness import HermesDomainOrchestrator
from tutor.application.ports.outbound.vault import Concept
from tutor.config import Settings

logger = logging.getLogger(__name__)

AGENT_NAME = "tutor"

_TUTOR_ROOT = Path(__file__).resolve().parents[2]
PEDAGOGIES_DIR = _TUTOR_ROOT / "pedagogies"
SOUL_PATH = _TUTOR_ROOT / "SOUL.md"

UNBOUND_CONCEPT = Concept(concept_id="")
"""The concept an agent is built for when no goal has been chosen yet.

It has no `domain:`, so it selects the generic pedagogy — which is the right
answer rather than a placeholder: the generic pedagogy is the default path and
the one that runs most often (RF2.6). This is what `adk web` and `adk run` get
when they import `root_agent` without a session having picked a concept."""


def default_orchestrator() -> HermesDomainOrchestrator:
    """Loads the pedagogies from disk, once."""
    return HermesDomainOrchestrator(PEDAGOGIES_DIR, SOUL_PATH)


def build_agent(
    concept: Concept = UNBOUND_CONCEPT,
    *,
    orchestrator: HermesDomainOrchestrator | None = None,
    settings: Settings | None = None,
) -> LlmAgent:
    """The agent for one concept: its pedagogy's instruction, its tools."""
    settings = settings or Settings.from_env()
    orchestrator = orchestrator or default_orchestrator()
    instruction, tool_predicate = orchestrator.for_concept(concept)

    if settings.model_is_known_bad_at_tool_calling:
        # Loud rather than fatal: configuring it is the operator's call, but
        # the failure mode is a model *narrating* tool calls in prose, which
        # reads like a bad session rather than a broken one (NFR2, #12).
        logger.warning(
            "%s is measured at 0/6 real tool calls once the system prompt "
            "mentions tools (#12), and every teaching turn is a tool-calling "
            "path — expect it to describe calling tools instead of calling them",
            settings.chat_model,
        )

    return LlmAgent(
        name=AGENT_NAME,
        model=LiteLlm(model=settings.litellm_model, api_base=settings.model_api_base),
        instruction=instruction,
        tools=[
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=settings.pipeline_mcp_url
                ),
                # `allowed-tools` narrows and can never extend (RF2.5). The
                # predicate is applied here, at the only place tools enter the
                # agent, so a pedagogy cannot acquire one by any other route.
                tool_filter=tool_predicate,
            )
        ],
    )


def build_session_service(settings: Settings | None = None):
    """ADK's own session store — **a different SQLite file from `learner.db`**
    (§7). ADK's session schema will churn; the review history is the one thing
    here that cannot be regenerated, so the two do not share a file."""
    from google.adk.sessions import DatabaseSessionService

    settings = settings or Settings.from_env()
    settings.learner_db_path.parent.mkdir(parents=True, exist_ok=True)
    return DatabaseSessionService(db_url=settings.session_db_url)


root_agent = build_agent()
"""What `adk web` / `adk run` import. Bound to no concept, so: generic
pedagogy, full read-only surface."""
