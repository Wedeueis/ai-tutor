from __future__ import annotations

from typing import Any, Protocol


class ChatModelPort(Protocol):
    """Text generation for every LLM-backed skill, whoever serves it.

    The seam PRD v3 NFR1 asks for: the provider is configuration, not a
    constant, so reaching a cloud model with better judgement is a settings
    change rather than an integration (issue #19).

    `model` is a per-call argument rather than client state because skills
    differ in what they need — relatedness runs on its own model today — and a
    single client instance serves all of them.

    Deliberately **not** covering embeddings or vision. Embeddings stay local
    unconditionally: every vector in ChromaDB was produced by one model, and
    changing it invalidates the whole index rather than improving it."""

    def generate(self, model: str, prompt: str) -> str: ...

    def generate_json(self, model: str, prompt: str) -> dict[str, Any] | list[Any]:
        """For prompts asking for an array (extraction, quality eval)."""
        ...

    def generate_json_object(self, model: str, prompt: str) -> dict[str, Any]:
        """For prompts asking for a single object — most skills. Raises rather
        than returning an array, which every caller would then `.get` on."""
        ...
