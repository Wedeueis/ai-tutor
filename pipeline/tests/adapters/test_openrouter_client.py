"""The OpenRouter client's response handling.

The HTTP layer is stubbed rather than mocked with a library — the interesting
behaviour is what the client does with a *reply*, especially the several ways
OpenRouter reports a failure without using an HTTP status."""

import httpx
import pytest

from pipeline.adapters.openrouter.client import OpenRouterClient, OpenRouterError


def _client(monkeypatch, payload=None, *, status=200, captured=None):
    def fake_post(url, json=None, headers=None, timeout=None):
        if captured is not None:
            captured.update({"url": url, "json": json, "headers": headers})
        request = httpx.Request("POST", url)
        return httpx.Response(status, json=payload, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    return OpenRouterClient(api_key="sk-test", max_retries=0, retry_backoff_seconds=0)


def _reply(content):
    return {"choices": [{"message": {"content": content}}]}


# --- construction --------------------------------------------------------


def test_a_missing_api_key_fails_at_construction_not_mid_batch():
    """Failing on the first skill call would leave partial writes behind it."""
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY is not set"):
        OpenRouterClient(api_key="")


# --- the request ---------------------------------------------------------


def test_the_key_is_sent_as_a_bearer_token(monkeypatch):
    captured: dict = {}
    client = _client(monkeypatch, _reply("hi"), captured=captured)

    client.generate("anthropic/claude-sonnet-4.5", "hello")

    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_generation_is_deterministic(monkeypatch):
    """Every skill prompt asks for a specific JSON shape and every rollup is
    thresholded, so sampling noise is pure downside: the same draft should get
    the same verdict twice."""
    captured: dict = {}
    client = _client(monkeypatch, _reply("hi"), captured=captured)

    client.generate("some/model", "hello")

    assert captured["json"]["temperature"] == 0.0
    assert captured["json"]["stream"] is False


def test_the_prompt_is_sent_as_a_single_user_message(monkeypatch):
    captured: dict = {}
    client = _client(monkeypatch, _reply("hi"), captured=captured)

    client.generate("some/model", "judge this pair")

    assert captured["json"]["messages"] == [
        {"role": "user", "content": "judge this pair"}
    ]


# --- the reply -----------------------------------------------------------


def test_content_is_returned(monkeypatch):
    client = _client(monkeypatch, _reply('{"score": 0.9}'))

    assert client.generate("some/model", "p") == '{"score": 0.9}'


def test_json_is_parsed_with_the_shared_extractor(monkeypatch):
    client = _client(monkeypatch, _reply('Sure!\n{"score": 0.9}\nHope that helps.'))

    assert client.generate_json_object("some/model", "p") == {"score": 0.9}


def test_an_array_where_an_object_was_asked_for_is_an_openrouter_error(monkeypatch):
    """Callers catch one provider error type, whichever layer failed."""
    client = _client(monkeypatch, _reply('[{"a": 1}]'))

    with pytest.raises(OpenRouterError, match="expected a JSON object"):
        client.generate_json_object("some/model", "p")


def test_an_upstream_error_returned_as_http_200_is_surfaced(monkeypatch):
    """OpenRouter reports provider failures — rate limits, no credits, model
    offline — in the body with a 200 status. A naive `choices[0]` would raise
    KeyError and lose the reason."""
    client = _client(monkeypatch, {"error": {"message": "Insufficient credits"}})

    with pytest.raises(OpenRouterError, match="Insufficient credits"):
        client.generate("some/model", "p")


def test_a_reply_with_no_choices_is_reported_clearly(monkeypatch):
    client = _client(monkeypatch, {})

    with pytest.raises(OpenRouterError, match="no choices"):
        client.generate("some/model", "p")


def test_empty_content_names_the_likely_cause_and_the_first_fix(monkeypatch):
    """A model can spend its whole budget thinking and return nothing — the
    failure `qwen3.5:4b` shows locally. "No JSON found" would send the reader
    looking in the wrong place, so the message names both the cause and the
    setting to check."""
    client = _client(monkeypatch, _reply(""))

    with pytest.raises(OpenRouterError, match="OPENROUTER_REASONING"):
        client.generate("some/model", "p")


# --- failures ------------------------------------------------------------


def test_a_4xx_is_not_retried_and_keeps_the_response_body(monkeypatch):
    """The body says what is wrong ("model not found", "no credits"), and for
    a metered provider retrying would turn one bad request into several."""
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        request = httpx.Request("POST", url)
        return httpx.Response(401, text="No auth credentials found", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="sk-bad", max_retries=3, retry_backoff_seconds=0)

    with pytest.raises(OpenRouterError, match="No auth credentials found"):
        client.generate("some/model", "p")
    assert calls["n"] == 1


def test_a_5xx_is_retried_then_gives_up(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        request = httpx.Request("POST", url)
        return httpx.Response(503, text="upstream unavailable", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="sk-test", max_retries=2, retry_backoff_seconds=0)

    with pytest.raises(OpenRouterError, match="after 3 attempt"):
        client.generate("some/model", "p")
    assert calls["n"] == 3


# --- reasoning is off by default -----------------------------------------


def test_reasoning_is_disabled_by_default(monkeypatch):
    """Skill prompts ask for scored JSON whose own `rationale` fields are the
    only reasoning anything downstream reads, so chain-of-thought tokens are
    billed and then discarded. Worse, a model that spends its budget thinking
    returns empty content — how `deepseek-v4-flash` failed 14 of 30 gold-set
    pairs. Measured 4.3x cheaper with it off."""
    captured: dict = {}
    client = _client(monkeypatch, _reply("hi"), captured=captured)

    client.generate("deepseek/deepseek-v4-flash-0731", "hello")

    assert captured["json"]["reasoning"] == {"enabled": False}


def test_reasoning_can_be_turned_back_on(monkeypatch):
    """`OPENROUTER_REASONING=true`, for a task that genuinely needs it — the
    parameter is then omitted entirely so the model's own default applies."""

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update({"json": json})
        return httpx.Response(200, json=_reply("hi"), request=httpx.Request("POST", url))

    captured: dict = {}
    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenRouterClient(api_key="sk-test", reasoning=True, max_retries=0)

    client.generate("some/model", "hello")

    assert "reasoning" not in captured["json"]
