from charvi_api.policy import ActionCategory, ActionRequest, evaluate_action


def test_read_action_can_start_without_approval() -> None:
    decision = evaluate_action(
        ActionRequest(ActionCategory.READ, "public-web", "Research public docs")
    )
    assert decision.allowed_to_start is True
    assert decision.approval_required is False


def test_financial_action_requires_owner_approval() -> None:
    decision = evaluate_action(
        ActionRequest(ActionCategory.FINANCIAL, "bank-transfer", "Transfer funds")
    )
    assert decision.allowed_to_start is False
    assert decision.approval_required is True


def test_missing_target_is_denied() -> None:
    decision = evaluate_action(ActionRequest(ActionCategory.READ, " ", "Search"))
    assert decision.allowed_to_start is False


def test_device_control_requires_approval_by_default() -> None:
    decision = evaluate_action(
        ActionRequest(ActionCategory.DEVICE_CONTROL, "front-door-lock", "Unlock")
    )
    assert decision.allowed_to_start is False
    assert decision.approval_required is True
