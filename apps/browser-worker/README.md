# Charvi Browser Worker

This is a separate, least-privilege service for the Browser Use open-source SDK.

## Isolation requirements

- Do not pass Supabase, GitHub, OpenAI coordinator or other Charvi control-plane secrets to this service.
- Pass only `CHARVI_BROWSER_WORKER_TOKEN`, `BROWSER_USE_API_KEY`, `BROWSER_USE_MODEL` and its timeout.
- Do not mount the API container filesystem, source repository, home directory, browser profiles or host sockets.
- Run as the non-root `browserworker` user with a read-only root filesystem, temporary storage, CPU/memory/PID limits and outbound network restrictions.
- Do not attach authenticated personal browser profiles. This worker is for public, read-only research.
- Browser Use and its browser harness need a compatible browser runtime in the image. Validate the deployment with the official Browser Use `--doctor` workflow before enabling the worker.

The task filter and system prompt are defence-in-depth, not a complete sandbox. Browser worker enablement stays off until network/browser isolation is verified.

## Run locally

Install `requirements.txt`, set the four environment variables above, then run:

```bash
uvicorn app:app --host 127.0.0.1 --port 8090
```

The API calls `POST /v1/research` with `X-Charvi-Worker-Token`. The health endpoint is `GET /health`.
