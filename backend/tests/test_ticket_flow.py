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
        assert created["status"] == "resolved"
        assert created["messages"][0]["sender_type"] == "customer"

        processed = created
        assert processed["intent"] == "logistics_query"
        assert processed["risk_level"] == "low"
        assert processed["status"] == "resolved"
        assert processed["messages"][-1]["sender_type"] == "assistant"
        assert "上海转运中心" in processed["messages"][-1]["content"]
        assert processed["audit_logs"][-1]["action"] == "query_logistics"
        assert [run["agent_name"] for run in processed["agent_runs"]] == [
            "dispatcher", "order_logistics", "risk_control", "reply",
        ]
        dispatcher = processed["agent_runs"][0]["output_data"]
        assert dispatcher["route"] == "logistics_fast_path"
        assert dispatcher["skipped_agents"][0]["agent_name"] == "knowledge"
        assert all(run["status"] == "completed" for run in processed["agent_runs"])

        monitor_response = client.get("/api/agent-runs")
        assert monitor_response.status_code == 200
        assert monitor_response.json()[0]["ticket_no"] == created["ticket_no"]


def test_unknown_intent_is_escalated() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "我想修改订单的收货地址",
            },
        )
        processed = create_response.json()
        assert processed["intent"] == "other"
        assert processed["status"] == "escalated"
        assert [run["agent_name"] for run in processed["agent_runs"]] == [
            "dispatcher", "risk_control", "reply",
        ]
        assert processed["agent_runs"][0]["output_data"]["route"] == "human_handoff"


def test_high_risk_refund_is_escalated_without_automatic_refund() -> None:
    with TestClient(app) as client:
        create_response = client.post(
            "/api/tickets",
            json={
                "order_no": "RF202608290001",
                "content": "耳机质量有问题，我要求全额退款。",
            },
        )
        processed = create_response.json()
        assert processed["intent"] == "refund_risk_review"
        assert processed["priority"] == "high"
        assert processed["risk_level"] == "high"
        assert processed["status"] == "escalated"
        assert processed["approval_tasks"][0]["task_type"] == "refund_review"
        assert processed["approval_tasks"][0]["status"] == "in_review"
        assert "禁止AI直接执行退款" in processed["approval_tasks"][0]["proposed_data"]["reason"]
        assert [run["agent_name"] for run in processed["agent_runs"]] == [
            "dispatcher", "knowledge", "risk_control", "reply",
        ]
        assert processed["agent_runs"][0]["output_data"]["route"] == "high_risk_refund_review"


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
        pending = create_response.json()
        assert pending["intent"] == "delivery_delay_compensation"
        assert pending["status"] == "pending_approval"
        assert pending["approval_tasks"][0]["status"] == "pending"
        assert pending["approval_tasks"][0]["proposed_data"]["coupon_amount"] == 5
        assert [run["agent_name"] for run in pending["agent_runs"]] == [
            "dispatcher", "order_logistics", "knowledge", "risk_control", "reply",
        ]
        assert pending["agent_runs"][0]["output_data"]["route"] == "compensation_with_approval"

        approve_response = client.post(f"/api/tickets/{ticket_id}/approve-coupon")
        approved = approve_response.json()
        assert approved["status"] == "resolved"
        assert approved["approval_tasks"][0]["status"] == "approved"
        assert "券码：RF5-" in approved["messages"][-1]["content"]
        assert approved["audit_logs"][-1]["action"] == "approve_coupon_compensation"


def test_approval_workbench_can_list_reject_and_assign_tasks() -> None:
    with TestClient(app) as client:
        coupon = client.post("/api/tickets", json={"order_no": "RF202608290001", "content": "快递晚了三天，能赔偿我吗？"}).json()
        refund = client.post("/api/tickets", json={"order_no": "RF202608290001", "content": "商品质量有问题，我要退款。"}).json()
        queue = client.get("/api/approvals")
        assert queue.status_code == 200
        tasks = {item["task_type"]: item for item in queue.json()}
        assert tasks["coupon_compensation"]["ticket_no"] == coupon["ticket_no"]

        rejected = client.post(f"/api/approvals/{tasks['coupon_compensation']['id']}/reject", json={"reason": "物流延迟天数不足"})
        assert rejected.status_code == 200
        assert rejected.json()["approval_tasks"][0]["status"] == "rejected"

        assert tasks["refund_review"]["status"] == "in_review"
        assert tasks["refund_review"]["decision_data"]["assigned_to"] == "supervisor"


def test_knowledge_document_can_be_created_updated_and_disabled() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/knowledge/documents",
            json={
                "title": "售后补充规则",
                "content": "客户提交商品问题照片后，客服需要在工单中登记证据并通知主管复核。",
                "category": "after_sales",
                "version": "v1.1",
                "is_active": True,
            },
        )
        assert created.status_code == 201
        document = created.json()
        assert document["content"].startswith("客户提交")

        updated = client.patch(
            f"/api/knowledge/documents/{document['id']}",
            json={"version": "v1.2", "is_active": False},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == "v1.2"
        assert updated.json()["is_active"] is False
