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
        assert created["status"] == "queued"
        assert created["messages"][0]["sender_type"] == "customer"

        processed = client.get(f"/api/tickets/{created['id']}").json()
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
        queued = create_response.json()
        assert queued["status"] == "queued"
        processed = client.get(f"/api/tickets/{queued['id']}").json()
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
        queued = create_response.json()
        assert queued["status"] == "queued"
        processed = client.get(f"/api/tickets/{queued['id']}").json()
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
        knowledge_run = next(run for run in processed["agent_runs"] if run["agent_name"] == "knowledge")
        assert knowledge_run["input_data"]["category"] == "after_sales"
        assert all(source["category"] == "after_sales" for source in knowledge_run["output_data"]["sources"])


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
        assert create_response.json()["status"] == "queued"
        pending = client.get(f"/api/tickets/{ticket_id}").json()
        assert pending["intent"] == "delivery_delay_compensation"
        assert pending["status"] == "pending_approval"
        assert pending["approval_tasks"][0]["status"] == "pending"
        assert pending["approval_tasks"][0]["proposed_data"]["coupon_amount"] == 5
        assert [run["agent_name"] for run in pending["agent_runs"]] == [
            "dispatcher", "order_logistics", "knowledge", "risk_control", "reply",
        ]
        plan = pending["agent_runs"][0]["output_data"]
        assert plan["route"] == "compensation_with_approval"
        assert plan["fanout_groups"][0]["agents"] == ["order_logistics", "knowledge"]
        knowledge_run = next(run for run in pending["agent_runs"] if run["agent_name"] == "knowledge")
        assert knowledge_run["input_data"]["category"] == "logistics"
        assert all(source["category"] == "logistics" for source in knowledge_run["output_data"]["sources"])

        approve_response = client.post(f"/api/tickets/{ticket_id}/approve-coupon")
        approved = approve_response.json()
        assert approved["status"] == "resolved"
        assert approved["approval_tasks"][0]["status"] == "approved"
        assert "券码：RF5-" in approved["messages"][-1]["content"]
        assert approved["audit_logs"][-1]["action"] == "approve_coupon_compensation"


def test_approval_workbench_can_list_reject_and_assign_tasks() -> None:
    with TestClient(app) as client:
        coupon_queued = client.post("/api/tickets", json={"order_no": "RF202608290001", "content": "快递晚了三天，能赔偿我吗？"}).json()
        refund_queued = client.post("/api/tickets", json={"order_no": "RF202608290001", "content": "商品质量有问题，我要退款。"}).json()
        coupon = client.get(f"/api/tickets/{coupon_queued['id']}").json()
        refund = client.get(f"/api/tickets/{refund_queued['id']}").json()
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


def test_knowledge_file_ingestion_creates_a_review_draft() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/documents/ingest",
            data={"category": "after_sales", "version": "v2.0"},
            files={
                "file": (
                    "售后FAQ.md",
                    "# 售后 FAQ\n\n商品损坏时，请客户上传商品照片并由主管复核。".encode("utf-8"),
                    "text/markdown",
                )
            },
        )
        assert response.status_code == 201
        ingested = response.json()
        assert ingested["document"]["source_type"] == "markdown"
        assert ingested["document"]["source_name"] == "售后FAQ.md"
        assert ingested["document"]["ingestion_status"] == "draft"
        assert ingested["document"]["is_active"] is False
        assert ingested["chunk_count"] >= 1


def test_rag_evaluation_persists_repeatable_run() -> None:
    with TestClient(app) as client:
        response = client.post("/api/knowledge/evaluations")
        assert response.status_code == 200
        result = response.json()
        assert result["total_cases"] == 6
        assert len(result["details"]) == 6

        history = client.get("/api/knowledge/evaluations")
        assert history.status_code == 200
        assert history.json()[0]["id"] == result["id"]
