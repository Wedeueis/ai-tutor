"""Throwaway spike for issue #12: does ADK's SkillToolset work with LiteLlm +
a local Ollama model?

Two pedagogy skills whose outputs are trivially distinguishable (each is
required to emit a marker). We ask three questions -- one clearly humanities,
one clearly software, one ambiguous -- and check whether the model discovers
the right skill, loads it, and then actually follows its instructions.

Not a test. Not to be merged. Run: uv run python run.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.adk.skills import list_skills_in_dir, load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
SKILLS_DIR = Path(__file__).parent / "skills"

PROMPTS = [
    ("humanities", "Teach me about Kant's categorical imperative."),
    ("software", "Teach me how a binary search works."),
    ("ambiguous", "Teach me about the ethics of writing software that ranks people."),
]


def build_agent() -> LlmAgent:
    # list_skills_in_dir returns {skill_id: Frontmatter}; SkillToolset wants
    # fully loaded Skill objects, so load each discovered directory.
    discovered = list_skills_in_dir(SKILLS_DIR)
    skills = [load_skill_from_dir(SKILLS_DIR / skill_id) for skill_id in discovered]
    print(f"discovered skills: {list(discovered)}\n")
    return LlmAgent(
        name="pedagogy_spike",
        model=LiteLlm(model=f"ollama_chat/{MODEL}", api_base=HOST),
        # Neutral persona only: naming tools in the system prompt was shown to
        # suppress native tool calling for llama3.1:8b (see run notes). This
        # leaves SkillToolset's own injected instruction as the only mention.
        instruction="You are a helpful tutor. Teach clearly.",
        tools=[SkillToolset(skills=skills)],
    )


async def ask(runner: InMemoryRunner, user_id: str, label: str, prompt: str) -> None:
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id
    )
    print(f"--- {label}: {prompt}")
    tool_calls: list[str] = []
    final = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for call in event.get_function_calls() or []:
            tool_calls.append(f"{call.name}({call.args})")
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts)

    print(f"    tool calls: {tool_calls or 'NONE'}")
    marker = next((m for m in ("[SOCRATIC]", "[CODE-DRILL]") if m in final), "NONE")
    print(f"    marker in reply: {marker}")
    print(f"    reply: {final.strip()[:300]}\n")


async def main() -> None:
    runner = InMemoryRunner(agent=build_agent(), app_name="pedagogy_spike")
    for label, prompt in PROMPTS:
        try:
            await ask(runner, "spike-user", label, prompt)
        except Exception as exc:  # noqa: BLE001 - spike: report and continue
            print(f"    FAILED: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
