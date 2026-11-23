# Charvi

Charvi is a voice-and-text personal AI operating system with one conversational assistant coordinating specialist agents behind the scenes.

## Architecture

- **Charvi Core:** understands the owner's request, plans work, routes tasks to specialists and presents one coherent response.
- **Control plane:** Python 3.12 + FastAPI. Owns identity, workspace access, action policy, approvals, audit events and task routing.
- **Assistant runtime:** Hermes Agent, planned as an isolated runtime. Hermes is not the authorization authority.
- **Specialist agents:** OpenHands for coding, Browser Use for browser work, n8n for workflows, and additional research, finance/business and device specialists as integrations mature.
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
- GitHub Actions lint and tests passed for the workspace-ownership code milestone.

**Not yet live:** the API is not deployed or configured with a server-only Supabase service-role key; no Charvi web/mobile interface, Hermes runtime, specialist agent orchestration, actual action executor, laptop pairing, voice interface, notifications, backup automation or restore service is deployed. Approval decisions are recorded, but the approved action is not executed by this API.

## Local development

See [the API guide](apps/api/README.md) for environment variables and route documentation. Copy `.env.example` to a private local `.env` file and configure credentials there. Never commit actual credentials.

The GitHub repository is currently public. Keep secrets, personal data, production exports and private configuration out of it.


## Multi-agent integration milestone

Charvi now has a unified agent registry and orchestration API:

- OpenAI Responses API is the coordinating model adapter.
- Hermes Agent and OpenClaw connect through their OpenAI-compatible chat-completions endpoints.
- Optional OpenHands and Browser Use integrations can be connected through a secured OpenAI-compatible service bridge; these are not direct native SDK integrations yet.
- The authenticated API exposes GET /v1/agents and POST /v1/agent-runs.
- Task routing selects specialists by capability, runs selected specialists, and passes their results to OpenAI for synthesis when configured.
- Specialist responses are treated as untrusted output. They cannot directly execute privileged actions through this integration.

The integration code is committed and GitHub Actions lint and tests pass. The services are not live yet: runtime URLs, private tokens and an OpenAI API key/model must be configured in the API hosting environment. No credentials are stored in this repository.
