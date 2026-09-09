import pytest

from app.services import agent_skills


def test_commerce_evidence_skill_wraps_atomic_tool_with_provenance(monkeypatch) -> None:
    captured = {}

    def fake_tool(_db, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "summary": "订单已找到", "data": {"order_found": True}}

    monkeypatch.setattr(agent_skills, "execute_read_only_tool", fake_tool)
    result = agent_skills.execute_agent_skill(
        object(), action="get_order", ticket_id=7, order_id=9,
        arguments={}, policy_category="after_sales",
    )

    assert result["skill"] == "commerce_evidence"
    assert result["operation"] == "get_order"
    assert result["read_only"] is True
    assert captured["action"] == "get_order"


def test_policy_retrieval_skill_applies_scenario_category(monkeypatch) -> None:
    captured = {}

    def fake_tool(_db, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "summary": "命中规则", "data": {"sources": []}}

    monkeypatch.setattr(agent_skills, "execute_read_only_tool", fake_tool)
    result = agent_skills.execute_agent_skill(
        object(), action="search_policy", ticket_id=7, order_id=9,
        arguments={"query": "物流延迟补偿"}, policy_category="logistics",
    )

    assert result["skill"] == "policy_retrieval"
    assert captured["arguments"]["category"] == "logistics"


def test_fast_path_can_bundle_order_and_logistics_in_one_skill(monkeypatch) -> None:
    calls = []

    def fake_tool(_db, **kwargs):
        calls.append(kwargs["action"])
        data = {"order_found": True} if kwargs["action"] == "get_order" else {"latest_logistics_event": "运输中"}
        return {"ok": True, "summary": "ok", "data": data}

    monkeypatch.setattr(agent_skills, "execute_read_only_tool", fake_tool)
    result = agent_skills.execute_commerce_evidence_skill(
        object(), operations=["get_order", "analyze_delivery_timeline"], ticket_id=7, order_id=9
    )

    assert calls == ["get_order", "analyze_delivery_timeline"]
    assert result["data"] == {"order_found": True, "latest_logistics_event": "运输中"}
    assert result["operations"] == ["get_order", "analyze_delivery_timeline"]


def test_unregistered_action_cannot_bypass_skill_registry() -> None:
    with pytest.raises(ValueError, match="registered Skill"):
        agent_skills.skill_for_action("execute_refund")
