from charvi_api.agents import AgentSettings, build_agent_registry, route_specialists
from charvi_api.orchestrator import CharviOrchestrator


def test_registry_adds_configured_hermes_openclaw_and_openhands() -> None:
    registry = build_agent_registry(AgentSettings(
        hermes_base_url="http://hermes:8642/v1",
        openclaw_base_url="http://openclaw:18789/v1",
        openhands_base_url="http://openhands:3000/v1",
    ))
    assert set(registry) == {"hermes", "openclaw", "openhands"}


def test_router_selects_coding_specialist() -> None:
    registry = build_agent_registry(AgentSettings(
        openhands_base_url="http://openhands:3000/v1",
        hermes_base_url="http://hermes:8642/v1",
    ))
    assert route_specialists("Build and test a mobile app", registry) == ["openhands"]


def test_router_selects_browser_specialist() -> None:
    registry = build_agent_registry(AgentSettings(
        openclaw_base_url="http://openclaw:18789/v1",
        hermes_base_url="http://hermes:8642/v1",
    ))
    assert route_specialists("Use the browser to navigate this website", registry) == ["openclaw"]


def test_router_uses_hermes_for_general_research() -> None:
    registry = build_agent_registry(AgentSettings(
        hermes_base_url="http://hermes:8642/v1",
        openclaw_base_url="http://openclaw:18789/v1",
    ))
    assert route_specialists("Research the latest GST changes", registry) == ["hermes"]


def test_catalog_reports_openai_as_coordinator_not_specialist() -> None:
    orchestrator = CharviOrchestrator(AgentSettings(
        openai_api_key="secret", openai_model="model"
    ))
    catalog = orchestrator.catalog()
    openai = next(item for item in catalog if item["id"] == "openai")
    assert openai["kind"] == "coordinator_model"
    assert openai["configured"] is True


def test_catalog_never_exposes_credentials() -> None:
    orchestrator = CharviOrchestrator(AgentSettings(
        openai_api_key="secret",
        openai_model="model",
        hermes_base_url="http://hermes:8642/v1",
        hermes_api_token="private-token",
    ))
    rendered = str(orchestrator.catalog())
    assert "secret" not in rendered
    assert "private-token" not in rendered
