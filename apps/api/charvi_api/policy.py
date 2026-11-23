from dataclasses import dataclass
from enum import StrEnum


class ActionCategory(StrEnum):
    READ = "read"
    DRAFT = "draft"
    WRITE = "write"
    EXTERNAL_MESSAGE = "external_message"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"
    DEVICE_CONTROL = "device_control"
    DEPLOYMENT = "deployment"
    CREDENTIAL_ACCESS = "credential_access"


@dataclass(frozen=True, slots=True)
class ActionRequest:
    category: ActionCategory
    target: str
    description: str
    reversible: bool = True


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed_to_start: bool
    approval_required: bool
    reason: str


_APPROVAL_REQUIRED = {
    ActionCategory.WRITE,
    ActionCategory.EXTERNAL_MESSAGE,
    ActionCategory.FINANCIAL,
    ActionCategory.DESTRUCTIVE,
    ActionCategory.DEVICE_CONTROL,
    ActionCategory.DEPLOYMENT,
    ActionCategory.CREDENTIAL_ACCESS,
}


def evaluate_action(action: ActionRequest) -> PolicyDecision:
    """Conservative first-pass policy. Production policy must also validate
    user, workspace, target scope, device capability and approval binding.
    """
    if not action.target.strip() or not action.description.strip():
        return PolicyDecision(False, True, "Missing action target or description.")

    if action.category in _APPROVAL_REQUIRED:
        return PolicyDecision(
            False,
            True,
            f"Owner approval required for {action.category.value} actions.",
        )

    if action.category in {ActionCategory.READ, ActionCategory.DRAFT}:
        return PolicyDecision(
            True,
            False,
            "Permitted as a low-impact action; enforce scope and rate limits.",
        )

    return PolicyDecision(False, True, "Unknown or unsupported action; deny by default.")
