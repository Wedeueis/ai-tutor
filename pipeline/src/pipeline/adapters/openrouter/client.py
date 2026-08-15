"""`ChatModelPort` over OpenRouter's OpenAI-compatible chat-completions API —
the cloud alternative to running everything on a local 8B model (issue #19).

**This sends vault content to a third party.** Raw notes, concept bodies, and
anything else a skill puts in a prompt leave the machine when this client is
selected. That is a deliberate, configured choice (`CHAT_PROVIDER=openrouter`),
never a default, and `Settings` logs a warning whenever it is in force.

Why it exists: the prerequisite gate measured 0.517 precision on
`llama3.1:8b` against the human-labelled gold set, with the decisive rubric
showing no discriminative power at all (issue #24). No rollup or threshold
change reached the 0.9 bar, because the limit is the model's judgement rather
than the way its scores are combined."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pipeline.adapters.http_retry import post_with_retry
from pipeline.domain.json_response import (
    MalformedJsonResponse,
    extract_json,
    extract_json_object,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T", dict[str, Any] | list[Any], dict[str, Any])

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 300.0,
        max_tokens: int = 2048,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        app_title: str = "okf-pipeline",
    ) -> None:
        if not api_key:
            # Failing at construction beats failing on the first skill call
            # halfway through an ingest batch, with partial writes behind it.
            raise OpenRouterError(
                "OPENROUTER_API_KEY is not set — required when CHAT_PROVIDER=openrouter"
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._app_title = app_title

    def generate(self, model: str, prompt: str) -> str:
        response = post_with_retry(
            f"{self._base_url}/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "max_tokens": self._max_tokens,
                # Every skill prompt asks for a specific JSON shape and the
                # rollups are thresholded, so sampling noise is pure downside
                # here: the same draft should get the same verdict twice.
                "temperature": 0.0,
            },
            provider="OpenRouter",
            error_cls=OpenRouterError,
            timeout=self._timeout,
            max_retries=self._max_retries,
            retry_backoff_seconds=self._retry_backoff_seconds,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                # OpenRouter attributes usage by these; they are optional, and
                # only ever identify this tool, never the vault or the user.
                "HTTP-Referer": "https://github.com/Wedeueis/ai-tutor",
                "X-Title": self._app_title,
            },
        )
        return _content(response.json())

    def generate_json(self, model: str, prompt: str) -> dict[str, Any] | list[Any]:
        return self._as_json(extract_json, model, prompt)

    def generate_json_object(self, model: str, prompt: str) -> dict[str, Any]:
        return self._as_json(extract_json_object, model, prompt)

    def _as_json(self, parse: Callable[[str], _T], model: str, prompt: str) -> _T:
        text = self.generate(model, prompt)
        try:
            return parse(text)
        except MalformedJsonResponse as exc:
            raise OpenRouterError(str(exc)) from exc


def _content(payload: dict[str, Any]) -> str:
    """OpenRouter returns upstream provider errors as a 200 with an `error`
    key rather than an HTTP status, so a naive `choices[0]` would raise
    `KeyError` and lose the reason (rate limit, no credits, model offline)."""
    if "error" in payload:
        error = payload["error"]
        message = error.get("message") if isinstance(error, dict) else error
        raise OpenRouterError(f"OpenRouter returned an error: {message}")

    choices = payload.get("choices")
    if not choices:
        raise OpenRouterError(f"OpenRouter returned no choices: {payload!r}")

    content = choices[0].get("message", {}).get("content")
    if not content:
        # A reasoning model can spend its entire budget on hidden reasoning and
        # return empty content — the same failure `qwen3.5:4b` shows locally.
        # Say so, rather than letting it surface as "no JSON found".
        raise OpenRouterError(
            "OpenRouter returned empty content — the model may have exhausted "
            "max_tokens on reasoning before answering"
        )
    return str(content)
