from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from charvi_api.auth import UserIdentity, get_current_user
from charvi_api.main import app
from charvi_api.store import get_store

OWNER_ID = "00000000-0000-4000-8000-000000000001"
WORKSPACE_ID = "00000000-0000-4000-8000-000000000002"


class FakeStore:
    def __init__(self):
        self.approvals = {}
        self.events = []

    async def get_workspace(self, workspace_id: str, owner_id: str):
        if workspace_id == WORKSPACE_ID and owner_id == OWNER_ID:
            return {"id": workspace_id, "owner_id": owner_id}
        return None

    async def create_approval(self, record):
        record = {
            **record,
            "id": "00000000-0000-4000-8000-000000000010",
            "approval_nonce": "00000000-0000-4000-8000-000000000011",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending",
        }
        self.approvals[record["id"]] = record
        self.events.append({"event_type": "requested", "actor_id": OWNER_ID})
        return record

    async def list_approvals(self, workspace_id: str):
        return [a for a in self.approvals.values() if a["workspace_id"] == workspace_id]

    async def get_approval(self, approval_id: str):
        return self.approvals.get(approval_id)

    async def decide_approval(self, approval_id, *, actor_id, status, note, decided_at):
        record = self.approvals.get(approval_id)
        if not record or record["status"] != "pending":
            return None
        record.update({
            "status": status,
            "decided_by": actor_id,
            "decided_at": decided_at,
            "decision_note": note,
        })
        self.events.append({"event_type": status, "actor_id": actor_id})
        return record

    async def list_approval_events(self, approval_id: str):
        return self.events


@pytest.fixture
def client():
    fake_store = FakeStore()
    app.dependency_overrides[get_current_user] = lambda: UserIdentity(
        user_id=OWNER_ID, email="owner@example.test"
    )
    app.dependency_overrides[get_store] = lambda: fake_store
    with TestClient(app) as test_client:
        yield test_client, fake_store
    app.dependency_overrides.clear()


def test_owner_can_create_approval_for_high_impact_action(client):
    test_client, fake_store = client
    response = test_client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals",
        json={
            "category": "financial",
            "target": "vendor-payment",
            "description": "Pay the supplier invoice",
            "reversible": False,
            "idempotency_key": "invoice-2026-001",
            "title": "Supplier payment",
            "payload": {"amount": 12000, "currency": "INR"},
            "expires_in_minutes": 60,
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["requested_by_user_id"] == OWNER_ID
    assert response.json()["risk_level"] == "critical"
    assert fake_store.events[0]["actor_id"] == OWNER_ID


def test_low_impact_draft_does_not_create_approval(client):
    test_client, fake_store = client
    response = test_client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals",
        json={
            "category": "draft",
            "target": "workspace/report.md",
            "description": "Draft a report",
            "idempotency_key": "draft-001",
            "title": "Draft report",
        },
    )
    assert response.status_code == 409
    assert "does not need approval" in response.json()["detail"]
    assert fake_store.approvals == {}


def test_owner_can_approve_and_audit_decision(client):
    test_client, fake_store = client
    created = test_client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals",
        json={
            "category": "external_message",
            "target": "email:vendor@example.test",
            "description": "Send invoice reminder",
            "idempotency_key": "mail-001",
            "title": "Send invoice reminder",
        },
    )
    approval_id = created.json()["id"]
    response = test_client.post(
        f"/v1/approvals/{approval_id}/decision",
        json={"decision": "approved", "note": "Reviewed and approved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["decided_by"] == OWNER_ID
    events = test_client.get(f"/v1/approvals/{approval_id}/events")
    assert events.status_code == 200
    assert events.json()[-1]["event_type"] == "approved"
    assert events.json()[-1]["actor_id"] == OWNER_ID


def test_non_owner_cannot_create_approval(client):
    test_client, _ = client
    response = test_client.post(
        "/v1/workspaces/00000000-0000-4000-8000-000000000003/approvals",
        json={
            "category": "financial",
            "target": "bank-account",
            "description": "Transfer funds",
            "idempotency_key": "transfer-001",
            "title": "Transfer funds",
        },
    )
    assert response.status_code == 404
