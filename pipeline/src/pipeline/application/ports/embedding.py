from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    """Turns text into a vector embedding.

    **Query and document are separate verbs because the asymmetry belongs to
    the model, not to the caller.** `qwen3-embedding` expects
    `Instruct: <task>\\nQuery: <text>` on the query side and bare text on the
    document side; `nomic-embed-text` before it wanted `search_query:` /
    `search_document:`. Either way, sending one where the other belongs costs
    real retrieval quality.

    A single `embed()` with a defaulted meaning is what this replaces, and it
    is worth saying why: under it, every call site silently meant "document",
    including the one that embeds the user's search query — and nothing in the
    type system could point at the mistake. Two verbs make each call site state
    which side it is on, and make a wrong answer a visible one.

    Deliberately **not** on the swappable chat-provider seam (NFR1, issue #19).
    Embeddings stay local unconditionally: every vector in the index came from
    one model, so changing it invalidates the index rather than improving it.
    `IndexFingerprintPort` is what turns that from a promise into a check.
    """

    def embed_document(self, text: str) -> list[float]:
        """Text being indexed, or compared against indexed text."""
        ...

    def embed_query(self, text: str, task: str | None = None) -> list[float]:
        """Text someone is searching *with*.

        `task` overrides the configured instruction for callers that know
        something more specific about what they are retrieving."""
        ...
