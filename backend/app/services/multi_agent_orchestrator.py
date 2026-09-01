"""Observable, role-based orchestration for ticket processing.

The agents share a workflow context but do not share decision authority: the
risk agent is rule-first and owns action gating, while an LLM can only assist
with intent classification and customer-facing wording.
"""

from dataclasses import asdict
from time import perf_counter
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, ApprovalTask, AuditLog, LogisticsEvent, Order, Ticket, TicketMessage, utc_now
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge
from app.services.llm_provider import get_provider
from app.services.ticket_processor import ClassificationResult, classify_ticket, generate_grounded_reply


def _compact(value: Any) -> Any:
    """Keep observability useful without persisting large prompts repeatedly."""
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _trace(
    db: Session,
    *,
    ticket: Ticket,
    sequence: int,
    agent_name: str,
    provider: str,
    model: str | None,
    input_data: dict[str, Any],
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started_at = utc_now()
    started = perf_counter()
    run = AgentRun(
        ticket_id=ticket.id,
        sequence=sequence,
        agent_name=agent_name,
        status="running",
        provider=provider,
        model=model,
        input_data=_compact(input_data),
        started_at=started_at,
    )
    db.add(run)
    db.flush()
    try:
        output = execute()
    except Exception as exc:
        run.status = "failed"
        run.error = type(exc).__name__
        run.duration_ms = round((perf_counter() - started) * 1000)
        run.finished_at = utc_now()
        raise
    run.status = "completed"
    run.output_data = _compact(output)
    run.duration_ms = round((perf_counter() - started) * 1000)
    run.finished_at = utc_now()
    return output


def _read_order_context(db: Session, ticket: Ticket) -> dict[str, Any]:
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    latest_event = None
    if order:
        latest_event = db.scalar(
            select(LogisticsEvent)
            .where(LogisticsEvent.order_id == order.id)
            .order_by(LogisticsEvent.occurred_at.desc())
            .limit(1)
        )
    return {
        "order_found": bool(order),
        "order_no": order.order_no if order else None,
        "product_name": order.product_name if order else None,
        "order_status": order.status if order else None,
        "latest_logistics_status": latest_event.status if latest_event else None,
        "latest_logistics_event": latest_event.description if latest_event else None,
    }


def _source_payload(sources: list[KnowledgeSource]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": source.document_id,
            "title": source.title,
            "version": source.version,
            "score": round(source.score, 4),
            "content": source.content,
        }
        for source in sources
    ]


def _risk_decision(classification: ClassificationResult, order_context: dict[str, Any]) -> dict[str, Any]:
    action = classification.suggested_action
    if action == "request_coupon_approval":
        return {
            "action": action,
            "status": "pending_approval",
            "requires_human_approval": True,
            "reason": "补偿属于资金权益操作，必须由人工确认。",
        }
    if action == "escalate_to_supervisor":
        return {
            "action": action,
            "status": "escalated",
            "requires_human_approval": True,
            "reason": "退款和质量争议属于高风险操作，禁止 AI 自动执行。",
        }
    if action == "query_logistics" and order_context["latest_logistics_event"]:
        return {
            "action": action,
            "status": "resolved",
            "requires_human_approval": False,
            "reason": "仅查询订单物流信息，无资金或退款风险。",
        }
    return {
        "action": "escalate_to_human",
        "status": "escalated",
        "requires_human_approval": True,
        "reason": "缺少可自动处置依据，转人工处理。",
    }


