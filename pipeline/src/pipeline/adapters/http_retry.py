"""Shared POST-with-backoff for the chat-model clients.

Both a local Ollama and a remote OpenRouter call fail the same ways — the
connection drops, the request times out, the server returns 5xx — and both need
the same answer: retry a few times, then give up loudly. Keeping one
implementation means a fix to the retry policy cannot land for one provider and
miss the other."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


def post_with_retry(
    url: str,
    json_body: dict,
    *,
    provider: str,
    error_cls: type[Exception],
    timeout: float,
    max_retries: int,
    retry_backoff_seconds: float,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """POSTs with exponential backoff on transient failures.

    A brief outage mid-run shouldn't abort an entire `ingest`/`parse-sources`
    batch (this complements the per-item error isolation in those use cases
    rather than replacing it).

    **4xx is never retried.** Retrying cannot fix a request that is wrong as
    sent — an unknown model, a missing or rejected API key, a malformed body —
    and for a metered provider it would turn one bad request into several."""
    attempt = 0
    while True:
        attempt += 1
        try:
            response = httpx.post(url, json=json_body, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            retryable = isinstance(exc, httpx.RequestError) or (
                isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
            )
            if not retryable or attempt > max_retries:
                logger.error("%s request to %s failed (attempt %d): %s", provider, url, attempt, exc)
                raise error_cls(
                    f"{provider} request to {url} failed after {attempt} attempt(s): "
                    f"{_detail(exc)}"
                ) from exc
            backoff = retry_backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "%s request to %s failed (attempt %d/%d): %s — retrying in %.1fs",
                provider,
                url,
                attempt,
                max_retries + 1,
                exc,
                backoff,
            )
            time.sleep(backoff)


def _detail(exc: httpx.HTTPError) -> str:
    """A 4xx body usually says exactly what is wrong ("model not found", "no
    credits"), and losing it turns a five-second fix into a debugging session."""
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text.strip()
        if body:
            return f"{exc} — {body[:500]}"
    return str(exc)
