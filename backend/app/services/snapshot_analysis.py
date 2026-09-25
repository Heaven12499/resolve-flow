from datetime import datetime, timezone

from app.internal_schemas import (
    CaseAnalysisRequest,
    CaseAnalysisResult,
    EvidenceReference,
)
from app.services.ticket_processor import classify_ticket


DELIVERED_STATUSES = {"delivered", "signed", "completed"}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def analyze_case_snapshot(payload: CaseAnalysisRequest) -> CaseAnalysisResult:
    """Analyze an immutable business snapshot without writing business data.

    The Java service remains responsible for validating and applying this
    non-binding recommendation.
    """
    classification = classify_ticket(payload.ticket.content)
    timeline = sorted(payload.logistics_timeline, key=lambda item: item.occurred_at)
    latest = timeline[-1] if timeline else None
    delivered = next(
        (item for item in reversed(timeline) if item.status in DELIVERED_STATUSES),
        None,
    )
    comparison_time = _utc_naive(delivered.occurred_at) if delivered else datetime.now(timezone.utc).replace(tzinfo=None)
    promised_at = (
        _utc_naive(payload.order.promised_delivery_at)
        if payload.order.promised_delivery_at
        else None
    )
    overdue = bool(promised_at and comparison_time > promised_at)

    evidence = [
        EvidenceReference(
            type="tracking",
            reference=f"tracking:{item.event_id or index + 1}",
        )
        for index, item in enumerate(timeline)
    ]
    evidence.extend(
        EvidenceReference(
            type="attachment",
            reference=f"evidence:{item.evidence_id or index + 1}",
        )
        for index, item in enumerate(payload.evidence)
    )

    intent = classification.intent
    if intent == "logistics_query" and latest:
        action = "QUERY_LOGISTICS"
        reply = (
            f"您好，订单 {payload.order.order_no} 当前物流状态："
            f"{latest.description}。我们会继续关注配送进度。"
        )
        requires_approval = False
    elif intent == "delivery_delay_compensation" and overdue and latest:
        action = "REQUEST_COUPON_APPROVAL"
        reply = "经核实物流已超过承诺时效，系统建议发放5元优惠券，需由客服审批后生效。"
        requires_approval = True
    elif intent == "refund_risk_review":
        action = "ESCALATE_REFUND_REVIEW"
        reply = "该诉求涉及退款或质量争议，已建议转交主管复核，AI不会直接执行退款。"
        requires_approval = True
    else:
        action = "ESCALATE_TO_HUMAN"
        reply = "当前信息不足以自动处置，建议转交人工客服进一步核验。"
        requires_approval = True

    return CaseAnalysisResult(
        task_id=payload.task_id,
        ticket_id=payload.ticket_id,
        business_version=payload.business_version,
        intent=intent,
        priority=classification.priority,
        risk_level=classification.risk_level,
        recommended_action=action,
        suggested_coupon_amount=5 if action == "REQUEST_COUPON_APPROVAL" else None,
        reply_draft=reply,
        confidence=0.9 if classification.source != "rules" else 0.75,
        requires_human_approval=requires_approval,
        evidence=evidence,
        model_source=classification.source,
        fallback_reason=classification.fallback_reason,
    )
