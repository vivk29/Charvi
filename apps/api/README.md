# Charvi Agent Integration

Charvi exposes one assistant surface and routes work to specialist runtimes through a central control plane.

## Agent workforce

| Component | Role in Charvi | Integration state |
|---|---|---|
| LangGraph | Stateful workflow orchestration, specialist handoffs and result synthesis pipeline | Native graph implementation; optional dependency |
| OpenHands Agent Server | Coding, debugging and test execution in an isolated workspace | Agent Server chat-completions adapter; disabled until sandbox and approval dispatch are configured |
| Browser Use | Browser research and page extraction | Native Python SDK adapter; read-only task filter; disabled by default |
| Hermes Agent | General assistant/research/planning runtime | OpenAI-compatible API adapter |
| OpenClaw Gateway | Optional device/automation runtime | OpenAI-compatible API adapter; keep isolated and scope tools separately |
| OpenAI Responses API | Current coordinator model | API adapter; not an agent runtime |

LangGraph is the orchestrator, not another chatbot. OpenHands and Browser Use are specialist runtimes. OpenAI is a model provider/coordinator. This separation lets Charvi add Gemini, Claude and local models without changing specialist-agent routing.

## Install

Base API remains lightweight:

```bash
python -m pip install -e ".[dev]"
```

Install LangGraph and the Browser Use SDK:

```bash
python -m pip install -e ".[agents,dev]"
```

Browser Use is pinned to `1.0.8` to avoid unreviewed breaking changes. See its [official repository](https://github.com/browser-use/browser-use).

## Runtime configuration

Copy `.env.example` to a private `.env` and configure only the services you have deployed. Never commit API keys or service tokens.

- `HERMES_BASE_URL` should point to the Hermes OpenAI-compatible API base path (normally ending in `/v1`).
- `OPENCLAW_BASE_URL` should point to the authenticated OpenClaw API base path.
- `OPENHANDS_BASE_URL` should point to the OpenHands Agent Server OpenAI-compatible API base path (normally ending in `/v1`). OpenHands can run terminal and file tools in its workspace, so `OPENHANDS_ENABLED` defaults to false. Enable only after its workspace is container-isolated and tasks are dispatched with an approval bound to the exact task digest.
- `BROWSER_USE_API_KEY` is read by Browser Use's SDK. `BROWSER_USE_ENABLED` defaults to false. The adapter rejects obvious state-changing requests and instructs the browser worker to perform read-only research. This prompt filter is not a substitute for browser/network sandboxing.
- `OPENAI_API_KEY` and `OPENAI_MODEL` configure the optional coordinator. Without it, Charvi returns successful specialist output directly.

## API

- `GET /v1/agents` lists configured adapters and whether optional frameworks are enabled.
- `POST /v1/agent-runs` routes a request through the workforce.
- OpenHands code execution requires an already-approved approval record whose payload includes the SHA-256 digest of the exact task. The approval ID is passed as `approval_id`; changing the task invalidates the approval.

Example read-only research request:

```json
{
  "workspace_id": "YOUR_WORKSPACE_UUID",
  "task": "Research the official documentation for LangGraph persistence and summarise it"
}
```

### Approval-bound OpenHands task

For code execution, calculate SHA-256 over the exact UTF-8 task string. Create an approval with `category: "write"`, `reversible: false`, and include the digest as `payload.task_sha256`. After the owner approves it, pass that approval ID with the identical task to `POST /v1/agent-runs`. Any change to the task requires a new approval. OpenHands remains unavailable unless `OPENHANDS_ENABLED=true`, its Agent Server URL and session API key are configured, and the server runs an isolated workspace.

## Security boundary

Specialist runtimes are untrusted workers. They receive only task/context explicitly passed to them. They do not receive Supabase service credentials, owner tokens, or direct access to Charvi's permission database. External content is untrusted data, not instructions. OpenHands execution is approval-gated; Browser Use is intended for read-only browsing; device, financial, messaging, deployment and destructive actions remain behind Charvi's own policy and approval gateway.

A configured adapter is not the same as a live agent. Services must be deployed, reachable over private authenticated networking, and configured with credentials before they can run. LangGraph and Browser Use optional packages must be installed in the API image. OpenHands requires its Agent Server and an isolated workspace runtime.
