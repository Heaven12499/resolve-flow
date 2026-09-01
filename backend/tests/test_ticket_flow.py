from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["ai_provider"] == "rules"


def test_logistics_ticket_can_be_processed_end_to_end() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "我的快递三天了还没到，现在到哪里了？",
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["status"] == "new"
        assert created["messages"][0]["sender_type"] == "customer"

        process_response = client.post(f"/api/tickets/{created['id']}/process")
        assert process_response.status_code == 200
        processed = process_response.json()
        assert processed["intent"] == "logistics_query"
        assert processed["risk_level"] == "low"
        assert processed["status"] == "resolved"
        assert processed["messages"][-1]["sender_type"] == "assistant"
        assert "上海转运中心" in processed["messages"][-1]["content"]
        assert processed["audit_logs"][-1]["action"] == "query_logistics"
        assert [run["agent_name"] for run in processed["agent_runs"]] == [
            "dispatcher", "order_logistics", "knowledge", "risk_control", "reply",
        ]
        assert all(run["status"] == "completed" for run in processed["agent_runs"])


def test_unknown_intent_is_escalated() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "我想修改订单的收货地址",
            },
        )
        ticket_id = create_response.json()["id"]

        process_response = client.post(f"/api/tickets/{ticket_id}/process")
        processed = process_response.json()
        assert processed["intent"] == "other"
        assert processed["status"] == "escalated"


def test_high_risk_refund_is_escalated_without_automatic_refund() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "耳机质量有问题，我要求全额退款。",
            },
        )
        ticket_id = create_response.json()["id"]

        process_response = client.post(f"/api/tickets/{ticket_id}/process")
        processed = process_response.json()
        assert processed["intent"] == "refund_risk_review"
        assert processed["priority"] == "high"
        assert processed["risk_level"] == "high"
        assert processed["status"] == "escalated"
        assert processed["approval_tasks"][0]["task_type"] == "refund_review"
        assert "禁止AI直接执行退款" in processed["approval_tasks"][0]["proposed_data"]["reason"]
        assert processed["agent_runs"][3]["agent_name"] == "risk_control"


def test_coupon_compensation_requires_approval_then_resolves() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "快递晚了三天，能赔偿我吗？",
            },
        )
        ticket_id = create_response.json()["id"]

        process_response = client.post(f"/api/tickets/{ticket_id}/process")
        pending = process_response.json()
        assert pending["intent"] == "delivery_delay_compensation"
        assert pending["status"] == "pending_approval"
        assert pending["approval_tasks"][0]["status"] == "pending"
        assert pending["approval_tasks"][0]["proposed_data"]["coupon_amount"] == 5

        approve_response = client.post(f"/api/tickets/{ticket_id}/approve-coupon")
        approved = approve_response.json()
        assert approved["status"] == "resolved"
        assert approved["approval_tasks"][0]["status"] == "approved"
        assert "券码：RF5-" in approved["messages"][-1]["content"]
        assert approved["audit_logs"][-1]["action"] == "approve_coupon_compensation"
