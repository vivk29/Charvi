import time
from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .auth import UserIdentity, get_current_user
from .gateway import GatewayRequest, authorize_gateway_request
from .policy import ActionCategory, ActionRequest

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]


app = FastAPI(
    title="Charvi Control Plane",
    version="0.3.0",
    description="Policy, approvals, audit and task-routing API for Charvi.",
)


class ActionEvaluationInput(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    """Liveness endpoint; deliberately returns no infrastructure secrets."""
    return {"status": "ok", "service": "charvi-control-plane"}


@app.get("/v1/me", tags=["identity"])
async def current_identity(user: CurrentUser) -> dict[str, str | None]:
    """Return the verified Supabase Auth identity, not caller-supplied identity data."""
    return {"user_id": user.user_id, "email": user.email}


@app.post("/v1/actions/evaluate", tags=["security"])
async def evaluate_action_request(
    payload: ActionEvaluationInput,
    user: CurrentUser,
) -> dict[str, object]:
    """Authenticated dry-run policy evaluation only; never executes an action.

    Workspace ownership checks and trusted approval-store lookup are separate
    required controls before this endpoint can authorize any real execution.
    """
    request = GatewayRequest(
        workspace_id=payload.workspace_id,
        actor_id=user.user_id,
        action=ActionRequest(
            category=payload.category,
            target=payload.target,
            description=payload.description,
            reversible=payload.reversible,
        ),
        idempotency_key=payload.idempotency_key,
    )
    decision = authorize_gateway_request(request, now_epoch=int(time.time()))
    return {
        "allowed_to_execute": decision.allowed_to_execute,
        "approval_required": decision.approval_required,
        "payload_sha256": decision.payload_sha256,
        "reason": decision.reason,
        "execution_performed": False,
        "actor_id": user.user_id,
    }
