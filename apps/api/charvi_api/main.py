from fastapi import FastAPI

app = FastAPI(
    title="Charvi Control Plane",
    version="0.1.0",
    description="Policy, approvals, audit and task-routing API for Charvi.",
)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Liveness endpoint; deliberately returns no infrastructure secrets."""
    return {"status": "ok", "service": "charvi-control-plane"}