def _draft_reply(decision: dict[str, Any], order_context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action = decision["action"]
    if action == "request_coupon_approval":
        proposal = {"coupon_amount": 5, "currency": "CNY", "reason": "物流延迟补偿"}
        return "因物流延迟，系统建议发放5元优惠券补偿，已提交客服审批。", proposal
    if action == "escalate_to_supervisor":
        proposal = {
            "reason": "涉及退款或质量争议，禁止AI直接执行退款",
            "required_evidence": ["订单信息", "商品问题照片或视频", "签收及使用情况"],
        }
        return "该退款诉求已标记为高风险，工单已转交主管复核，请补充商品问题的照片或视频。", proposal
    if action == "query_logistics":
        return (
            f"您好，订单 {order_context['order_no']} 当前物流状态："
            f"{order_context['latest_logistics_event']}。我们会继续关注配送进度。",
            {
                "order_no": order_context["order_no"],
                "logistics_status": order_context["latest_logistics_status"],
                "latest_event": order_context["latest_logistics_event"],
            },
        )
    return "该问题需要人工进一步判断，工单已转交人工客服处理。", {"reason": "unsupported_intent"}


def orchestrate_ticket(db: Session, ticket: Ticket) -> Ticket:
    """Run the five agents synchronously and save a replayable execution trace."""
    if ticket.status in {"resolved", "pending_approval", "escalated"}:
        return ticket

    dispatcher_provider = get_provider("dispatcher")
    classification_box: dict[str, ClassificationResult] = {}

    def dispatch() -> dict[str, Any]:
        classification = classify_ticket(ticket.content)
        classification_box["value"] = classification
        return asdict(classification)

    classification_data = _trace(
        db,
        ticket=ticket,
        sequence=1,
        agent_name="dispatcher",
        provider=dispatcher_provider.name if dispatcher_provider else "rules",
        model=dispatcher_provider.model if dispatcher_provider else None,
        input_data={"ticket_content": ticket.content},
        execute=dispatch,
    )
    classification = classification_box["value"]
    ticket.intent = classification.intent
    ticket.priority = classification.priority
    ticket.risk_level = classification.risk_level
    ticket.status = "processing"

    order_context = _trace(
        db,
        ticket=ticket,
        sequence=2,
        agent_name="order_logistics",
        provider="database",
        model=None,
        input_data={"order_id": ticket.order_id, "intent": classification.intent},
        execute=lambda: _read_order_context(db, ticket),
    )

    source_box: dict[str, list[KnowledgeSource]] = {}

    def search_knowledge() -> dict[str, Any]:
        sources = retrieve_knowledge(db, ticket.content)
        source_box["value"] = sources
        return {"source_count": len(sources), "sources": _source_payload(sources)}

    knowledge_context = _trace(
        db,
        ticket=ticket,
        sequence=3,
        agent_name="knowledge",
        provider="milvus" if source_box is not None else "disabled",
        model=None,
        input_data={"query": ticket.content, "top_k": 3},
        execute=search_knowledge,
    )
    sources = source_box["value"]

    decision = _trace(
        db,
        ticket=ticket,
        sequence=4,
        agent_name="risk_control",
        provider="rules",
        model=None,
        input_data={
            "classification": classification_data,
            "order_found": order_context["order_found"],
            "knowledge_source_count": knowledge_context["source_count"],
        },
        execute=lambda: _risk_decision(classification, order_context),
    )

    reply_provider = get_provider("reply")
    reply_box: dict[str, Any] = {}

    def compose_reply() -> dict[str, Any]:
        draft_reply, action_result = _draft_reply(decision, order_context)
        reply, reply_source = generate_grounded_reply(ticket.content, draft_reply, sources)
        reply_box.update(reply=reply, action_result=action_result, reply_source=reply_source)
        return {"reply": reply, "reply_source": reply_source, "used_knowledge": bool(sources)}

    _trace(
        db,
        ticket=ticket,
        sequence=5,
        agent_name="reply",
        provider=reply_provider.name if reply_provider else "template",
        model=reply_provider.model if reply_provider else None,
        input_data={"action": decision["action"], "knowledge_source_count": len(sources)},
        execute=compose_reply,
    )

    action_result = reply_box["action_result"]
    action_result["reply_source"] = reply_box["reply_source"]
    action_result["knowledge_sources"] = _source_payload(sources)
    if decision["action"] == "request_coupon_approval":
        db.add(ApprovalTask(ticket_id=ticket.id, task_type="coupon_compensation", proposed_data=action_result.copy()))
    elif decision["action"] == "escalate_to_supervisor":
        db.add(ApprovalTask(ticket_id=ticket.id, task_type="refund_review", proposed_data=action_result.copy()))

    ticket.status = decision["status"]
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="assistant", content=reply_box["reply"]))
    db.add(
        AuditLog(
            ticket_id=ticket.id,
            action=decision["action"],
            operator_type="orchestrator",
            input_data={"classification": asdict(classification), "risk_decision": decision},
            output_data=action_result,
        )
    )
    db.commit()
    return ticket
