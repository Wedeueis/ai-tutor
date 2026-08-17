"""Refusing to read or write an index that a different model produced.

Every vector in ChromaDB came from one embedding model. Mixing two models'
vectors in one collection does not error — cosine distance is perfectly happy
to compare two unrelated vector spaces and return confident nonsense. The
failure is silent, it degrades every search, and nothing in the stores points
at the cause.

Until now the only defence was a comment in three files asking people not to
change `OLLAMA_EMBED_MODEL`. This is the check that replaces it.

**It fails loudly and names the remedy.** A guard that raises something the
operator cannot act on is only marginally better than no guard.
"""

from __future__ import annotations

import logging

from pipeline.application.ports.index_fingerprint import (
    IndexFingerprint,
    IndexFingerprintPort,
)

logger = logging.getLogger(__name__)


class IndexFingerprintMismatch(RuntimeError):
    """The configured embedding model is not the one that built the index."""


class EnsureIndexFingerprint:
    def __init__(
        self,
        fingerprints: IndexFingerprintPort,
        embed_model: str,
        query_instruction: str = "",
    ) -> None:
        self._fingerprints = fingerprints
        self._embed_model = embed_model
        self._query_instruction = query_instruction
        self._checked = False

    def check(self) -> None:
        """Once per process, before the first read or write of the index.

        Memoized deliberately: this sits in front of `IndexConcept.run`, which
        runs once per concept, and a SQLite round-trip per concept to re-learn
        an answer that cannot change mid-process is waste."""
        if self._checked:
            return

        stored = self._fingerprints.read()
        if stored is None:
            # Nothing indexed yet. Not a mismatch — a new index, which the
            # first `record()` will stamp.
            self._checked = True
            return

        if stored.embed_model != self._embed_model:
            raise IndexFingerprintMismatch(
                f"the index was built with {stored.embed_model!r} "
                f"({stored.dimensions} dimensions) but OLLAMA_EMBED_MODEL is now "
                f"{self._embed_model!r}. Mixing two embedding models in one "
                "collection silently corrupts search rather than failing. "
                "Rebuild with `pipeline index --rebuild`, or start clean with "
                "`pipeline clear --all`."
            )

        if stored.query_instruction != self._query_instruction:
            # Not fatal: the document side carries no instruction, so stored
            # vectors stay valid and only what a query retrieves shifts.
            logger.warning(
                "EMBED_QUERY_INSTRUCTION changed since the index was built "
                "(%r -> %r). Stored vectors are unaffected; retrieval will "
                "shift. Recording the new value.",
                stored.query_instruction,
                self._query_instruction,
            )
            self._fingerprints.write(
                IndexFingerprint(
                    embed_model=stored.embed_model,
                    dimensions=stored.dimensions,
                    query_instruction=self._query_instruction,
                )
            )

        self._checked = True

    def record(self, vector: list[float]) -> None:
        """Stamp the index from the first vector actually produced.

        The dimension comes from the model's own output rather than from
        config, because that is the value that proves the vectors came from the
        model the name claims."""
        if self._fingerprints.read() is not None:
            return
        self._fingerprints.write(
            IndexFingerprint(
                embed_model=self._embed_model,
                dimensions=len(vector),
                query_instruction=self._query_instruction,
            )
        )
        logger.info(
            "index fingerprint recorded: %s, %d dimensions",
            self._embed_model,
            len(vector),
        )

    def forget(self) -> None:
        """The vectors went away; the fingerprint must go with them."""
        self._fingerprints.clear()
        self._checked = False
