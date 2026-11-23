from fastapi import FastAPI
from pydantic import BaseModel, Field

from .gateway import GatewayRequest, authorize_gateway_request
from .policy import ActionCategory, ActionRequest

app = FastAPI(
    title="Charvi Control Plane",
    version="0.2.0",
    description="Policy, approvals, audit and task-routing API for Charvi.",
)


class ActionEvaluationInput(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Liveness endpoint; deliberately returns no infrastructure secrets."""
    return {"status": "ok", "service": "charvi-control-plane"}


@app.post("/v1/actions/evaluate", tags=["security"])
async def evaluate_action_request(payload: ActionEvaluationInput) -> dict[str, object]:
    """Dry-run policy evaluation only; this endpoint never executes an action.

    Authentication, trusted approval-store lookup and executor integration are
    intentionally not implied by this endpoint and must be added before exposure.
    """
    request = GatewayRequest(
        workspace_id=payload.workspace_id,
        actor_id=payload.actor_id,
        action=ActionRequest(
            category=payload.category,
            target=payload.target,
            description=payload.description,
            reversible=payload.reversible,
        ),
        idempotency_key=payload.idempotency_key,
    )
    decision = authorize_gateway_request(request, now_epoch=0)
    return {
        "allowed_to_execute": decision.allowed_to_execute,
        "approval_required": decision.approval_required,
        "payload_sha256": decision.payload_sha256,
        "reason": decision.reason,
        "execution_performed": False,
    }
