"""Charvi's single-front-door, LangGraph-backed multi-agent coordinator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from .agents import (
    AgentResult,
    AgentSettings,
    OpenAIResponsesBackend,
    build_agent_registry,
    run_specialists,
)


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    status: str
    coordinator: AgentResult
    specialists: tuple[AgentResult, ...]
    routed_to: tuple[str, ...]


class _RunState(TypedDict, total=False):
    task: str
    context: str
    allow_code_execution: bool
    specialists: list[AgentResult]
    coordinator: AgentResult


class CharviOrchestrator:
    def __init__(self, settings: AgentSettings | None = None):
        self.settings = settings or AgentSettings()
        self.registry = build_agent_registry(self.settings)
        self.coordinator = OpenAIResponsesBackend(self.settings)
        self._graph = self._build_graph()

    def _build_graph(self):
        """Use LangGraph when installed; retain a tested async fallback for base installs."""
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            return None

        async def dispatch(state: _RunState) -> dict[str, Any]:
            results = await run_specialists(
                task=state["task"],
                registry=self.registry,
                context=state.get("context", ""),
                allow_code_execution=state.get("allow_code_execution", False),
            )
            return {"specialists": results}

        async def synthesize(state: _RunState) -> dict[str, Any]:
            specialist_context = "\n\n".join(
                f"[{item.agent_id} — {item.status}]\n{item.output or item.error or 'No result'}"
                for item in state.get("specialists", [])
            )
            combined_context = "\n\n".join(
                part for part in (state.get("context", ""), specialist_context) if part
            )
            result = await self.coordinator.invoke(
                task=state["task"], context=combined_context
            )
            if result.status != "completed":
                successful = [
                    item for item in state.get("specialists", [])
                    if item.status == "completed"
                ]
                if len(successful) == 1:
                    result = successful[0]
                elif successful:
                    result = AgentResult(
                        "charvi",
                        "completed",
                        output="\n\n".join(
                            f"### {item.agent_id}\n{item.output}" for item in successful
                        ),
                        execution_performed=any(item.execution_performed for item in successful),
                    )
            return {"coordinator": result}

        graph = StateGraph(_RunState)
        graph.add_node("dispatch_specialists", dispatch)
        graph.add_node("synthesize_result", synthesize)
        graph.add_edge(START, "dispatch_specialists")
        graph.add_edge("dispatch_specialists", "synthesize_result")
        graph.add_edge("synthesize_result", END)
        return graph.compile()

    def catalog(self) -> list[dict[str, Any]]:
        rows = [
            {
                "id": agent_id,
                "kind": "specialist_runtime",
                "capabilities": list(backend.capabilities),
                "configured": (
                    bool(getattr(backend, "settings", None).browser_use_enabled)
                    if agent_id == "browser_use"
                    else True
                ),
                "execution_requires_approval": agent_id == "openhands",
            }
            for agent_id, backend in self.registry.items()
        ]
        rows.append({
            "id": "langgraph",
            "kind": "orchestration_framework",
            "capabilities": ["stateful_workflows", "async_handoffs", "graph_execution"],
            "configured": self._graph is not None,
        })
        rows.append({
            "id": "openai",
            "kind": "coordinator_model",
            "capabilities": list(self.coordinator.capabilities),
            "configured": bool(self.settings.openai_api_key and self.settings.openai_model),
        })
        return rows

    async def run(
        self,
        *,
        task: str,
        context: str = "",
        allow_code_execution: bool = False,
    ) -> OrchestrationResult:
        state: _RunState = {
            "task": task,
            "context": context,
            "allow_code_execution": allow_code_execution,
        }
        if self._graph is not None:
            result_state = await self._graph.ainvoke(state)
            specialist_results = result_state.get("specialists", [])
            coordinator = result_state.get(
                "coordinator",
                AgentResult("charvi", "unavailable", error="Graph returned no coordinator result."),
            )
        else:
            specialist_results = await run_specialists(
                task=task,
                registry=self.registry,
                context=context,
                allow_code_execution=allow_code_execution,
            )
            specialist_context = "\n\n".join(
                f"[{item.agent_id} — {item.status}]\n{item.output or item.error or 'No result'}"
                for item in specialist_results
            )
            coordinator = await self.coordinator.invoke(
                task=task,
                context="\n\n".join(part for part in (context, specialist_context) if part),
            )
            if coordinator.status != "completed":
                successful = [item for item in specialist_results if item.status == "completed"]
                if len(successful) == 1:
                    coordinator = successful[0]
                elif successful:
                    coordinator = AgentResult(
                        "charvi", "completed",
                        output="\n\n".join(
                            f"### {item.agent_id}\n{item.output}" for item in successful
                        ),
                        execution_performed=any(item.execution_performed for item in successful),
                    )
        status = "completed" if coordinator.status == "completed" else "unavailable"
        return OrchestrationResult(
            status=status,
            coordinator=coordinator,
            specialists=tuple(specialist_results),
            routed_to=tuple(item.agent_id for item in specialist_results),
        )
