# Charvi threat model — initial baseline

## Assets

- Owner identity and approval authority
- Supabase data and backups
- Model-provider credentials and OAuth tokens
- Laptop files, local applications and device controls
- Agent prompts, memory, task inputs and outputs
- Audit records and recovery checkpoints

## Trust boundaries

1. Owner client -> authenticated API
2. Cloud API -> Hermes and specialist agent sandboxes
3. Cloud API -> Supabase
4. Cloud API -> outbound laptop worker
5. Agent/browser -> untrusted websites, files, emails and messages
6. Agent -> external side-effecting services

## Threats and controls

| Threat | Required control |
|---|---|
| Prompt injection in external content | Treat content as data; policy engine ignores instructions that request privilege escalation |
| Stolen device token | Per-device credentials, short expiry/rotation, revocation and capability scopes |
| Agent overreach | Server-side policy decision before every tool/action |
| Approval replay or mutation | Single-use approval bound to canonical action hash, target, actor and expiry |
| Secret leakage | Secret manager, output redaction, no secrets in prompts/logs/repository |
| Cross-workspace data access | Supabase RLS plus backend authorization checks |
| Destructive failure | Checkpoints, idempotency, immutable audit events and tested restore |
| Compromised specialist agent | Separate containers, restricted mounts/network, no ambient credentials |
| Public repository exposure | Never commit credentials, private data, generated memory or local config |

## Approval semantics

Approval is not a natural-language boolean. It is a signed/recorded decision for one exact action. If the action payload, target, scope or requested permissions change, require a new decision.

## Deployment gate

Do not enable unattended actions on a real laptop or production account until:
- authentication and device pairing are tested;
- all action categories have deny-by-default tests;
- approval expiry/replay/tampering tests pass;
- sandbox escape and network egress assumptions are reviewed;
- backup restoration is demonstrated.
