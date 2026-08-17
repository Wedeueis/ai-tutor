"""`DiscoverySkillPort` over LiteLLM.

The model that reads a finished session and says what it revealed about the
**vault**. A dedicated call rather than an aside inside a teaching turn:
spotting that three concepts lean on an undefined term is a different task from
teaching, and a prompt that does only that does it better (#43).

Same seam as `assessment.py` — one model string, so #19's swap stays a config
change (NFR1). Off the interactive path (NFR8): this runs after the last review
is already committed, and losing its output costs inquiries, never a review.

**The boundary is upstream of this file.** The prompt below asks for nothing
about the learner, but that is not what enforces it: `DiscoveryKind` has no
member for a blindspot, so an entry claiming to be one has nowhere to go. A
model that ignores the instruction produces something the parser drops, not
something the pass files in the wrong place.
"""

from __future__ import annotations

import logging
from typing import Any

from litellm import acompletion

from tutor.adapters.llm._json import as_array
from tutor.application.ports.outbound.discovery import Discovery, DiscoveryKind

logger = logging.getLogger(__name__)

_DISCOVER = """You have just finished a tutoring session over someone's
personal knowledge vault. Read the transcript and report what it revealed
**about the vault itself** — not about the learner.

You are looking for exactly three things:

- "coverage_gap": the vault leans on something it never defines or explains.
- "contradiction": two concepts in the vault disagree with each other.
- "derived_concept": a distinction or synthesis the session produced that the
  vault does not state anywhere, and that would read the same to someone who
  never took this session.

Report NOTHING about the learner. What they got wrong, what they confuse, how
they are progressing, what they should study — none of that belongs here, and
there is no category for it. The test for every entry: *would this still make
sense to someone who never took this session?* If not, leave it out.

Report only what the transcript actually supports. An empty array is the right
answer for a session that revealed nothing — do not invent findings to fill it.

Concepts taught this session:
{concept_ids}

Transcript:
---
{transcript}
---

Respond with ONLY a JSON array:
[{{"kind": "coverage_gap" | "contradiction" | "derived_concept",
   "title": "<short, specific>",
   "body": "<what it is, and what in the session showed it>",
   "concept_ids": ["<ids this concerns, from the list above>"]}}, ...]
"""


class LiteLlmDiscoverySkill:
    def __init__(
        self, model: str, api_base: str | None = None, temperature: float = 0.2
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._temperature = temperature

    async def discover(
        self, transcript: str, concept_ids: tuple[str, ...]
    ) -> list[Discovery]:
        """Whatever the model reported that maps onto a real `DiscoveryKind`.

        An empty transcript short-circuits: the ADK session store is disposable
        and may hand back nothing (#39), and asking a model to find findings in
        no text is how you get invented ones."""
        if not transcript.strip():
            logger.info("empty transcript — nothing to discover from")
            return []

        raw = await self._complete(
            _DISCOVER.format(
                concept_ids="\n".join(f"- {cid}" for cid in concept_ids) or "(none)",
                transcript=transcript,
            )
        )
        return [
            discovery
            for discovery in (_discovery(entry, concept_ids) for entry in as_array(raw))
            if discovery is not None
        ]

    async def _complete(self, prompt: str) -> str:
        response = await acompletion(
            model=self._model,
            api_base=self._api_base,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response["choices"][0]["message"]["content"] or "")


def _discovery(entry: Any, taught: tuple[str, ...]) -> Discovery | None:
    """One entry, or `None` if it is not usable.

    **An unrecognised `kind` is dropped, never defaulted.** Routing an
    unfamiliar kind to a default branch is exactly how something about the
    learner would reach the vault — the one failure this design exists to make
    impossible (§2.1, NFR5)."""
    if not isinstance(entry, dict):
        return None
    try:
        kind = DiscoveryKind(str(entry.get("kind", "")).strip().lower())
    except ValueError:
        logger.warning("dropping discovery with unknown kind %r", entry.get("kind"))
        return None

    title = str(entry.get("title") or "").strip()
    body = str(entry.get("body") or "").strip()
    if not title or not body:
        logger.warning("dropping discovery %r with no title or body", title)
        return None

    return Discovery(
        kind=kind,
        title=title,
        body=body,
        # Narrowed to what was actually taught: a model naming a concept that
        # was not in this session is guessing, and a link to a concept that
        # does not exist is worse than no link.
        concept_ids=tuple(
            cid for cid in _string_list(entry.get("concept_ids")) if cid in taught
        ),
    )


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]
