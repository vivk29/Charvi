# Architecture decisions

## ADR-001 — Hermes is the initial assistant runtime

Hermes Agent is the first conversational/delegation runtime. It does not own authorization. Charvi's control plane remains the policy enforcement point.

## ADR-002 — Cloud control plane, laptop as worker

The cloud service stores durable task state and routes work. The laptop initiates an outbound authenticated connection and polls/streams only scoped jobs. No public inbound listener is required on the laptop.

## ADR-003 — Approval by action category and risk

Read-only research and scoped drafts can run automatically. External communications, money movement, destructive actions, production deployment, credential access and sensitive device control require explicit owner approval.

## ADR-004 — Optional integrations are isolated

OpenHands, Browser Use and n8n are specialist integrations. OpenClaw remains an optional, separately sandboxed evaluation; it is not granted blanket access to the Charvi database, secrets or worker.

## ADR-005 — Recovery is a product feature

Runs carry idempotency keys and audit events. Changes to code use Git checkpoints; files and state use encrypted snapshots. Recovery is not considered complete until a restore drill passes.
