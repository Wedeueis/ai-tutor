"""Thin HTTP client for the local Ollama API — the one place that knows
Ollama's wire format. Satisfies `ChatModelPort`, and additionally serves
embeddings and vision, which stay local unconditionally (see that port)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

from pipeline.adapters.http_retry import post_with_retry
from pipeline.domain.json_response import MalformedJsonResponse, extract_json, extract_json_object

logger = logging.getLogger(__name__)

_T = TypeVar("_T", dict[str, Any] | list[Any], dict[str, Any])


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
        return post_with_retry(
            f"{self._host}{path}",
            json_body,
            provider="Ollama",
            error_cls=OllamaError,
            timeout=self._timeout,
            max_retries=self._max_retries,
            retry_backoff_seconds=self._retry_backoff_seconds,
        )

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

    def generate_json(self, model: str, prompt: str) -> dict[str, Any] | list[Any]:
        """Returns whichever shape the model produced. Only the extraction and
        quality-eval skills want an array; every other skill should call
        `generate_json_object`."""
        return self._as_json(extract_json, model, prompt)

    def generate_json_object(self, model: str, prompt: str) -> dict[str, Any]:
        return self._as_json(extract_json_object, model, prompt)

    def _as_json(self, parse: Callable[[str], _T], model: str, prompt: str) -> _T:
        text = self.generate(model, prompt)
        try:
            return parse(text)
        except MalformedJsonResponse as exc:
            # Re-raised as OllamaError so callers keep catching one provider
            # error type, whichever layer the failure came from.
            raise OllamaError(str(exc)) from exc

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
