import json
import logging
from dataclasses import asdict, dataclass, replace
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ApprovalTask, AuditLog, LogisticsEvent, Order, Ticket, TicketMessage
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassificationResult:
    intent: str
    priority: str
    risk_level: str
    suggested_action: str
    source: str = "rules"
    fallback_reason: str | None = None


class DeepSeekClassification(BaseModel):
    intent: Literal[
        "logistics_query",
        "delivery_delay_compensation",
        "refund_risk_review",
        "other",
    ]


LOGISTICS_KEYWORDS = ("物流", "快递", "没到", "到哪", "发货", "配送")
COMPENSATION_KEYWORDS = ("赔偿", "补偿", "优惠券", "延迟")
REFUND_RISK_KEYWORDS = ("退款", "质量", "不一样", "假货", "损坏")
ESCALATION_KEYWORDS = ("投诉", "12315", "曝光", "起诉")


def classification_from_intent(
    intent: str, content: str, *, source: str = "rules"
) -> ClassificationResult:
    """The backend, not the model, owns business risk and action mapping."""
    if intent == "refund_risk_review":
        return ClassificationResult(
            intent="refund_risk_review",
            priority="high",
            risk_level="high",
            suggested_action="escalate_to_supervisor",
            source=source,
        )
    if intent == "delivery_delay_compensation":
        return ClassificationResult(
            intent="delivery_delay_compensation",
            priority="medium",
            risk_level="medium",
            suggested_action="request_coupon_approval",
            source=source,
        )
    if intent == "logistics_query":
        return ClassificationResult(
            intent="logistics_query",
            priority=(
                "high"
                if any(keyword in content for keyword in ESCALATION_KEYWORDS)
                else "medium"
            ),
            risk_level="low",
            suggested_action="query_logistics",
            source=source,
        )

    return ClassificationResult(
        intent="other",
        priority="medium",
        risk_level="medium",
        suggested_action="escalate_to_human",
        source=source,
    )


def classify_by_rules(content: str) -> ClassificationResult:
    """Offline baseline and fallback for all LLM failures."""
    if any(keyword in content for keyword in REFUND_RISK_KEYWORDS):
        return classification_from_intent("refund_risk_review", content)
    if any(keyword in content for keyword in COMPENSATION_KEYWORDS):
        return classification_from_intent("delivery_delay_compensation", content)
    if any(keyword in content for keyword in LOGISTICS_KEYWORDS):
        return classification_from_intent("logistics_query", content)
    return classification_from_intent("other", content)


def classify_with_deepseek(content: str) -> ClassificationResult:
    fallback = classify_by_rules(content)
    if settings.ai_provider.lower() != "deepseek":
        return fallback
    if not settings.deepseek_api_key:
        return replace(fallback, fallback_reason="deepseek_api_key_missing")

    system_prompt = """你是电商客服工单意图分类器。仅返回一个JSON对象，不要Markdown，且只能包含intent字段。
intent只能是以下四个值之一：logistics_query、delivery_delay_compensation、refund_risk_review、other。
物流查询使用logistics_query；用户因物流延迟要求赔偿、补偿或优惠券时使用delivery_delay_compensation；
涉及退款、质量争议、假货或损坏时，必须使用refund_risk_review；其余使用other。"""
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"客户工单内容：{content}"},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.deepseek_timeout_seconds,
        )
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
        result = DeepSeekClassification.model_validate(json.loads(raw_content))
        return classification_from_intent(result.intent, content, source="deepseek")
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        diagnostic = f"http_{status_code}" if status_code else type(exc).__name__
        logger.warning("DeepSeek classification failed; using rules fallback (%s)", diagnostic)
        return replace(fallback, fallback_reason=f"deepseek_{diagnostic}")


def classify_ticket(content: str) -> ClassificationResult:
    return classify_with_deepseek(content)


