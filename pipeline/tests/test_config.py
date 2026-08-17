"""Provider selection (PRD v3 NFR1, issue #19)."""

import pytest

from pipeline.config import ChatProvider, Settings


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    """`.env` is loaded at import time, so a developer's real key would
    otherwise leak into these assertions."""
    for name in (
        "CHAT_PROVIDER",
        "OPENROUTER_API_KEY",
        "OPENROUTER_CHAT_MODEL",
        "OPENROUTER_RELATEDNESS_MODEL",
        "OLLAMA_CHAT_MODEL",
        "OLLAMA_RELATEDNESS_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_the_default_provider_is_local():
    """Sending vault content to a third party has to be chosen, never
    inherited."""
    assert Settings.from_env().chat_provider is ChatProvider.OLLAMA


def test_the_chat_model_resolves_to_the_active_provider(monkeypatch):
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "anthropic/claude-sonnet-4.5")

    assert Settings.from_env().chat_model == "llama3.1:8b"

    monkeypatch.setenv("CHAT_PROVIDER", "openrouter")
    assert Settings.from_env().chat_model == "anthropic/claude-sonnet-4.5"


def test_the_relatedness_model_stays_separately_configurable(monkeypatch):
    """It has always had its own override; keeping that per provider stops a
    switch silently changing which model judges relatedness."""
    monkeypatch.setenv("CHAT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "anthropic/claude-sonnet-4.5")
    monkeypatch.setenv("OPENROUTER_RELATEDNESS_MODEL", "openai/gpt-4o-mini")

    settings = Settings.from_env()

    assert settings.chat_model == "anthropic/claude-sonnet-4.5"
    assert settings.relatedness_model == "openai/gpt-4o-mini"


def test_the_relatedness_model_falls_back_to_the_chat_model(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_CHAT_MODEL", "anthropic/claude-sonnet-4.5")

    assert Settings.from_env().relatedness_model == "anthropic/claude-sonnet-4.5"


def test_an_unknown_provider_stops_the_run(monkeypatch):
    """Falling back to local would silently keep using the model the user was
    trying to move off."""
    monkeypatch.setenv("CHAT_PROVIDER", "openrouterr")

    with pytest.raises(ValueError, match="CHAT_PROVIDER must be one of"):
        Settings.from_env()


def test_the_provider_name_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "  OpenRouter \n")

    assert Settings.from_env().chat_provider is ChatProvider.OPENROUTER


def test_an_absent_api_key_reads_as_none_not_empty_string(monkeypatch):
    """So the client's own "not set" check fires, rather than sending an
    `Authorization: Bearer ` header and getting a confusing 401."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    assert Settings.from_env().openrouter_api_key is None


def test_the_embedding_model_is_unaffected_by_the_provider(monkeypatch):
    """Every vector in ChromaDB came from one embedding model; changing it
    invalidates the index rather than improving it.

    Asserted against the default constant rather than a literal: the claim is
    that switching *chat* provider leaves embeddings alone, which has nothing
    to do with which embedding model is current."""
    from pipeline.config import DEFAULT_EMBED_MODEL

    monkeypatch.setenv("CHAT_PROVIDER", "openrouter")

    assert Settings.from_env().ollama_embed_model == DEFAULT_EMBED_MODEL


def test_the_default_embedding_model_is_multilingual():
    """The vault takes material in English and Portuguese. `nomic-embed-text`
    is English-centric and was measurably weaker on Brazilian Portuguese."""
    from pipeline.config import DEFAULT_EMBED_MODEL

    assert DEFAULT_EMBED_MODEL != "nomic-embed-text"
    assert DEFAULT_EMBED_MODEL.startswith("qwen3-embedding")


def test_the_query_instruction_is_set_by_default(monkeypatch):
    """An empty instruction silently disables prefixing, which is exactly the
    bug the port split exists to prevent — so the default must not be empty."""
    monkeypatch.delenv("EMBED_QUERY_INSTRUCTION", raising=False)

    assert Settings.from_env().embed_query_instruction.strip() != ""


def test_the_default_openrouter_model_is_not_a_premium_one():
    """Cost is a first-class constraint here: a personal vault, and a full
    prerequisite backfill is hundreds of calls. A cheap model underperforming
    is a reason to fix the harness before it is a reason to spend more."""
    from pipeline.config import DEFAULT_OPENROUTER_CHAT_MODEL

    assert DEFAULT_OPENROUTER_CHAT_MODEL.startswith("deepseek/")


def test_reasoning_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("OPENROUTER_REASONING", raising=False)
    assert Settings.from_env().openrouter_reasoning is False

    monkeypatch.setenv("OPENROUTER_REASONING", "true")
    assert Settings.from_env().openrouter_reasoning is True
