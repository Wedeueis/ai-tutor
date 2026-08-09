"""Thin HTTP client for the local Ollama API. Shared by the embedding adapter and
every skill adapter — the one place that knows Ollama's wire format."""

from __future__ import annotations

import json

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str, timeout: float = 300.0, max_predict_tokens: int = 2048) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._max_predict_tokens = max_predict_tokens

    def generate(self, model: str, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self._host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    # A local model that never emits an EOS (e.g. stuck repeating)
                    # would otherwise generate unbounded output; this caps it so a
                    # single call can't hang the pipeline indefinitely.
                    "options": {"num_predict": self._max_predict_tokens},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama generate request failed: {exc}") from exc
        return response.json()["response"]

    def generate_json(self, model: str, prompt: str) -> dict | list:
        """Generates a response and decodes the first complete JSON value found in
        it — local chat models routinely wrap JSON in prose/code fences, or tack on
        extra commentary *after* the JSON, so this scans to the first `{`/`[` and
        decodes incrementally rather than assuming the whole rest of the text (or a
        greedy brace-to-brace regex match) is valid JSON."""
        text = self.generate(model, prompt)
        start = next((i for i, ch in enumerate(text) if ch in "{["), None)
        if start is None:
            raise OllamaError(f"no JSON found in Ollama response: {text!r}")
        try:
            # strict=False: local models routinely emit literal newlines inside
            # JSON string values (e.g. multi-line "body" fields) instead of \n.
            value, _ = json.JSONDecoder(strict=False).raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise OllamaError(f"invalid JSON in Ollama response: {exc}") from exc
        return value

    def generate_with_image(self, model: str, prompt: str, image_base64: str) -> str:
        try:
            response = httpx.post(
                f"{self._host}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_base64],
                    "stream": False,
                    "options": {"num_predict": self._max_predict_tokens},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama generate (vision) request failed: {exc}") from exc
        return response.json()["response"]

    def embed(self, model: str, text: str) -> list[float]:
        try:
            response = httpx.post(
                f"{self._host}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama embeddings request failed: {exc}") from exc
        return response.json()["embedding"]
