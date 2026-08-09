from __future__ import annotations

import httpx
import pytest

OLLAMA_HOST = "http://localhost:11434"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: needs a real local service (e.g. Ollama) running"
    )


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    try:
        httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def _skip_if_ollama_unavailable(request, ollama_available):
    if request.node.get_closest_marker("integration") and not ollama_available:
        pytest.skip("Ollama is not reachable at localhost:11434")
