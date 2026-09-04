import json

from app.core.config import settings
from app.services import llm_provider, ticket_processor


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "intent": "delivery_delay_compensation",
                            }
                        )
                    }
                }
            ]
        }


class InvalidJsonResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "not-json"}}]}


def test_deepseek_json_classification(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(llm_provider.httpx, "post", lambda *args, **kwargs: FakeResponse())

    result = ticket_processor.classify_ticket("快递晚了三天，能赔偿我吗？")

    assert result.intent == "delivery_delay_compensation"
    assert result.suggested_action == "request_coupon_approval"
    assert result.source == "deepseek"


def test_deepseek_failure_falls_back_to_rules(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")

    def raise_timeout(*args, **kwargs):
        raise ticket_processor.httpx.TimeoutException("timeout")

    monkeypatch.setattr(llm_provider.httpx, "post", raise_timeout)
    result = ticket_processor.classify_ticket("我的快递到哪里了？")

    assert result.intent == "logistics_query"
    assert result.source == "rules"
    assert result.fallback_reason == "deepseek_TimeoutException"


def test_deepseek_invalid_json_falls_back_to_rules(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(llm_provider.httpx, "post", lambda *args, **kwargs: InvalidJsonResponse())

    result = ticket_processor.classify_ticket("我的快递到哪里了？")

    assert result.intent == "logistics_query"
    assert result.source == "rules"
    assert result.fallback_reason == "deepseek_JSONDecodeError"


def test_refund_review_analysis_falls_back_to_non_binding_package(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "rules")

    analysis = ticket_processor.analyse_refund_review(
        "耳机颜色和商品页面不一样，我想退款。",
        {"order_found": True, "order_status": "shipped"},
        [],
    )

    assert analysis["issue_type"] == "wrong_item"
    assert analysis["analysis_source"] == "template"
    assert analysis["recommended_next_step"] == "request_evidence"
    assert "退款概率" not in analysis
