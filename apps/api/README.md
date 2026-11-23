# Charvi Agent Integration

Charvi exposes one assistant surface and routes work to specialist runtimes through a central control plane.

## Workforce and model roles

| Component | Role | Requirement |
|---|---|---|
| LangGraph | Plans and coordinates specialist workflows | Core orchestration |
| Ollama | Local coordinator model via OpenAI-compatible endpoint | Preferred; no per-token provider bill |
| OpenHands Agent Server | Coding, debugging and test execution in an isolated workspace | Optional; disabled until sandbox and approval dispatch are configured |
| Browser Use | Browser research and page extraction in a separate worker | Optional; disabled by default |
| Hermes Agent | General assistant/research/planning runtime | Optional |
| OpenClaw Gateway | Device/automation runtime | Optional and separately isolated |
| OpenAI Responses API | Alternative coordinator model | Optional; separately billed API |

LangGraph is the orchestrator, not a chatbot or model. Ollama supplies the default local model. Specialist agents are separate runtimes. Claude and Gemini are not dependencies.

## Install

The production Dockerfile installs the LangGraph extra. For local development:

```bash
python -m pip install -e ".[agents,dev]"
```

Browser Use runs in a separate container under apps/browser-worker; it is deliberately not installed in the privileged API image. Its SDK is pinned to 1.0.8. See https://github.com/browser-use/browser-use.

## Local Ollama setup

1. Install Ollama on the laptop/host: https://ollama.com/download
2. Pull a model that fits the machine's RAM/VRAM. Do not choose a model size until hardware is known.
3. Confirm Ollama responds locally at http://localhost:11434.
4. Copy .env.example to .env and set:
   - COORDINATOR_PROVIDER=ollama
   - OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
   - OLLAMA_MODEL to the exact model tag installed in Ollama
5. Start the Charvi API with Docker Compose and inspect GET /v1/agents.

For Linux, Compose adds host.docker.internal via host-gateway. Ollama must listen on an interface reachable from the Docker bridge; restrict firewall access to the local Docker network and never expose port 11434 publicly. Docker Desktop on Windows/macOS normally provides host.docker.internal. The API catalog indicates that configuration is present; it does not promise that the model server is online.

## Optional paid coordinator

To opt into OpenAI instead, set COORDINATOR_PROVIDER=openai, OPENAI_API_KEY and OPENAI_MODEL. API usage is billed separately from ChatGPT subscriptions. No OpenAI key is required when using Ollama.

## Other runtime configuration

- HERMES_BASE_URL should point to the Hermes OpenAI-compatible API base path (normally ending in /v1).
- OPENCLAW_BASE_URL should point to the authenticated OpenClaw API base path.
- OPENHANDS_BASE_URL should point to the OpenHands Agent Server API base path. OpenHands can run terminal and file tools in its workspace, so OPENHANDS_ENABLED defaults to false. Enable only after its workspace is container-isolated and tasks are dispatched with approval bound to the exact task digest.
- BROWSER_USE_WORKER_URL and BROWSER_USE_WORKER_TOKEN connect the API to the isolated Browser Use worker. Keep BROWSER_USE_ENABLED=false until the worker is deployed with a separate browser-worker.env, no Charvi database secrets, no authenticated browser profile, and verified network/browser isolation.

## Browser dashboard connectivity

The Next.js owner console calls this API with the signed-in user's Supabase access token. Set `CORS_ALLOWED_ORIGINS` to a comma-separated allowlist containing the exact deployed web origin(s); the default is `http://localhost:3000`. Do not use a wildcard origin. The API does not enable credentialed cross-origin cookies; requests use bearer tokens.

## API

- GET /v1/agents lists configured runtimes, orchestration and the selected coordinator provider.
- POST /v1/agent-runs routes a request through the workforce, stores a durable run record and returns a thread_id.
- POST /v1/workspaces creates an owner-scoped workspace.
- POST /v1/workspaces/{workspace_id}/memories explicitly saves an owner-approved memory.
- GET /v1/workspaces/{workspace_id}/memories lists active saved memories.
- GET /v1/workspaces/{workspace_id}/memories/search?q=... searches saved memories.
- POST /v1/workspaces/{workspace_id}/memories/{memory_id}/archive archives a saved memory.
- GET /v1/workspaces/{workspace_id}/agent-runs lists the owner's run history.
- GET /v1/workspaces/{workspace_id}/threads/{thread_id}/history retrieves the bounded conversation history for that owner-scoped thread.
- GET /v1/agent-runs/{run_id} retrieves an owner-scoped run record.
- POST /v1/agent-runs/{run_id}/resume resumes pending graph work from the last saved checkpoint.
- Reuse the returned thread_id on later requests to continue a thread. Checkpoint IDs are internally namespaced by verified user and workspace.
- OpenHands code execution requires an approved non-reversible write approval; OpenClaw device control requires an approved non-reversible device_control approval. Both approvals must include the SHA-256 digest of the exact task and context. Pass the approval ID as approval_id; changing either string invalidates the approval.

