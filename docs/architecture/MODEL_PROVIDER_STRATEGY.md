# Charvi model-provider strategy

## Decision

LangGraph is Charvi's workflow orchestrator. It is not an LLM and does not replace a model provider. Specialist runtimes (OpenHands, Browser Use, Hermes and optional OpenClaw) are separate from the coordinator model.

Charvi's default coordinator provider is **Ollama**, using its OpenAI-compatible /v1/chat/completions endpoint. This lets the owner run an open-weight model locally without a Claude Pro, Gemini Advanced or ChatGPT subscription. The existing OpenAI Responses adapter remains optional and is selected only when CHARVI_COORDINATOR_PROVIDER=openai.

## Initial local setup

1. Install Ollama on the laptop/host: https://ollama.com/download
2. Pull a model supported by the machine's memory and compute. A small quantized model is a sensible starting point; choose the exact model after checking RAM/VRAM.
3. Start Ollama and confirm its local API is available at http://localhost:11434.
4. Configure the Charvi API environment:
   - CHARVI_COORDINATOR_PROVIDER=ollama
   - OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 when the API runs in Docker and Ollama runs on the host
   - OLLAMA_MODEL=<the exact model tag pulled in Ollama>
5. Restart the API and inspect GET /v1/agents. The provider catalog reports configuration, not a live connectivity guarantee.

On Linux, Docker may need an explicit host-gateway mapping (provided in the Compose API service) and Ollama must listen on an interface reachable from the Docker bridge. Restrict host firewall access to the local Docker network; do not expose port 11434 publicly. On Windows/macOS Docker Desktop, host.docker.internal is normally available.

## Provider policy

- Ollama is the default and preferred no-subscription path.
- OpenAI is optional and uses a separately billed API key; a ChatGPT subscription does not include API credits.
- Claude and Gemini are not dependencies. Add another provider only if a concrete capability or reliability gap justifies it.
- A provider being configured does not mean it is reachable, and a successful model response does not grant permission to execute tools.
- The Charvi policy/control plane remains the authority for approvals, credentials, device access and external side effects.

## Hardware and cost

Local inference has no per-token provider bill, but it consumes laptop resources and electricity. Model size, quantization, context length and response speed depend on RAM/VRAM and CPU/GPU. Do not assume a particular model will run well until the machine specifications are known.
