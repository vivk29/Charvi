# Charvi Agent Integration

Charvi exposes one assistant surface and delegates work to configured specialist runtimes.

## Connected runtime design

- OpenAI Responses API: coordinating model; synthesizes specialist output into Charvi's final response.
- Hermes Agent: general-purpose assistant, research and automation specialist through its OpenAI-compatible API server.
- OpenClaw Gateway: browser, device and automation specialist through its OpenAI-compatible HTTP endpoint.
- OpenHands: optional coding specialist endpoint. A deployment-specific adapter is required; setting a URL alone does not install or start OpenHands.
- Browser Use: optional browser specialist endpoint. Deploy and secure the service before configuring its URL.

Hermes and OpenClaw expose compatible chat-completions endpoints. Charvi uses a shared adapter for those runtimes and the OpenAI Responses API for its coordinator.

## Environment

Copy .env.example into a private .env file and set endpoints and credentials. Do not commit real values. Use private service networking or authenticated TLS; do not expose Hermes or OpenClaw gateways publicly without hardened ingress.

## API

- GET /v1/agents reports configured adapters and capabilities without returning credentials.
- POST /v1/agent-runs routes a user request to a specialist and optionally synthesizes the result with OpenAI.

Example request body:
{
  "workspace_id": "YOUR_WORKSPACE_UUID",
  "task": "Research the latest GST changes and prepare a short summary"
}

## Security boundary

Specialist runtimes are untrusted workers. They receive only the task and context explicitly passed to them. They do not receive Supabase service credentials, owner tokens, or permission to execute side effects through this integration. Any real-world action must return through Charvi's own policy and execution gateway. This integration produces plans, analysis and drafts; it is not an autonomous browser, shell, payment or device execution service.

## Important status

Adapters and routing code are in the repository. They are not live until each runtime is deployed, reachable over a private authenticated network, and configured with credentials. OpenAI also needs an API key and a model enabled for the API project.
