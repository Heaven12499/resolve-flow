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

    def counted_analysis(request):
        nonlocal calls
        calls += 1
        return original(request)

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


def test_internal_agent_monitor_reads_snapshot_analysis_runs():
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
    run = next(item for item in response.json() if item["ticket_no"] == "RF-MONITOR-001")
    assert run["agent_name"] == "snapshot_analysis"
    assert run["status"] == "completed"


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
