"""Control for the skills spike: same model, same LiteLlm wiring, but a single
plain FunctionTool instead of SkillToolset.

Isolates the question. If this one emits a real function call and the skills
run does not, the failure is specific to the skills flow (many tools + long
system instruction), not to tool calling with llama3.1:8b in general.
"""

from __future__ import annotations

import asyncio
import os
import sys

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def load_pedagogy(subject_area: str) -> dict:
    """Loads the teaching style to use for a subject area.

    Args:
        subject_area: The subject area, e.g. "philosophy" or "programming".
    """
    style = "socratic" if subject_area in ("philosophy", "humanities") else "code-drill"
    return {"style": style, "marker": f"[{style.upper()}]"}


async def main() -> None:
    agent = LlmAgent(
        name="control_spike",
        model=LiteLlm(model=f"ollama_chat/{MODEL}", api_base=HOST),
        instruction=(
            "You are a tutor. Before answering, you MUST call load_pedagogy with"
            " the subject area, then begin your reply with the marker it returns."
        ),
        tools=[load_pedagogy],
    )
    runner = InMemoryRunner(agent=agent, app_name="control_spike")
    session = await runner.session_service.create_session(
        app_name="control_spike", user_id="spike-user"
    )

    prompt = "Teach me about Kant's categorical imperative."
    print(f"--- control: {prompt}")
    tool_calls: list[str] = []
    final = ""
    async for event in runner.run_async(
        user_id="spike-user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for call in event.get_function_calls() or []:
            tool_calls.append(f"{call.name}({call.args})")
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts)

    print(f"    tool calls: {tool_calls or 'NONE'}")
    print(f"    reply: {final.strip()[:300]}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
