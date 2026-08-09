from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient


class OllamaEmbedding:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def embed(self, text: str) -> list[float]:
        return self._client.embed(self._model, text)
