from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AiAnalysisRun


client = TestClient(app)


def request_payload(content: str = "物流延迟了，我要求补偿") -> dict:
    return {
        "task_id": "AIT-001",
        "ticket_id": 1,
        "business_version": 0,
        "ticket": {"title": "物流问题", "content": content},
        "order": {
            "order_no": "RF202608290001",
            "product_name": "测试商品",
            "amount": "299.00",
            "status": "shipped",
            "shipped_at": "2026-09-20T08:00:00",
            "promised_delivery_at": "2026-09-21T18:00:00",
        },
        "logistics_timeline": [
            {
                "event_id": 10,
                "status": "in_transit",
                "description": "包裹运输中",
                "occurred_at": "2026-09-20T12:00:00",
            }
        ],
        "messages": [],
        "evidence": [],
    }


def test_internal_ai_endpoint_requires_service_token():
    response = client.post("/internal/v1/ai/analyze", json=request_payload())
    assert response.status_code == 401


def test_internal_ai_endpoint_returns_non_binding_structured_recommendation():
    response = client.post(
        "/internal/v1/ai/analyze",
        json=request_payload(),
        headers={"X-Internal-Token": settings.internal_api_token},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["task_id"] == "AIT-001"
    assert result["business_version"] == 0
    assert result["recommended_action"] == "REQUEST_COUPON_APPROVAL"
    assert result["requires_human_approval"] is True
    assert result["suggested_coupon_amount"] == 5


def test_internal_admin_proxy_requires_token_and_exposes_knowledge_documents():
    unauthorized = client.get("/internal/v1/admin/knowledge/documents")
    assert unauthorized.status_code == 401

    response = client.get(
        "/internal/v1/admin/knowledge/documents",
        headers={"X-Internal-Token": settings.internal_api_token},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_analysis_is_persisted_and_replayed_by_task_id(monkeypatch):
    from app.api import internal_routes

    payload = request_payload()
    payload["task_id"] = "AIT-IDEMPOTENT-001"
    original = internal_routes.analyze_case_snapshot
    calls = 0

    def counted_analysis(request, db=None):
        nonlocal calls
        calls += 1
        return original(request, db)

    monkeypatch.setattr(internal_routes, "analyze_case_snapshot", counted_analysis)
    headers = {"X-Internal-Token": settings.internal_api_token}

    first = client.post("/internal/v1/ai/analyze", json=payload, headers=headers)
    replay = client.post("/internal/v1/ai/analyze", json=payload, headers=headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert calls == 1
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count()).select_from(AiAnalysisRun).where(
                AiAnalysisRun.task_id == payload["task_id"]
            )
        )
    assert count == 1


def test_task_id_cannot_be_reused_for_a_different_snapshot():
    payload = request_payload()
    payload["task_id"] = "AIT-IDENTITY-001"
    headers = {"X-Internal-Token": settings.internal_api_token}
    first = client.post("/internal/v1/ai/analyze", json=payload, headers=headers)
    assert first.status_code == 200

    payload["ticket"]["content"] = "同一个任务号但内容已经变化"
    conflict = client.post("/internal/v1/ai/analyze", json=payload, headers=headers)

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "task_id is already bound to a different snapshot"


def test_internal_agent_monitor_reads_multi_agent_snapshot_trace():
    payload = request_payload()
    payload["task_id"] = "AIT-MONITOR-001"
    payload["order"]["order_no"] = "RF-MONITOR-001"
    headers = {"X-Internal-Token": settings.internal_api_token}
    analyzed = client.post("/internal/v1/ai/analyze", json=payload, headers=headers)
    assert analyzed.status_code == 200

    response = client.get(
        "/internal/v1/admin/agent-runs",
        headers=headers,
    )

    assert response.status_code == 200
    runs = [item for item in response.json() if item["ticket_no"] == "RF-MONITOR-001"]
    names = [run["agent_name"] for run in runs]
    assert names[0] == "supervisor"
    assert names[-2:] == ["risk_control", "reply"]
    assert names.count("logistics_resolution_agent") == 4
    assert names.count("evidence_gate") == 4
    assert [
        run["output_data"]["action"]
        for run in runs if run["agent_name"] == "logistics_resolution_agent"
    ] == ["get_order", "get_ticket_messages", "analyze_delivery_timeline", "search_policy"]
    assert all(run["status"] == "completed" for run in runs)


def test_snapshot_result_contains_auditable_orchestration_trace():
    payload = request_payload("商品损坏了，我要退款")
    payload["task_id"] = "AIT-TRACE-001"
    payload["ticket"]["ticket_no"] = "TK-TRACE-001"
    payload["evidence"] = [
        {
            "evidence_id": 7,
            "file_name": "damage.jpg",
            "media_type": "image/jpeg",
            "storage_uri": "s3://demo/damage.jpg",
            "sha256": "a" * 64,
        }
    ]
    response = client.post(
        "/internal/v1/ai/analyze",
        json=payload,
        headers={"X-Internal-Token": settings.internal_api_token},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["orchestration_plan"]["route"] == "refund_agent_investigation"
    names = [step["agent_name"] for step in result["execution_trace"]]
    assert names[0] == "supervisor"
    assert names[-3:] == ["refund_review_analyst", "risk_control", "reply"]
    assert names.count("refund_investigation_agent") == 4
    assert [
        step["output_data"]["action"]
        for step in result["execution_trace"]
        if step["agent_name"] == "refund_investigation_agent"
    ] == ["get_order", "get_ticket_messages", "search_policy", "inspect_customer_evidence"]
    assert result["review_package"]["recommended_next_step"] in {
        "request_evidence", "supervisor_review"
    }
    assert result["recommended_action"] == "ESCALATE_REFUND_REVIEW"


def test_refund_agent_requests_customer_evidence_when_attachment_is_missing():
    payload = request_payload("商品损坏了，我要退款")
    payload["task_id"] = "AIT-WAIT-EVIDENCE-001"
    response = client.post(
        "/internal/v1/ai/analyze",
        json=payload,
        headers={"X-Internal-Token": settings.internal_api_token},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["recommended_action"] == "REQUEST_CUSTOMER_EVIDENCE"
    ask_step = next(
        step for step in result["execution_trace"]
        if step["agent_name"] == "case_action_ask_customer"
    )
    assert "照片" in ask_step["output_data"]["data"]["question"]
    assert result["execution_trace"][-2]["agent_name"] == "risk_control"


def test_specialist_loop_stops_at_hard_step_budget(monkeypatch):
    from app.services import snapshot_orchestrator
    from app.services.case_investigation import CaseManagerDecision

    monkeypatch.setattr(
        snapshot_orchestrator,
        "choose_case_action",
        lambda *args, **kwargs: (
            CaseManagerDecision(action="get_order", reason="重复核验以模拟失控规划器"),
            "test-planner",
            None,
        ),
    )
    payload = request_payload()
    payload["task_id"] = "AIT-BOUNDED-LOOP-001"
    response = client.post(
        "/internal/v1/ai/analyze",
        json=payload,
        headers={"X-Internal-Token": settings.internal_api_token},
    )

    assert response.status_code == 200
    result = response.json()
    specialist_steps = [
        step for step in result["execution_trace"]
        if step["agent_name"] == "logistics_resolution_agent"
    ]
    assert len(specialist_steps) == 10
    assert result["recommended_action"] == "ESCALATE_TO_HUMAN"


def test_ai_service_health_is_independent_of_legacy_business_routes():
    response = client.get("/health", headers={"X-Request-Id": "web-request-1234"})

    assert response.status_code == 200
    assert response.json()["service"] == "ai-service"
    assert response.headers["X-Request-Id"] == "web-request-1234"


def test_ai_service_replaces_unsafe_request_id_and_exposes_metrics():
    health = client.get("/health", headers={"X-Request-Id": "bad id"})
    metrics = client.get("/metrics")

    assert health.headers["X-Request-Id"] != "bad id"
    assert metrics.status_code == 200
    assert "resolveflow_ai_http_requests_total" in metrics.text
    assert "resolveflow_ai_analysis_runs_total" in metrics.text
