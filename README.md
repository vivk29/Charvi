# Charvi

Charvi is a voice-and-text personal AI operating system with a cloud control plane and an owner-connected laptop worker.

## Architecture

- **Control plane:** Python 3.12 + FastAPI. Owns authentication boundaries, policy evaluation, approvals, audit events, task routing and provider adapters.
- **Assistant runtime:** Hermes Agent, deployed as an isolated worker. Hermes is an execution runtime, not the authorization authority.
- **Data plane:** Supabase PostgreSQL/Auth. RLS protects tenant data; privileged execution writes happen through trusted backend services only.
- **Recovery:** immutable action history, idempotent runs, Git checkpoints, object-storage snapshots and tested restore procedures.
- **Specialist integrations:** OpenHands (coding), Browser Use (browser automation), n8n (workflow automation), optional OpenClaw (isolated evaluation only).
- **Devices:** cloud-first; laptop worker connects outbound over authenticated TLS and receives narrowly scoped jobs.
- **Clients:** web and mobile, with text and voice interaction.

## Non-negotiable security defaults

1. Deny by default. Every action is classified and evaluated by Charvi's policy service before execution.
2. Low-risk read/research actions may run automatically within explicit scopes.
3. External messages, financial actions, destructive changes, production deployments, credential access and sensitive device controls require owner approval.
4. Approval is bound to the exact action payload/hash, target, actor, expiry and run. Any material change requires a new approval.
5. Execution runs in isolated containers with non-root users, resource limits, restricted network egress and scoped mounts.
6. No Supabase service-role key, model key, OAuth refresh token or device secret in browser/mobile code, Git, logs or agent prompts.
7. Device pairing is explicit, revocable and capability-scoped. Never expose the laptop worker's local control port to the public internet.
8. External content is untrusted input. Prompt injection cannot grant new permissions.
9. Every execution has an idempotency key, audit trail, timeout and recovery checkpoint where applicable.
10. Backups are encrypted, access-controlled and periodically restore-tested.

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

- Supabase security hardening and recovery/control-plane tables have been applied to the connected Charvi project.
- This repository is being initialized with the control-plane security baseline.
- Hermes deployment, API service, worker pairing, backups and restore automation are **not yet deployed**.

## Local development

The first milestone will provide a minimal API health endpoint and policy primitives. Do not connect live device credentials or production accounts until the threat model, pairing flow and approval tests are complete.


## Secure action gateway (initial dry-run milestone)

The API now includes `POST /v1/actions/evaluate` and a pure decision layer that
binds an approval to the exact workspace, actor, action payload and idempotency
key. Expired, mismatched or missing approval evidence is rejected.

**Important:** this is a policy-evaluation milestone, not an execution service.
The endpoint does not execute tools or side effects. It is not ready for public
exposure until authentication, trusted server-side approval lookup, audit
persistence, rate limits and a separately sandboxed executor are integrated.
