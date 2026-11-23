import pytest
from fastapi.testclient import TestClient

from charvi_api.auth import UserIdentity, get_current_user
from charvi_api.gateway import (
    ApprovalBinding,
    GatewayRequest,
    authorize_gateway_request,
    payload_digest,
)
from charvi_api.main import app
from charvi_api.policy import ActionCategory, ActionRequest
from charvi_api.store import get_store


@pytest.fixture
def client() -> TestClient:
    class WorkspaceStore:
        async def get_workspace(self, workspace_id: str, owner_id: str):
            if owner_id == "00000000-0000-4000-8000-000000000001":
                return {"id": workspace_id, "owner_id": owner_id}
            return None

    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        user_id="00000000-0000-4000-8000-000000000001",
        email="owner@example.test",
    )
    app.dependency_overrides[get_store] = WorkspaceStore
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_request(category: ActionCategory = ActionCategory.FINANCIAL) -> GatewayRequest:
    return GatewayRequest(
        workspace_id="workspace-1",
        actor_id="agent-1",
        action=ActionRequest(category, "payment-destination", "Create payment"),
        idempotency_key="task-123",
    )


def test_high_impact_action_is_blocked_without_approval() -> None:
    decision = authorize_gateway_request(make_request(), now_epoch=100)
    assert decision.allowed_to_execute is False
    assert decision.approval_required is True


def test_exact_unexpired_approval_binding_allows_policy_gated_action() -> None:
    request = make_request()
    approval = ApprovalBinding(
        approval_id="approval-1",
        approval_nonce="nonce-1",
        status="approved",
        workspace_id="workspace-1",
        actor_id="agent-1",
        payload_sha256=payload_digest(request),
        approved_by="owner-1",
        expires_at_epoch=200,
    )
    decision = authorize_gateway_request(request, approval=approval, now_epoch=100)
    assert decision.allowed_to_execute is True
    assert decision.approval_required is False


def test_changed_payload_invalidates_approval() -> None:
    request = make_request()
    approval = ApprovalBinding(
        approval_id="approval-payload",
        approval_nonce="nonce-payload",
        status="approved",
        workspace_id="workspace-1",
        actor_id="agent-1",
        payload_sha256=payload_digest(request),
        approved_by="owner-1",
        expires_at_epoch=200,
    )
    changed = GatewayRequest(
        workspace_id=request.workspace_id,
        actor_id=request.actor_id,
        action=ActionRequest(ActionCategory.FINANCIAL, "different-destination", "Create payment"),
        idempotency_key=request.idempotency_key,
    )
    decision = authorize_gateway_request(changed, approval=approval, now_epoch=100)
    assert decision.allowed_to_execute is False
    assert "payload" in decision.reason


def test_wrong_workspace_invalidates_approval() -> None:
    request = make_request()
    approval = ApprovalBinding(
        approval_id="approval-2",
        approval_nonce="nonce-2",
        status="approved",
        workspace_id="other-workspace",
        actor_id="agent-1",
        payload_sha256=payload_digest(request),
        approved_by="owner-1",
        expires_at_epoch=200,
    )
    decision = authorize_gateway_request(request, approval=approval, now_epoch=100)
    assert decision.allowed_to_execute is False


def test_expired_approval_is_rejected() -> None:
    request = make_request()
    approval = ApprovalBinding(
        approval_id="approval-3",
        approval_nonce="nonce-3",
        status="approved",
        workspace_id="workspace-1",
        actor_id="agent-1",
        payload_sha256=payload_digest(request),
        approved_by="owner-1",
        expires_at_epoch=100,
    )
    decision = authorize_gateway_request(request, approval=approval, now_epoch=100)
    assert decision.allowed_to_execute is False


def test_low_risk_read_can_be_evaluated_without_approval() -> None:
    decision = authorize_gateway_request(make_request(ActionCategory.READ), now_epoch=100)
    assert decision.allowed_to_execute is True
    assert decision.approval_required is False


def test_reversible_workspace_write_does_not_need_approval() -> None:
    decision = authorize_gateway_request(make_request(ActionCategory.WRITE), now_epoch=100)
    assert decision.allowed_to_execute is True
    assert decision.approval_required is False


def test_http_evaluation_endpoint_checks_workspace_and_never_executes_action(client: TestClient) -> None:
    response = client.post(
        "/v1/actions/evaluate",
        json={
            "workspace_id": "00000000-0000-4000-8000-000000000002",
            "category": "financial",
            "target": "payment-destination",
            "description": "Create payment",
            "reversible": False,
            "idempotency_key": "task-123",
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed_to_execute"] is False
    assert response.json()["approval_required"] is True
    assert response.json()["execution_performed"] is False
    assert response.json()["actor_id"] == "00000000-0000-4000-8000-000000000001"


def test_workspace_evaluation_rejects_other_users_workspace(client: TestClient) -> None:
    response = client.post(
        "/v1/actions/evaluate",
        json={
            "workspace_id": "00000000-0000-4000-8000-000000000003",
            "category": "read",
            "target": "notes",
            "description": "Read notes",
            "idempotency_key": "task-124",
        },
    )
    assert response.status_code == 404


def test_pending_database_approval_is_not_execution_authority() -> None:
    request = make_request()
    approval = ApprovalBinding(
        approval_id="approval-pending",
        approval_nonce="nonce-pending",
        status="pending",
        workspace_id="workspace-1",
        actor_id="agent-1",
        payload_sha256=payload_digest(request),
        approved_by="owner-1",
        expires_at_epoch=200,
    )
    decision = authorize_gateway_request(request, approval=approval, now_epoch=100)
    assert decision.allowed_to_execute is False
    assert "approved state" in decision.reason
