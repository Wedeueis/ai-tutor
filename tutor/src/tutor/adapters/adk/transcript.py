"""`TranscriptPort` over ADK's session store.

The **only** place in `tutor` that reads ADK's session database back, and it is
deliberately the only one: that store is disposable (#39). `review_events` is
authoritative and self-sufficient, ADK's schema will churn, and anything else
that started depending on this would couple the irreplaceable thing to the
replaceable one.

Because it is disposable, this is also allowed to fail quietly-ish: it returns
what it can read, and the pass above it treats an empty transcript as nothing
to report rather than as an error.
"""

from __future__ import annotations

import logging

from tutor.adapters.adk.turn import APP_NAME, DEFAULT_USER_ID

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 24_000
"""A long session against a small local context window would otherwise push the
concepts out of the prompt entirely. Truncation keeps the **end** — the later
exchanges are where a contradiction has usually surfaced, and where the tutor
has already said the vault is thin on something."""


class AdkTranscript:
    def __init__(
        self,
        session_service: object,
        # Taken from the turn adapter rather than restated: these two address
        # the session `AdkTeachingTurn` wrote. A divergent literal here would
        # not error — it would read a session that does not exist and report
        # an empty transcript, which looks exactly like a quiet session.
        app_name: str = APP_NAME,
        user_id: str = DEFAULT_USER_ID,
        max_chars: int = MAX_TRANSCRIPT_CHARS,
    ) -> None:
        self._session_service = session_service
        self._app_name = app_name
        self._user_id = user_id
        self._max_chars = max_chars

    async def read(self, session_id: str) -> str:
        """Async, because the pass runs at the end of an async session and
        ADK's session store has no synchronous API. Reaching for
        `asyncio.run` here would raise inside the loop that is already
        running."""
        return self._render(await self._get(session_id))

    async def _get(self, session_id: str) -> object | None:
        return await self._session_service.get_session(  # type: ignore[attr-defined]
            app_name=self._app_name, user_id=self._user_id, session_id=session_id
        )

    def _render(self, session: object | None) -> str:
        if session is None:
            logger.warning("no ADK session to read — nothing to discover from")
            return ""

        lines: list[str] = []
        for event in getattr(session, "events", []) or []:
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            text = "".join(getattr(part, "text", "") or "" for part in parts).strip()
            if not text:
                continue
            role = "learner" if getattr(content, "role", "") == "user" else "tutor"
            lines.append(f"{role}: {text}")

        rendered = "\n\n".join(lines)
        return rendered[-self._max_chars :] if len(rendered) > self._max_chars else rendered
