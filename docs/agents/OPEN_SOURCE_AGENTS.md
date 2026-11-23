# Open-source agent selection for Charvi

Updated: 2026-11-23

## Implement now

1. **LangGraph** — central orchestration graph. Use it for explicit, inspectable task stages, retries/checkpoints and human approval handoffs. It should not be treated as a worker with unrestricted tools.
2. **OpenHands Software Agent SDK / Agent Server** — coding worker for repository changes, debugging and tests. Run its Agent Server in an ephemeral Docker/Kubernetes workspace. Charvi calls its OpenAI-compatible Agent Server API; it does not run OpenHands code inside the FastAPI process.
3. **Browser Use** — browser research worker using the open-source Python SDK. Keep it read-only by default and isolate browser profiles, downloads and network access. Do not enable transactions or form submission through this adapter.
4. **Hermes Agent** — general-purpose assistant runtime, accessed through its API.
5. **OpenClaw** — optional separate device/automation runtime. Do not merge its tool permissions with Browser Use or OpenHands.

## Add later only when a concrete use case exists

- **n8n** — workflow automation engine, not a general reasoning agent. Add a webhook adapter after Charvi's approval gateway can bind approvals to the exact workflow ID and input payload.
- **LlamaIndex or Haystack** — document retrieval/RAG layer for private files and knowledge bases. Choose one after the memory/document ingestion requirements are defined; neither replaces LangGraph.
- **CrewAI** — role-based multi-agent collaboration. Defer because LangGraph already provides the orchestration layer; running both as competing orchestrators adds complexity.
- **smolagents** — lightweight code/tool agents. Defer because arbitrary code execution overlaps with OpenHands and needs the same sandbox boundary.
- **Mem0** — optional memory layer only if Hermes plus Charvi's own durable memory do not meet retrieval/retention needs. Do not duplicate memory stores prematurely.

## Deliberately not selected

Do not install every framework. Multiple orchestration engines create duplicated retries, tracing, state and permission boundaries. AutoGen should not be selected for a new build without a fresh maintenance review. Each additional runtime increases patching, attack surface, hosting cost and operational complexity.

## Deployment gates

- All agents run as separate least-privilege services or isolated workers.
- OpenHands gets ephemeral workspaces, non-root containers, resource limits, restricted mounts and network egress controls.
- Browser Use gets isolated browser profiles, download restrictions and domain/network policy.
- Secrets are injected at runtime, never stored in prompts, logs or the public GitHub repository.
- All external side effects route through Charvi's backend policy service.
- Every agent run records task digest, agent ID/version, model, start/end status, output references, tool events and approval references.
