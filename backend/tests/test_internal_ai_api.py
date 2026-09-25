from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


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
