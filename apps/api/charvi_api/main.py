import hashlib
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .agents import AgentSettings
from .auth import UserIdentity, get_current_user
from .gateway import GatewayRequest, authorize_gateway_request, payload_digest
from .orchestrator import CharviOrchestrator
from .policy import ActionCategory, ActionRequest, evaluate_action
from .store import SupabaseRestStore, get_store

CurrentUser = Annotated[UserIdentity, Depends(get_current_user)]
Store = Annotated[SupabaseRestStore, Depends(get_store)]


def get_orchestrator() -> CharviOrchestrator:
    return CharviOrchestrator(AgentSettings())


Orchestrator = Annotated[CharviOrchestrator, Depends(get_orchestrator)]

app = FastAPI(
    title="Charvi Control Plane",
    version="0.4.0",
    description="Identity, workspace, policy, approvals, audit and task-routing API for Charvi.",
)


class ActionEvaluationInput(BaseModel):
    workspace_id: UUID
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)
    payload: dict[str, object] = Field(default_factory=dict)


class ApprovalRequestInput(BaseModel):
    category: ActionCategory
    target: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=2000)
    reversible: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)
    expires_in_minutes: int = Field(default=60, ge=5, le=10080)


class AgentRunInput(BaseModel):
    workspace_id: UUID
    task: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=20000)
    approval_id: UUID | None = None


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approved", "rejected", "cancelled"]
    note: str | None = Field(default=None, max_length=2000)


def risk_for(category: ActionCategory, reversible: bool = False) -> str:
    if category == ActionCategory.WRITE and reversible:
        return "low"
    if category in {ActionCategory.FINANCIAL, ActionCategory.DESTRUCTIVE,
                    ActionCategory.CREDENTIAL_ACCESS}:
        return "critical"
    if category in {ActionCategory.EXTERNAL_MESSAGE, ActionCategory.DEVICE_CONTROL,
                    ActionCategory.DEPLOYMENT}:
        return "high"
    if category == ActionCategory.WRITE:
        return "medium"
    return "low"


async def owned_workspace(store: SupabaseRestStore, workspace_id: UUID, user: UserIdentity):
    workspace = await store.get_workspace(str(workspace_id), user.user_id)
    if workspace is None:
        # Avoid revealing whether another user's workspace exists.
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "charvi-control-plane"}


@app.get("/v1/me", tags=["identity"])
async def current_identity(user: CurrentUser) -> dict[str, str | None]:
    return {"user_id": user.user_id, "email": user.email}


@app.get("/v1/workspaces", tags=["workspaces"])
async def list_my_workspaces(user: CurrentUser, store: Store) -> list[dict[str, object]]:
    return await store.list_workspaces(user.user_id)


