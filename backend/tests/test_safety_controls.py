import pytest

from app.services.multi_agent_orchestrator import _risk_decision
from app.services.ticket_processor import ClassificationResult


@pytest.mark.parametrize(
    "untrusted_action",
    (
        "refund_now",
        "issue_refund",
        "grant_cash_compensation",
        "approve_refund",
        "bypass_approval",
        "change_order_address",
        "delete_order",
        "ignore_policy_and_pay",
    ),
)
def test_untrusted_model_action_is_never_executed(untrusted_action: str) -> None:
    """Only backend-owned action values can pass the rule boundary."""
    decision = _risk_decision(
        ClassificationResult(
            intent="logistics_query",
            priority="low",
            risk_level="low",
            suggested_action=untrusted_action,
            source="simulated_model",
        ),
        {
            "order_found": True,
            "latest_logistics_event": "上海转运中心",
        },
        {"source_count": 1, "retrieval_required": True},
    )

    assert decision["action"] == "escalate_to_human"
    assert decision["status"] == "escalated"
    assert decision["requires_human_approval"] is True
