import asyncio

import pytest

from charvi_api.agents import (
    AgentSettings,
    BrowserUseSDKBackend,
    build_agent_registry,
    route_specialists,
)
from charvi_api.orchestrator import CharviOrchestrator


def test_registry_adds_configured_hermes_and_openclaw() -> None:
    registry = build_agent_registry(AgentSettings(
        hermes_base_url="http://hermes:8642/v1",
        openclaw_base_url="http://openclaw:18789/v1",
    ))
    assert {"hermes", "openclaw", "browser_use"} == set(registry)


def test_openhands_is_disabled_until_explicitly_enabled_and_authenticated() -> None:
    disabled = build_agent_registry(AgentSettings(
        openhands_base_url="http://openhands:3000/v1",
        openhands_api_token="token",
    ))
    assert "openhands" not in disabled
    enabled = build_agent_registry(AgentSettings(
        openhands_base_url="http://openhands:3000/v1",
        openhands_api_token="token",
        openhands_enabled=True,
    ))
    assert "openhands" in enabled
    assert enabled["openhands"].auth_header == "X-Session-API-Key"


def test_router_selects_openhands_only_when_execution_is_approved() -> None:
    registry = build_agent_registry(AgentSettings(
        openhands_base_url="http://openhands:3000/v1",
        openhands_api_token="token",
        openhands_enabled=True,
    ))
    assert route_specialists("Build and test a mobile app", registry) == []
    assert route_specialists(
        "Build and test a mobile app", registry, allow_code_execution=True
    ) == ["openhands"]


def test_router_prefers_browser_use_for_read_only_browser_research() -> None:
    registry = build_agent_registry(AgentSettings(
        openclaw_base_url="http://openclaw:18789/v1",
    ))
    assert route_specialists("Use the browser to navigate this website", registry) == [
        "browser_use"
    ]


def test_browser_use_blocks_state_changing_tasks() -> None:
    backend = BrowserUseSDKBackend(AgentSettings(
        browser_use_enabled=True,
        browser_use_worker_token="private",
    ))
    assert backend._blocked.search("Book an appointment")
    result = asyncio.run(backend.invoke(task="Research a public webpage", context=""))
    assert result.status == "not_configured"


def test_router_uses_hermes_for_general_research() -> None:
    registry = build_agent_registry(AgentSettings(
        hermes_base_url="http://hermes:8642/v1",
    ))
    assert route_specialists("Research the latest GST changes", registry) == ["hermes"]


def test_catalog_reports_langgraph_and_does_not_expose_credentials() -> None:
    orchestrator = CharviOrchestrator(AgentSettings(
        openai_api_key="secret",
        openai_model="model",
        hermes_base_url="http://hermes:8642/v1",
        hermes_api_token="private-token",
    ))
    catalog = orchestrator.catalog()
    openai = next(item for item in catalog if item["id"] == "openai")
    langgraph = next(item for item in catalog if item["id"] == "langgraph")
    assert openai["kind"] == "coordinator_model"
    assert openai["configured"] is True
    assert langgraph["kind"] == "orchestration_framework"
    rendered = str(catalog)
    assert "secret" not in rendered
    assert "private-token" not in rendered


def test_langgraph_graph_compiles_when_optional_dependency_is_installed() -> None:
    pytest.importorskip("langgraph.graph")
    orchestrator = CharviOrchestrator(AgentSettings())
    assert orchestrator._graph is not None
