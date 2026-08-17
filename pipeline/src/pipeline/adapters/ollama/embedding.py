"""`EmbeddingPort` over Ollama.

Holds the one thing the port's two verbs actually differ by: the instruction
prefix a query carries and a document does not.

An empty `query_instruction` means no prefix at all, which keeps this adapter
correct for models that do not want one (`nomic-embed-text` and friends) rather
than needing a second class for them.
"""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient


class OllamaEmbedding:
    def __init__(
        self, client: OllamaClient, model: str, query_instruction: str = ""
    ) -> None:
        self._client = client
        self._model = model
        self._query_instruction = query_instruction

    def embed_document(self, text: str) -> list[float]:
        """No prefix, ever.

        This is also what makes the instruction cheap to change later: because
        the document side carries none, editing `EMBED_QUERY_INSTRUCTION`
        re-tunes retrieval without invalidating a single stored vector."""
        return self._client.embed(self._model, text)

    def embed_query(self, text: str, task: str | None = None) -> list[float]:
        instruction = self._query_instruction if task is None else task
        prompt = f"Instruct: {instruction}\nQuery: {text}" if instruction else text
        return self._client.embed(self._model, prompt)
