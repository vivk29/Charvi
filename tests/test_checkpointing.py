import asyncio

import pytest

from charvi_api.agents import AgentSettings
from charvi_api.orchestrator import CharviOrchestrator


def test_checkpointed_graph_persists_state_for_a_thread() -> None:
    memory_module = pytest.importorskip("langgraph.checkpoint.memory")
    checkpointer = memory_module.InMemorySaver()
    orchestrator = CharviOrchestrator(AgentSettings(), checkpointer=checkpointer)

    result = asyncio.run(orchestrator.run(
        task="Remember this task state",
        context="checkpoint test",
        thread_id="thread-test-001",
    ))

    assert orchestrator.checkpointing_enabled is True
    assert result.status == "unavailable"  # Ollama is deliberately not configured in this test.
    snapshot = asyncio.run(orchestrator._graph.aget_state({
        "configurable": {"thread_id": "thread-test-001"}
    }))
    assert snapshot.values["task"] == "Remember this task state"
    assert snapshot.values["context"] == "checkpoint test"
    assert snapshot.values["coordinator"]["agent_id"] == "ollama"


def test_completed_thread_has_no_pending_resume_work() -> None:
    memory_module = pytest.importorskip("langgraph.checkpoint.memory")
    checkpointer = memory_module.InMemorySaver()
    orchestrator = CharviOrchestrator(AgentSettings(), checkpointer=checkpointer)

    async def scenario():
        await orchestrator.run(task="Complete a normal run", thread_id="thread-complete")
        return await orchestrator.resume(thread_id="thread-complete")

    assert asyncio.run(scenario()) is None


def test_catalog_reports_durable_checkpointing_only_when_saver_is_supplied() -> None:
    memory_module = pytest.importorskip("langgraph.checkpoint.memory")
    orchestrator = CharviOrchestrator(
        AgentSettings(),
        checkpointer=memory_module.InMemorySaver(),
    )
    langgraph = next(item for item in orchestrator.catalog() if item["id"] == "langgraph")
    assert langgraph["durable_checkpointing"] is True
