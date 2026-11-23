"""Pure decision layer for Charvi's action gateway.

This module never executes actions or trusts approval claims supplied by an agent.
Approval evidence must be loaded from the trusted control-plane store in a later
integration; until then, high-impact actions remain blocked.
"""
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json

from .policy import ActionCategory, ActionRequest, PolicyDecision, evaluate_action


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    workspace_id: str
    actor_id: str
    action: ActionRequest
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Trusted approval record shape; callers must load it server-side."""

    workspace_id: str
    actor_id: str
    payload_sha256: str
    approved_by: str
    expires_at_epoch: int


@dataclass(frozen=True, slots=True)
class GatewayDecision:
    allowed_to_execute: bool
    approval_required: bool
    payload_sha256: str
    reason: str


def payload_digest(request: GatewayRequest) -> str:
    """Stable digest binds approval to the exact requested action and scope."""
    canonical = {
        "workspace_id": request.workspace_id,
        "actor_id": request.actor_id,
        "category": request.action.category.value,
        "target": request.action.target,
        "description": request.action.description,
        "reversible": request.action.reversible,
        "idempotency_key": request.idempotency_key,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def authorize_gateway_request(
    request: GatewayRequest,
    *,
    approval: ApprovalBinding | None = None,
    now_epoch: int,
) -> GatewayDecision:
    """Authorize only when policy permits and any required approval is exact.

    This is a pure function. It does not run tools, write files, send messages,
    or perform external side effects.
    """
    if not request.workspace_id.strip() or not request.actor_id.strip():
        return GatewayDecision(False, True, payload_digest(request),
                               "Workspace and actor identity are required.")
    if not request.idempotency_key.strip():
        return GatewayDecision(False, True, payload_digest(request),
                               "An idempotency key is required.")

    policy: PolicyDecision = evaluate_action(request.action)
    digest = payload_digest(request)

    if policy.allowed_to_start and not policy.approval_required:
        return GatewayDecision(True, False, digest, policy.reason)

    if approval is None:
        return GatewayDecision(False, True, digest, policy.reason)

    if approval.workspace_id != request.workspace_id:
        return GatewayDecision(False, True, digest, "Approval workspace does not match.")
    if approval.actor_id != request.actor_id:
        return GatewayDecision(False, True, digest, "Approval actor does not match.")
    if approval.payload_sha256 != digest:
        return GatewayDecision(False, True, digest, "Approval payload does not match.")
    if approval.expires_at_epoch <= now_epoch:
        return GatewayDecision(False, True, digest, "Approval has expired.")
    if not approval.approved_by.strip():
        return GatewayDecision(False, True, digest, "Approval identity is missing.")

    return GatewayDecision(True, False, digest, "Exact, unexpired approval binding accepted.")
