"""`TeachingTurnPort` over an ADK agent and a console.

The only place ADK and the learner's terminal meet. Everything about *when* the
event is written lives in `application/teaching.py`; this decides only how a
question reaches a person and how their reply comes back.

**The agent is rebuilt per visit**, inside one ADK session. The instruction
changes — different concept, different history, possibly a different pedagogy
if the Domain differs — while the conversation carries on, so the learner sees
one continuous session and the model sees the right context for the concept in
front of it. That is also what freezes the volatile tier at the right moment
(RF2.7): once per visit, before the turn, never mid-answer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from google.adk.runners import Runner
from google.genai import types

from tutor.agent import build_agent
from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.teaching_turn import Answer
from tutor.application.ports.outbound.vault import Concept
from tutor.config import Settings
from tutor.domain.learner_context import LearnerContext
from tutor.domain.review import ReviewEvent

logger = logging.getLogger(__name__)

APP_NAME = "tutor"
SKIP_COMMAND = "/skip"
QUIT_COMMANDS = frozenset({"/quit", "/exit", "/stop"})
"""Structural, not inferred (#39). A skip is a command the interface reads
directly; anything else the learner types is an attempt and gets graded — "I
don't know" included."""

_POSE = """Ask the learner this question, in your own voice and in keeping with
your pedagogy. Set it up in a sentence or two if that helps, then ask it.

{question}

Ask it and stop. Do not answer it, do not hint at the answer, and do not give
them anything to recognise — what they say next is graded as unassisted recall,
and help offered now would be scored as if they had remembered it.
"""

_TEACH = """They answered:

{answer}

That answer has already been graded and recorded — {outcome}. Nothing you say
now changes their schedule, so teach freely: correct what was wrong, fill what
was missing, and answer what they ask. Keep it short, and work from the
concept's own material.
"""

_UNGRADED = "the grading failed, so nothing was recorded this time"


class AdkTeachingTurn:
    """Holds one ADK session open across the whole tutoring session."""

    def __init__(
        self,
        session_service: object,
        session_id: str,
        user_id: str = "learner",
        settings: Settings | None = None,
        read: Callable[[str], str] | None = None,
        write: Callable[[str], None] | None = None,
    ) -> None:
        self._session_service = session_service
        self._session_id = session_id
        self._user_id = user_id
        self._settings = settings or Settings.from_env()
        self._read = read or input
        self._write = write or print

    async def pose(
        self, assessment: Assessment, concept: Concept, context: LearnerContext
    ) -> Answer:
        """Put the question, then take the learner's **first** reply.

        One `_say` and one read, with nothing between them. The contract in the
        port is that no help reaches the learner before this returns, and the
        way to keep it is to have nowhere for help to happen."""
        await self._say(
            concept, context, _POSE.format(question=assessment.question)
        )
        return self._listen()

    async def teach(
        self, assessment: Assessment, answer: Answer, event: ReviewEvent | None
    ) -> None:
        """Everything after the grade. Unbounded turns, none of which are read
        by anything that writes."""
        outcome = (
            _UNGRADED
            if event is None
            else f"they were graded {event.rating.name.lower()}"
        )
        concept = Concept(concept_id=assessment.concept_id)
        await self._say(
            concept, None, _TEACH.format(answer=answer.text, outcome=outcome)
        )

        while True:
            reply = self._read("> ").strip()
            if not reply or reply.lower() in QUIT_COMMANDS or reply == SKIP_COMMAND:
                return
            await self._say(concept, None, reply)

    def _listen(self) -> Answer:
        raw = self._read("> ")
        stripped = raw.strip()
        if stripped == SKIP_COMMAND:
            return Answer(skipped=True)
        if stripped.lower() in QUIT_COMMANDS:
            return Answer(abandoned=True)
        return Answer(text=raw)

    async def _say(
        self, concept: Concept, context: LearnerContext | None, message: str
    ) -> None:
        """One turn through the agent, printed as it streams.

        The agent is rebuilt here rather than held, so the instruction tracks
        the concept while the ADK session — and therefore the conversation —
        carries on unchanged."""
        runner = Runner(
            app_name=APP_NAME,
            agent=build_agent(concept, context, settings=self._settings),
            session_service=self._session_service,  # type: ignore[arg-type]
        )
        content = types.Content(role="user", parts=[types.Part(text=message)])
        async for event in runner.run_async(
            user_id=self._user_id,
            session_id=self._session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(part.text or "" for part in event.content.parts)
                if text.strip():
                    self._write(text.strip())
