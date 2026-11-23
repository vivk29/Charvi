"""Charvi's single-front-door, LangGraph-backed multi-agent coordinator."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Annotated, Any, TypedDict

from .agents import AgentResult, AgentSettings, build_agent_registry, run_specialists
from .providers import build_coordinator, coordinator_status


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
    allow_device_control: bool
    specialists: list[dict[str, Any]]
    coordinator: dict[str, Any]
    history: Annotated[list[dict[str, str]], _merge_history]


def _restore_result(value: dict[str, Any]) -> AgentResult:
    return AgentResult(**value)


def _merge_history(
    previous: list[dict[str, str]] | None,
    new: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Append conversation messages while bounding checkpoint growth."""
    return ((previous or []) + (new or []))[-40:]


class CharviOrchestrator:
    def __init__(self, settings: AgentSettings | None = None, checkpointer: Any = None):
        self.settings = settings or AgentSettings()
        self.registry = build_agent_registry(self.settings)
        self.coordinator = build_coordinator(self.settings)
        self.checkpointing_enabled = checkpointer is not None
        self._graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: Any = None):
        """Compile the graph with durable persistence when a Postgres saver is supplied."""
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError:
            return None

        async def dispatch(state: _RunState) -> dict[str, Any]:
            previous_history = state.get("history", [])[:-1]
            history_context = "\n".join(
                f"{message['role']}: {message['content']}"
                for message in previous_history
            )
            specialist_context = "\n\n".join(
                part for part in (state.get("context", ""), history_context) if part
            )
            results = await run_specialists(
                task=state["task"],
                registry=self.registry,
                context=specialist_context,
                allow_code_execution=state.get("allow_code_execution", False),
                allow_device_control=state.get("allow_device_control", False),
            )
            # Persist plain JSON-compatible dictionaries, not custom Python objects.
            return {"specialists": [asdict(item) for item in results]}

        async def synthesize(state: _RunState) -> dict[str, Any]:
            specialists = [
                _restore_result(item) for item in state.get("specialists", [])
            ]
            specialist_context = "\n\n".join(
                f"[{item.agent_id} — {item.status}]\n{item.output or item.error or 'No result'}"
                for item in specialists
            )
            previous_history = state.get("history", [])[:-1]
            history_context = "\n".join(
                f"{message['role']}: {message['content']}"
                for message in previous_history
            )
            combined_context = "\n\n".join(
                part for part in (state.get("context", ""), history_context, specialist_context) if part
            )
            result = await self.coordinator.invoke(task=state["task"], context=combined_context)
            if result.status != "completed":
                successful = [item for item in specialists if item.status == "completed"]
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
            return {
                "coordinator": asdict(result),
                "history": [{
                    "role": "assistant",
                    "content": result.output or result.error or "No response was produced.",
                }],
            }

        graph = StateGraph(_RunState)
        graph.add_node("dispatch_specialists", dispatch)
        graph.add_node("synthesize_result", synthesize)
        graph.add_edge(START, "dispatch_specialists")
        graph.add_edge("dispatch_specialists", "synthesize_result")
        graph.add_edge("synthesize_result", END)
        return graph.compile(checkpointer=checkpointer)

    def _from_graph_state(self, state: dict[str, Any]) -> OrchestrationResult:
        specialists = tuple(
            _restore_result(item) for item in state.get("specialists", [])
        )
        coordinator_data = state.get("coordinator")
        coordinator = (
            _restore_result(coordinator_data)
            if coordinator_data
            else AgentResult("charvi", "unavailable", error="Graph returned no coordinator result.")
        )
        return OrchestrationResult(
            status="completed" if coordinator.status == "completed" else "unavailable",
            coordinator=coordinator,
            specialists=specialists,
            routed_to=tuple(item.agent_id for item in specialists),
        )

    async def model_status(self) -> dict[str, Any]:
        """Inspect provider readiness without generating text or spending API credits."""
        return await coordinator_status(self.settings)

    def catalog(self) -> list[dict[str, Any]]:
        rows = [
            {
                "id": agent_id,
                "kind": "specialist_runtime",
                "capabilities": list(backend.capabilities),
                "configured": (
                    bool(
                        backend.settings.browser_use_enabled
                        and backend.settings.browser_use_worker_url
                        and backend.settings.browser_use_worker_token
                    )
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
            "capabilities": [
                "workflow_graph",
                "specialist_handoffs",
                "result_synthesis",
                "thread_checkpoints",
                "interrupted_run_recovery",
            ],
            "configured": self._graph is not None,
            "durable_checkpointing": self.checkpointing_enabled,
        })
        if self.settings.coordinator_provider.strip().lower() == "ollama":
            configured = bool(self.settings.ollama_base_url and self.settings.ollama_model)
        elif self.settings.coordinator_provider.strip().lower() == "openai":
            configured = bool(self.settings.openai_api_key and self.settings.openai_model)
        else:
            configured = False
        rows.append({
            "id": self.coordinator.agent_id,
            "kind": "coordinator_model",
            "provider": self.settings.coordinator_provider,
            "capabilities": list(self.coordinator.capabilities),
            "configured": configured,
        })
        return rows

    async def run(
        self,
        *,
        task: str,
        context: str = "",
        allow_code_execution: bool = False,
        allow_device_control: bool = False,
        thread_id: str | None = None,
    ) -> OrchestrationResult:
        state: _RunState = {
            "task": task,
            "context": context,
            "allow_code_execution": allow_code_execution,
            "allow_device_control": allow_device_control,
            "history": [{"role": "user", "content": task + ("\n\n" + context if context else "")}],
        }
        if self._graph is not None:
            config = {"configurable": {"thread_id": thread_id}} if thread_id else None
            result_state = await self._graph.ainvoke(state, config=config)
            return self._from_graph_state(result_state)

        specialist_results = await run_specialists(
            task=task,
            registry=self.registry,
            context=context,
            allow_code_execution=allow_code_execution,
            allow_device_control=allow_device_control,
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

    async def get_thread_history(self, *, thread_id: str) -> list[dict[str, str]]:
        """Return bounded conversation history for one already-authorized thread."""
        if self._graph is None or not self.checkpointing_enabled:
            raise RuntimeError("Durable LangGraph checkpointing is not configured.")
        snapshot = await self._graph.aget_state({
            "configurable": {"thread_id": thread_id}
        })
        if snapshot is None:
            return []
        return snapshot.values.get("history", [])

    async def resume(self, *, thread_id: str) -> OrchestrationResult | None:
        """Resume a graph with pending work from its last durable checkpoint."""
        if self._graph is None or not self.checkpointing_enabled:
            raise RuntimeError("Durable LangGraph checkpointing is not configured.")
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = await self._graph.aget_state(config)
        if snapshot is None or not snapshot.next:
            return None
        result_state = await self._graph.ainvoke(None, config=config)
        return self._from_graph_state(result_state)
