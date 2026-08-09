"""Thin HTTP client for the local Ollama API. Shared by the embedding adapter and
every skill adapter — the one place that knows Ollama's wire format."""

from __future__ import annotations

import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 300.0,
        max_predict_tokens: int = 2048,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._max_predict_tokens = max_predict_tokens
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def _post(self, path: str, json_body: dict) -> httpx.Response:
        """POSTs with exponential-backoff retry on transient failures (connection
        errors, timeouts, 5xx) — Ollama being briefly unreachable or overloaded
        mid-run shouldn't abort an entire `ingest`/`parse-sources` batch (see
        IngestRawMaterial/ParseSourceDocuments's own per-item error isolation,
        which this complements rather than replaces). A 4xx (e.g. unknown model)
        is never retried — retrying can't fix a request that's wrong as sent."""
        url = f"{self._host}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                response = httpx.post(url, json=json_body, timeout=self._timeout)
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                retryable = isinstance(exc, httpx.RequestError) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
                )
                if not retryable or attempt > self._max_retries:
                    logger.error("Ollama request to %s failed (attempt %d): %s", path, attempt, exc)
                    raise OllamaError(
                        f"Ollama request to {path} failed after {attempt} attempt(s): {exc}"
                    ) from exc
                backoff = self._retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Ollama request to %s failed (attempt %d/%d): %s — retrying in %.1fs",
                    path,
                    attempt,
                    self._max_retries + 1,
                    exc,
                    backoff,
                )
                time.sleep(backoff)

    def generate(self, model: str, prompt: str) -> str:
        response = self._post(
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                # A local model that never emits an EOS (e.g. stuck repeating)
                # would otherwise generate unbounded output; this caps it so a
                # single call can't hang the pipeline indefinitely.
                "options": {"num_predict": self._max_predict_tokens},
            },
        )
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
        response = self._post(
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
                "options": {"num_predict": self._max_predict_tokens},
            },
        )
        return response.json()["response"]

    def embed(self, model: str, text: str) -> list[float]:
        response = self._post("/api/embeddings", {"model": model, "prompt": text})
        return response.json()["embedding"]
