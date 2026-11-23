from fastapi.testclient import TestClient

from charvi_api.gateway import (
    ApprovalBinding,
    GatewayRequest,
    authorize_gateway_request,
    payload_digest,
)
from charvi_api.main import app
from charvi_api.policy import ActionCategory, ActionRequest


client = TestClient(app)


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


def test_http_evaluation_endpoint_never_executes_action() -> None:
    response = client.post(
        "/v1/actions/evaluate",
        json={
            "workspace_id": "workspace-1",
            "actor_id": "agent-1",
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
