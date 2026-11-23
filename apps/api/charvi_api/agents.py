"""Unified agent and model adapters for Charvi."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    hermes_base_url: str = ""
    hermes_api_token: str = ""
    hermes_model: str = "hermes"
    openclaw_base_url: str = ""
    openclaw_api_token: str = ""
    openclaw_model: str = "openclaw/default"
    openhands_base_url: str = ""
    openhands_api_token: str = ""
    openhands_model: str = ""
    browser_use_base_url: str = ""
    browser_use_api_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@dataclass(frozen=True, slots=True)
class AgentResult:
    agent_id: str
    status: str
    output: str | None = None
    error: str | None = None


class AgentBackend(Protocol):
    agent_id: str
    capabilities: tuple[str, ...]

    async def invoke(self, *, task: str, context: str) -> AgentResult: ...


class OpenAICompatibleBackend:
    """Adapter for Hermes, OpenClaw and compatible specialist gateways."""

    def __init__(self, *, agent_id: str, base_url: str, api_token: str = "",
                 model: str, capabilities: tuple[str, ...], timeout_seconds: float = 90.0):
        self.agent_id = agent_id
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.model = model
        self.capabilities = capabilities
        self.timeout_seconds = timeout_seconds

    async def invoke(self, *, task: str, context: str) -> AgentResult:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": (
                    "You are a specialist worker for Charvi. Return analysis, plans or drafts only. "
                    "Do not claim external actions were performed. Never request or expose secrets."
                )},
                {"role": "user", "content": f"Task:\n{task}\n\nContext:\n{context}"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=body
                )
                response.raise_for_status()
                data = response.json()
            output = data["choices"][0]["message"]["content"]
            if not isinstance(output, str) or not output.strip():
                return AgentResult(self.agent_id, "failed", error="Agent returned empty content.")
            return AgentResult(self.agent_id, "completed", output=output)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            return AgentResult(self.agent_id, "unavailable",
                               error=f"{type(exc).__name__}: specialist request failed.")


class OpenAIResponsesBackend:
    """OpenAI Responses API adapter used as Charvi's coordinator model."""

    agent_id = "openai"
    capabilities = ("reasoning", "planning", "writing", "coding", "analysis")

    def __init__(self, settings: AgentSettings | None = None):
        self.settings = settings or AgentSettings()

    async def invoke(self, *, task: str, context: str) -> AgentResult:
        if not self.settings.openai_api_key or not self.settings.openai_model:
            return AgentResult(self.agent_id, "not_configured",
                               error="OpenAI model is not configured.")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
                response = await client.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/responses",
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.settings.openai_model,
                        "instructions": (
                            "You are Charvi's coordinating intelligence. Synthesize specialist "
                            "results, identify uncertainty, and never claim an action was executed "
                            "unless evidence says so."
                        ),
                        "input": f"User request:\n{task}\n\nSpecialist results and context:\n{context}",
                        "store": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
            output = data.get("output_text")
            if not output:
                chunks = []
                for item in data.get("output", []):
                    for part in item.get("content", []):
                        if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                            chunks.append(part["text"])
                output = "\n".join(chunks)
            if not isinstance(output, str) or not output.strip():
                return AgentResult(self.agent_id, "failed", error="OpenAI returned no text output.")
            return AgentResult(self.agent_id, "completed", output=output)
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return AgentResult(self.agent_id, "unavailable",
                               error=f"{type(exc).__name__}: OpenAI request failed.")


def build_agent_registry(settings: AgentSettings | None = None) -> dict[str, AgentBackend]:
    settings = settings or AgentSettings()
    registry: dict[str, AgentBackend] = {}
    if settings.hermes_base_url:
        registry["hermes"] = OpenAICompatibleBackend(
            agent_id="hermes", base_url=settings.hermes_base_url,
            api_token=settings.hermes_api_token, model=settings.hermes_model,
            capabilities=("general", "research", "planning", "automation"),
        )
    if settings.openclaw_base_url:
        registry["openclaw"] = OpenAICompatibleBackend(
            agent_id="openclaw", base_url=settings.openclaw_base_url,
            api_token=settings.openclaw_api_token, model=settings.openclaw_model,
            capabilities=("browser", "device", "automation", "general"),
        )
    if settings.openhands_base_url:
        registry["openhands"] = OpenAICompatibleBackend(
            agent_id="openhands", base_url=settings.openhands_base_url,
            api_token=settings.openhands_api_token, model=settings.openhands_model or "default",
            capabilities=("coding", "debugging", "testing"),
        )
    if settings.browser_use_base_url:
        registry["browser_use"] = OpenAICompatibleBackend(
            agent_id="browser_use", base_url=settings.browser_use_base_url,
            api_token=settings.browser_use_api_token, model="default",
            capabilities=("browser", "research"),
        )
    return registry


def route_specialists(task: str, registry: dict[str, AgentBackend]) -> list[str]:
    prompt = task.casefold()
    wanted = []
    if any(word in prompt for word in ("build", "code", "debug", "app", "software", "test")):
        wanted.append("coding")
    if any(word in prompt for word in ("browser", "website", "navigate", "book", "web page")):
        wanted.append("browser")
    if any(word in prompt for word in ("research", "compare", "analyse", "analyze", "latest", "find")):
        wanted.append("research")
    if any(word in prompt for word in ("automate", "schedule", "workflow", "repeat")):
        wanted.append("automation")
    if not wanted:
        wanted.append("general")
    selected = []
    for capability in wanted:
        candidates = [
            agent_id for agent_id, backend in registry.items()
            if capability in backend.capabilities
        ]
        if candidates:
            selected.append(candidates[0])
    if not selected and registry:
        selected.append(next(iter(registry)))
    return list(dict.fromkeys(selected))


async def run_specialists(*, task: str, registry: dict[str, AgentBackend],
                          context: str = "") -> list[AgentResult]:
    selected = route_specialists(task, registry)
    if not selected:
        return []
    results = await asyncio.gather(
        *(registry[agent_id].invoke(task=task, context=context) for agent_id in selected)
    )
    return list(results)
