# Charvi

Charvi is a voice-and-text personal AI operating system with one conversational assistant coordinating specialist agents behind the scenes.

## Architecture

- **Charvi Core:** understands the owner's request, plans work, routes tasks to specialists and presents one coherent response.
- **Control plane:** Python 3.12 + FastAPI. Owns identity, workspace access, action policy, approvals, audit events and task routing.
- **Orchestration:** LangGraph coordinates specialist workflows; it is not itself an AI model.
- **Coordinator intelligence:** Ollama is the default local model provider. OpenAI is optional; Claude and Gemini are not required.
- **Specialist agents:** OpenHands for approval-gated coding, Browser Use in a separate read-only browser worker, Hermes for general work, and OpenClaw as an optional isolated device runtime with owner approval required for device control. n8n is a planned workflow executor.
- **Data plane:** Supabase PostgreSQL/Auth. RLS protects tenant data; privileged operations are restricted to trusted backend services.
- **Devices:** cloud-first; laptop worker connects outbound over authenticated TLS and receives narrowly scoped jobs.
- **Clients:** web and mobile, with text and voice interaction.

## Autonomy and approval defaults

Charvi should not ask for approval for every small step. Its policy is designed around risk and configured scope:

- Read, research, analysis and drafting: autonomous within authorised scopes.
- Reversible changes inside Charvi's isolated workspace: autonomous under the current starter policy.
- External messages, financial actions, destructive changes, production deployments, credential access and sensitive device controls: owner approval.
- Low-impact device actions can become autonomous only after explicit device pairing and capability configuration.

Approval is bound to the exact action payload/hash, target, actor, workspace and expiry. A changed payload requires a new approval. Approval is a gate, not proof that an action was executed.

## Non-negotiable security defaults

1. Deny by default. Every action is classified and evaluated by Charvi's policy service before execution.
2. The backend derives identity from a verified Supabase Auth token; agents cannot supply or impersonate the owner identity.
3. Workspace ownership is checked before workspace or approval access.
4. Privileged database credentials stay on the server and never enter browser/mobile code, Git, logs or agent prompts.
5. Device pairing is explicit, revocable and capability-scoped. Never expose the laptop worker's local control port to the public internet.
6. External content is untrusted input. Prompt injection cannot grant new permissions.
7. Every execution should have an idempotency key, audit trail, timeout and recovery checkpoint where applicable.
8. Backups are encrypted, access-controlled and periodically restore-tested.

## Repository layout

```
apps/
  api/                 # FastAPI control plane
  web/                 # Next.js owner console (planned)
  mobile/              # Expo client (planned)
workers/
  laptop/              # Outbound connected worker (planned)
  hermes/              # Hermes runtime configuration (planned)
integrations/
  openhands/
  browser-use/
  n8n/
  openclaw-evaluation/
infra/
  docker/
  supabase/
docs/
  architecture/
  security/
  runbooks/
```

## Current implementation status

- Supabase RLS and approval/audit schema are applied to the connected Charvi project.
- Approval records store a verified requester identity, immutable payload hash and server-generated nonce. Database triggers enforce pending-to-decision transitions and write request/decision audit events.
- The API verifies Supabase Auth access tokens and derives the actor ID from the verified identity.
- The API has owner-scoped workspace lookup, policy evaluation, approval creation/listing/decision routes and audit-event retrieval.
- The policy allows read/draft work and reversible workspace writes without creating an approval request. Higher-impact categories are gated.
- The API, agent adapters and model-provider selection are source-controlled. The latest CI run passed before this provider milestone; this milestone still requires its own CI verification.

**Not yet live:** the API and agent runtimes are not deployed or configured with server-only Supabase credentials; no Charvi web/mobile interface, Hermes/OpenClaw/OpenHands services, Browser Use worker, laptop pairing, voice interface, notifications, backup automation or restore service is deployed. LangGraph routing is implemented but durable checkpoint persistence is not wired. The Ollama adapter is committed only after this milestone's changes are merged and CI passes; Ollama itself still needs to be installed and configured on the user's machine.

## Local development

See the API guide in apps/api/README.md. Copy .env.example to a private .env file and configure credentials there. Never commit actual credentials.

The GitHub repository is currently public. Keep secrets, personal data, production exports and private configuration out of it.

## Multi-agent and local model milestone

Charvi has a unified agent registry and orchestration API:

- LangGraph coordinates specialist routing and result synthesis.
- Ollama is the default coordinator model, using its OpenAI-compatible chat-completions endpoint. It can run locally without a premium chat subscription or per-token cloud provider bill.
- OpenAI Responses API remains an explicitly selected optional provider; it is not required. Claude and Gemini are not dependencies.
- Hermes and OpenClaw use compatible API adapters. OpenHands is approval-gated. Browser Use runs in a separate read-only worker.
- The authenticated API exposes GET /v1/agents and POST /v1/agent-runs.
- Specialist responses are untrusted data and cannot grant themselves execution privileges.

See docs/architecture/MODEL_PROVIDER_STRATEGY.md for local setup. A configured adapter does not mean the model or specialist service is deployed or reachable.
