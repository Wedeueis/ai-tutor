"""Reading a finished session back, and asking what it revealed about the vault.

Two ports, because they are two different things that both happen after the
session ends: one reads ADK's transcript, one asks a model what was in it.

**Neither is on the teaching path.** The shipped invariant block tells the
teaching agent it has no tools that write and must not describe itself as
filing anything — *"recording that is handled outside this conversation"*.
This is that outside (#39).

The `Discovery` type is the boundary. It can be a coverage gap, a contradiction
or a proposed concept, and it **cannot be anything about the learner** — there
is no kind for that, so nothing downstream has to decide whether a discovery is
safe to file (§2.1, NFR5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class DiscoveryKind(str, Enum):
    COVERAGE_GAP = "coverage_gap"
    CONTRADICTION = "contradiction"
    DERIVED_CONCEPT = "derived_concept"


@dataclass(frozen=True)
class Discovery:
    """Something a session revealed about the **vault**.

    Every field here is semantic: it would read the same to someone who never
    took the session, which is the test §2.1 sets. A blindspot fails that test,
    and the enumeration above is why it cannot be expressed."""

    kind: DiscoveryKind
    title: str
    body: str
    concept_ids: tuple[str, ...] = field(default_factory=tuple)


class TranscriptPort(Protocol):
    async def read(self, session_id: str) -> str:
        """The conversation, as text.

        The **only** reader of ADK's session store in all of `tutor`, and it
        runs while the session is still live: the transcript is disposable and
        may be dropped at any time, so nothing may depend on it later (#39)."""
        ...


class DiscoverySkillPort(Protocol):
    async def discover(
        self, transcript: str, concept_ids: tuple[str, ...]
    ) -> list[Discovery]:
        """What did this session reveal about the vault?

        A dedicated call rather than an aside inside a teaching turn: spotting
        that three concepts lean on an undefined term is a different task from
        teaching, and a prompt that does only that does it better."""
        ...