@app.post("/v1/actions/evaluate", tags=["security"])
async def evaluate_action_request(
    payload: ActionEvaluationInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, payload.workspace_id, user)
    request = GatewayRequest(
        workspace_id=str(payload.workspace_id),
        actor_id=user.user_id,
        action=ActionRequest(
            category=payload.category,
            target=payload.target,
            description=payload.description,
            reversible=payload.reversible,
        ),
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
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


@app.post("/v1/workspaces/{workspace_id}/approvals", tags=["approvals"], status_code=201)
async def create_approval_request(
    workspace_id: UUID,
    payload: ApprovalRequestInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    await owned_workspace(store, workspace_id, user)
    action = ActionRequest(payload.category, payload.target, payload.description, payload.reversible)
    policy = evaluate_action(action)
    if not policy.approval_required:
        raise HTTPException(
            status_code=409,
            detail="This action does not need approval under the current policy; Charvi can proceed within its configured scope.",
        )
    request = GatewayRequest(
        workspace_id=str(workspace_id),
        actor_id=user.user_id,
        action=action,
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=payload.expires_in_minutes)
    record = await store.create_approval({
        "workspace_id": str(workspace_id),
        "requested_by_user_id": user.user_id,
        "action_type": payload.category.value,
        "action_category": payload.category.value,
        "risk_level": risk_for(payload.category, payload.reversible),
        "title": payload.title,
        "description": payload.description,
        "payload": {
            **payload.payload,
            "target": payload.target,
            "description": payload.description,
            "reversible": payload.reversible,
            "idempotency_key": payload.idempotency_key,
        },
        "payload_sha256": payload_digest(request),
        "status": "pending",
        "expires_at": expires_at.isoformat(),
    })
    return record


@app.get("/v1/workspaces/{workspace_id}/approvals", tags=["approvals"])
async def list_workspace_approvals(
    workspace_id: UUID,
    user: CurrentUser,
    store: Store,
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = Query(default=None),
) -> list[dict[str, object]]:
    await owned_workspace(store, workspace_id, user)
    records = await store.list_approvals(str(workspace_id))
    return [item for item in records if status is None or item.get("status") == status]


@app.get("/v1/approvals/{approval_id}/events", tags=["approvals"])
async def list_approval_events(
    approval_id: UUID,
    user: CurrentUser,
    store: Store,
) -> list[dict[str, object]]:
    approval = await store.get_approval(str(approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    await owned_workspace(store, UUID(approval["workspace_id"]), user)
    return await store.list_approval_events(str(approval_id))


@app.post("/v1/approvals/{approval_id}/decision", tags=["approvals"])
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionInput,
    user: CurrentUser,
    store: Store,
) -> dict[str, object]:
    approval = await store.get_approval(str(approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    await owned_workspace(store, UUID(approval["workspace_id"]), user)
    if approval.get("status") != "pending":
        raise HTTPException(status_code=409, detail="This approval has already been decided.")
    expiry = approval.get("expires_at")
    if expiry and datetime.fromisoformat(expiry) <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="This approval request has expired.")
    result = await store.decide_approval(
        str(approval_id),
        actor_id=user.user_id,
        status=payload.decision,
        note=payload.note,
        decided_at=datetime.now(UTC).isoformat(),
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Approval was already decided; refresh and try again.")
    return result


@app.get("/v1/agents", tags=["agents"])
async def list_configured_agents(
    user: CurrentUser,
    orchestrator: Orchestrator,
) -> list[dict[str, object]]:
    return orchestrator.catalog()


@app.post("/v1/agent-runs", tags=["agents"])
async def run_agent_task(
    payload: AgentRunInput,
    user: CurrentUser,
    store: Store,
    orchestrator: Orchestrator,
) -> dict[str, object]:
    await owned_workspace(store, payload.workspace_id, user)
    allow_code_execution = False
    if payload.approval_id is not None:
        approval = await store.get_approval(str(payload.approval_id))
        if approval is None or approval.get("workspace_id") != str(payload.workspace_id):
            raise HTTPException(status_code=404, detail="Approval request not found.")
        if approval.get("status") != "approved":
            raise HTTPException(status_code=409, detail="OpenHands requires an approved execution request.")
        expiry = approval.get("expires_at")
        if expiry and datetime.fromisoformat(expiry) <= datetime.now(UTC):
            raise HTTPException(status_code=409, detail="Execution approval has expired.")
        approved_payload = approval.get("payload") or {}
        if approval.get("action_category") != ActionCategory.WRITE.value:
            raise HTTPException(status_code=409, detail="Approval is not a workspace-write approval.")
        if approved_payload.get("reversible") is not False:
            raise HTTPException(status_code=409, detail="OpenHands requires an explicitly non-reversible execution approval.")
        execution_digest = hashlib.sha256(
            f"{payload.task}\0{payload.context}".encode()
        ).hexdigest()
        if approved_payload.get("execution_sha256") != execution_digest:
            raise HTTPException(
                status_code=409,
                detail="Approval does not match this exact task and context. Create a new approval for the revised request.",
            )
        allow_code_execution = True

    result = await orchestrator.run(
        task=payload.task,
        context=payload.context,
        allow_code_execution=allow_code_execution,
    )
    openhands_invoked = any(
        item.agent_id == "openhands" and item.status == "completed"
        for item in result.specialists
    )
    code_execution_performed: bool | None = None if openhands_invoked else False
    return {
        "status": result.status,
        "routed_to": list(result.routed_to),
        "coordinator": {
            "agent_id": result.coordinator.agent_id,
            "status": result.coordinator.status,
            "output": result.coordinator.output,
            "error": result.coordinator.error,
        },
        "specialists": [
            {
                "agent_id": item.agent_id,
                "status": item.status,
                "output": item.output,
                "error": item.error,
                "execution_performed": item.execution_performed,
            }
            for item in result.specialists
        ],
        "openhands_runtime_invoked": openhands_invoked,
        "code_execution_possible": openhands_invoked,
        "code_execution_performed": code_execution_performed,
        "external_side_effects_performed": False,
    }
