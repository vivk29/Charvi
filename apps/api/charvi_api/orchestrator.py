"""Charvi's single-front-door multi-agent coordinator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


class CharviOrchestrator:
    def __init__(self, settings: AgentSettings | None = None):
        self.settings = settings or AgentSettings()
        self.registry = build_agent_registry(self.settings)
        self.coordinator = OpenAIResponsesBackend(self.settings)

    def catalog(self) -> list[dict[str, Any]]:
        rows = [
            {
                "id": agent_id,
                "kind": "specialist_runtime",
                "capabilities": list(backend.capabilities),
                "configured": True,
            }
            for agent_id, backend in self.registry.items()
        ]
        rows.append({
            "id": "openai",
            "kind": "coordinator_model",
            "capabilities": list(self.coordinator.capabilities),
            "configured": bool(self.settings.openai_api_key and self.settings.openai_model),
        })
        return rows

    async def run(self, *, task: str, context: str = "") -> OrchestrationResult:
        specialist_results = await run_specialists(
            task=task, registry=self.registry, context=context
        )
        specialist_context = "\n\n".join(
            f"[{item.agent_id} — {item.status}]\n{item.output or item.error or 'No result'}"
            for item in specialist_results
        )
        combined_context = "\n\n".join(
            part for part in (context, specialist_context) if part
        )
        coordinator = await self.coordinator.invoke(task=task, context=combined_context)
        if coordinator.status != "completed":
            successful = [
                item for item in specialist_results if item.status == "completed"
            ]
            if len(successful) == 1:
                coordinator = successful[0]
            elif successful:
                coordinator = AgentResult(
                    "charvi",
                    "completed",
                    output="\n\n".join(
                        f"### {item.agent_id}\n{item.output}" for item in successful
                    ),
                )
        status = "completed" if coordinator.status == "completed" else "unavailable"
        return OrchestrationResult(
            status=status,
            coordinator=coordinator,
            specialists=tuple(specialist_results),
            routed_to=tuple(item.agent_id for item in specialist_results),
        )
