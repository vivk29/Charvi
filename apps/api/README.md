# Charvi API

Minimal control-plane skeleton. It intentionally has no agent execution endpoint yet.

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
PYTHONPATH=apps/api uvicorn charvi_api.main:app --reload
```

Health check: `GET http://127.0.0.1:8000/health`.

Run tests:

```bash
PYTHONPATH=apps/api pytest
```

Do not expose this development server publicly. Authentication, authorization, rate limits and deployment hardening are still pending.