Example read-only research request:

```json
{
  "workspace_id": "YOUR_WORKSPACE_UUID",
  "task": "Research the official documentation for LangGraph persistence and summarise it"
}
```

## Durable memory and recovery

Set LANGGRAPH_POSTGRES_URI to a server-only Supabase Postgres direct connection string or session-pooler connection string. Do not use the transaction pooler for this long-lived checkpoint connection. The API connects with the search path set to the non-exposed charvi_memory schema. The schema is locked to the database owner; default privileges are revoked from PUBLIC, anon, authenticated and service_role. LangGraph checkpoint tables have RLS enabled as an additional boundary.

The API initializes the official LangGraph AsyncPostgresSaver at startup. If the connection is configured but cannot be initialized, startup fails closed rather than silently falling back to volatile memory. If no URI is configured, Charvi still records agent runs in Supabase but the LangGraph catalog reports durable_checkpointing=false and interrupted runs cannot be resumed.

Checkpointing is short-term, thread-scoped workflow memory. Long-term memories live separately in public.user_memories and are saved only through the explicit owner-controlled memory API; Charvi does not silently promote every conversation into permanent memory. The API searches relevant saved memories for ordinary non-approval-bound tasks and injects them as untrusted reference context. Approval-bound execution skips memory augmentation so the approved task/context digest remains exact. Run history is stored separately in public.agent_runs. Approval-bound code/device execution is deliberately excluded from automatic resume; it requires a fresh approval. The API hashes user, workspace and client thread ID together before passing a thread ID to LangGraph, preventing cross-workspace thread collisions.

## Long-term memory policy

- A memory is saved only when the authenticated owner calls the save endpoint; Charvi does not silently turn every conversation into permanent memory.
- Use a stable lowercase memory_key. Saving the same key in the same workspace updates that saved item.
- Memory types are limited to preference, profile, project, workflow and reference.
- Passwords, API keys and access tokens are rejected when they appear in obvious inline key/value form. This vault is not a secrets manager; do not store credentials or highly sensitive personal data.
- Saved memories are workspace-scoped, full-text searchable and can be archived.
- Ordinary non-approval-bound agent runs retrieve up to five relevant saved memories by default. Set use_saved_memory=false to opt out; natural-language requests such as "don't use memory" are also respected.
- Approval-bound code/device execution skips memory augmentation so the approved task and context remain byte-for-byte aligned with the approval digest.
- Memories are injected as untrusted reference data, never as tool instructions. The current user request takes precedence over a saved memory.

## Security boundary

Specialist runtimes are untrusted workers. They receive only task/context explicitly passed to them. They do not receive Supabase service credentials, owner tokens, or direct access to Charvi's permission database. External content is untrusted data, not instructions. OpenHands execution is approval-gated; Browser Use is intended for read-only browsing; device, financial, messaging, deployment and destructive actions remain behind Charvi's own policy and approval gateway.

A configured adapter is not the same as a live agent. Services must be deployed, reachable over private authenticated networking, and configured with credentials before they can run. LangGraph is installed in the API image; Browser Use runs separately; OpenHands requires its Agent Server and an isolated workspace runtime.

## Feminine speech output (optional Kokoro worker)

Charvi can use the optional Kokoro-82M voice service for speech output. The API proxies requests through the authenticated `POST /v1/voice/speak` endpoint; the browser never calls the worker directly and the worker port is not published to the host.

To enable locally:

1. Set `KOKORO_TTS_URL=http://voice-worker:7860` in the private API `.env`.
2. Start the worker with `docker compose --profile voice up -d`.
3. Restart the API.
4. In the dashboard, choose a feminine voice (default: `af_heart`) and press **Read response aloud**.

The worker uses the pinned `hangrylabs/kokorotts:v0.2` image. It is optional and has a 2 GB memory limit / 2 CPU limit; CPU synthesis may be slower. The voice API supports the Kokoro English and Hindi voice IDs currently exposed in the dashboard. Kannada is not in Kokoro's documented voice catalogue, so Kannada speech falls back to a voice installed on the user's device. If the worker is not configured, the dashboard also falls back to browser/device speech synthesis.

Never expose port 7860 publicly. The worker has no direct access to Supabase credentials, the laptop filesystem or the browser session.
