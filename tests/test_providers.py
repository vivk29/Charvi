import asyncio

import httpx

from charvi_api.agents import AgentSettings
from charvi_api.providers import coordinator_status


def test_ollama_status_reports_unconfigured_without_network_call() -> None:
    result = asyncio.run(coordinator_status(AgentSettings()))
    assert result["provider"] == "ollama"
    assert result["configured"] is False
    assert result["reachable"] is None
    assert result["subscription_required"] is False


def test_ollama_status_checks_model_list_without_generation(monkeypatch) -> None:
    requested = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.2:3b"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            requested["url"] = url
            requested["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    settings = AgentSettings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="local-token",
    )
    result = asyncio.run(coordinator_status(settings))
    assert requested["url"] == "http://localhost:11434/v1/models"
    assert requested["headers"]["Authorization"] == "Bearer local-token"
    assert result["reachable"] is True
    assert result["model_available"] is True
    assert result["available_models"] == ["qwen2.5:7b", "llama3.2:3b"]
    assert "local-token" not in str(result)


def test_ollama_status_distinguishes_missing_model(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "llama3.2:3b"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(coordinator_status(AgentSettings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
    )))
    assert result["reachable"] is True
    assert result["model_available"] is False


def test_unknown_provider_is_reported_without_fallback_to_paid_api() -> None:
    result = asyncio.run(coordinator_status(AgentSettings(
        coordinator_provider="claude",
    )))
    assert result["provider"] == "claude"
    assert result["configured"] is False
    assert result["reachable"] is None
