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
    invalidates the index rather than improving it."""
    monkeypatch.setenv("CHAT_PROVIDER", "openrouter")

    assert Settings.from_env().ollama_embed_model == "nomic-embed-text"