def generate_grounded_reply(
    customer_content: str, draft_reply: str, sources: list[KnowledgeSource]
) -> tuple[str, str]:
    """Use retrieved policy as context, while keeping action decisions in backend code."""
    if settings.ai_provider.lower() != "deepseek" or not settings.deepseek_api_key:
        return draft_reply, "template"
    if not sources:
        return draft_reply, "template"

    policy_context = "\n\n".join(
        f"【{source.title} {source.version}】\n{source.content}" for source in sources
    )
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是电商客服回复助手。根据提供的规则依据，优化客服回复。"
                    "不得承诺规则之外的赔付、退款或时效；不得改变系统已经决定的处置结果；"
                    "只输出面向客户的一段简洁中文回复，不要Markdown。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"客户问题：{customer_content}\n\n"
                    f"系统已确定的处置结果：{draft_reply}\n\n"
                    f"规则依据：\n{policy_context}"
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 240,
        "thinking": {"type": "disabled"},
    }
    try:
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.deepseek_timeout_seconds,
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"].strip()
        if not reply:
            raise ValueError("empty_reply")
        return reply, "deepseek_rag"
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        logger.warning("DeepSeek RAG reply failed; using template fallback")
        return draft_reply, "template"


def process_ticket(db: Session, ticket: Ticket) -> Ticket:
    if ticket.status in {"resolved", "pending_approval", "escalated"}:
        return ticket

    classification = classify_ticket(ticket.content)
    ticket.intent = classification.intent
    ticket.priority = classification.priority
    ticket.risk_level = classification.risk_level
    ticket.status = "processing"

    reply: str
    action_result: dict

    if classification.suggested_action == "request_coupon_approval":
        proposed_data = {
            "coupon_amount": 5,
            "currency": "CNY",
            "reason": "物流延迟补偿",
        }
        db.add(
            ApprovalTask(
                ticket_id=ticket.id,
                task_type="coupon_compensation",
                proposed_data=proposed_data,
            )
        )
        reply = "因物流延迟，系统建议发放5元优惠券补偿，已提交客服审批。"
        action_result = proposed_data
        ticket.status = "pending_approval"
    elif classification.suggested_action == "escalate_to_supervisor":
        proposed_data = {
            "reason": "涉及退款或质量争议，禁止AI直接执行退款",
            "required_evidence": ["订单信息", "商品问题照片或视频", "签收及使用情况"],
        }
        db.add(
            ApprovalTask(
                ticket_id=ticket.id,
                task_type="refund_review",
                proposed_data=proposed_data,
            )
        )
        reply = "该退款诉求已标记为高风险，工单已转交主管复核，请补充商品问题的照片或视频。"
        action_result = proposed_data
        ticket.status = "escalated"
    elif classification.suggested_action == "query_logistics" and ticket.order_id:
        order = db.get(Order, ticket.order_id)
        latest_event = db.scalar(
            select(LogisticsEvent)
            .where(LogisticsEvent.order_id == ticket.order_id)
            .order_by(LogisticsEvent.occurred_at.desc())
            .limit(1)
        )
        if order and latest_event:
            reply = (
                f"您好，订单 {order.order_no} 当前物流状态："
                f"{latest_event.description}。我们会继续关注配送进度。"
            )
            action_result = {
                "order_no": order.order_no,
                "logistics_status": latest_event.status,
                "latest_event": latest_event.description,
            }
            ticket.status = "resolved"
        else:
            reply = "暂时没有查询到物流轨迹，工单已转交人工客服处理。"
            action_result = {"reason": "logistics_event_not_found"}
            ticket.status = "escalated"
    else:
        reply = "该问题需要人工进一步判断，工单已转交人工客服处理。"
        action_result = {"reason": "unsupported_intent"}
        ticket.status = "escalated"

    knowledge_sources = retrieve_knowledge(db, ticket.content)
    if knowledge_sources:
        reply, reply_source = generate_grounded_reply(
            ticket.content, reply, knowledge_sources
        )
        action_result["reply_source"] = reply_source
        action_result["knowledge_sources"] = [
            {
                "document_id": source.document_id,
                "title": source.title,
                "version": source.version,
                "score": round(source.score, 4),
            }
            for source in knowledge_sources
        ]

    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_type="assistant",
            content=reply,
        )
    )
    db.add(
        AuditLog(
            ticket_id=ticket.id,
            action=classification.suggested_action,
            operator_type="system",
            input_data={"classification": asdict(classification)},
            output_data=action_result,
        )
    )
    db.commit()
    return ticket
