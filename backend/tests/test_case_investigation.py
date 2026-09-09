from types import SimpleNamespace

from app.services import case_investigation


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, content: str) -> None:
        self.content = content

    def chat(self, *_args, **_kwargs):
        return SimpleNamespace(content=self.content)


def empty_gate(step: int = 0):
    return case_investigation.evaluate_evidence(
        [],
        ticket_content="耳机有质量问题，我要退款",
        source_count=0,
        retrieval_required=False,
        customer_message_count=1,
        pending_question=None,
        step=step,
    )


def test_agent_may_choose_finish_but_evidence_gate_rejects_incomplete_work(monkeypatch) -> None:
    monkeypatch.setattr(
        case_investigation,
        "get_provider",
        lambda _name: FakeProvider('{"action":"finish","reason":"调查完成","arguments":{},"question":null}'),
    )
    gate = empty_gate()
    decision, source, fallback_reason = case_investigation.choose_case_action(
        "耳机有质量问题，我要退款", [], gate, step=0
    )

    assert decision.action == "finish"
    assert source == "fake"
    assert fallback_reason is None
    assert gate.accepted is False
    assert "order_verified" in gate.missing_slots


def test_case_manager_rejects_an_unlisted_business_action(monkeypatch) -> None:
    monkeypatch.setattr(
        case_investigation,
        "get_provider",
        lambda _name: FakeProvider('{"action":"execute_refund","reason":"直接退款","arguments":{}}'),
    )
    decision, source, fallback_reason = case_investigation.choose_case_action(
        "耳机有质量问题，我要退款", [], empty_gate(), step=0
    )

    assert decision.action == "get_order"
    assert source == "rules"
    assert fallback_reason == "fake_ValidationError"


def test_case_manager_stops_at_the_hard_step_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        case_investigation,
        "get_provider",
        lambda _name: FakeProvider('{"action":"search_policy","reason":"继续查找","arguments":{"query":"再次搜索"}}'),
    )
    gate = empty_gate(step=case_investigation.MAX_CASE_STEPS)
    decision, source, _ = case_investigation.choose_case_action(
        "耳机有质量问题，我要退款",
        [],
        gate,
        step=case_investigation.MAX_CASE_STEPS,
    )

    assert decision.action == "finish"
    assert source == "rules"
    assert "预算" in decision.reason


def test_delivery_agent_uses_scenario_specific_evidence_gate() -> None:
    history = [
        {"action": "get_order", "ok": True, "data": {}},
        {"action": "get_ticket_messages", "ok": True, "data": {"customer_message_count": 1}},
        {
            "action": "analyze_delivery_timeline",
            "ok": True,
            "data": {"anomaly_type": "delivery_overdue", "is_overdue": True},
        },
        {"action": "search_policy", "ok": True, "data": {"source_count": 1}},
    ]
    gate = case_investigation.evaluate_evidence(
        history,
        ticket_content="快递晚了三天，申请补偿",
        source_count=1,
        retrieval_required=True,
        customer_message_count=1,
        pending_question=None,
        step=4,
        scenario="delivery_delay",
    )

    assert gate.accepted is True
    assert gate.disposition == "ready"
    assert "customer_evidence_present" not in gate.checks
