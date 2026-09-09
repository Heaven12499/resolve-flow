"""Atomic read-only tools hidden behind the shared Agent Skill layer."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LogisticsEvent, Order, TicketMessage
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge


READ_ONLY_CASE_TOOLS = {
    "get_order",
    "get_logistics",
    "search_policy",
    "get_ticket_messages",
    "list_customer_evidence",
}

EVIDENCE_KEYWORDS = ("照片", "图片", "视频", "附件", "检测报告", "故障录屏", "证据")


def source_payload(sources: list[KnowledgeSource]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": source.chunk_id,
            "document_id": source.document_id,
            "title": source.title,
            "version": source.version,
            "category": source.category,
            "score": round(source.score, 4),
            "content": source.content,
        }
        for source in sources
    ]


def execute_read_only_tool(
    db: Session,
    *,
    action: str,
    ticket_id: int,
    order_id: int | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if action not in READ_ONLY_CASE_TOOLS:
        raise ValueError(f"tool is not in the read-only registry: {action}")

    if action == "get_order":
        order = db.get(Order, order_id) if order_id else None
        data = {
            "order_found": bool(order),
            "order_no": order.order_no if order else None,
            "product_name": order.product_name if order else None,
            "order_status": order.status if order else None,
            "amount": str(order.amount) if order else None,
        }
        return {"ok": bool(order), "summary": "订单已找到" if order else "未找到关联订单", "data": data}

    if action == "get_logistics":
        event = db.scalar(
            select(LogisticsEvent)
            .where(LogisticsEvent.order_id == order_id)
            .order_by(LogisticsEvent.occurred_at.desc())
            .limit(1)
        ) if order_id else None
        data = {
            "latest_logistics_status": event.status if event else None,
            "latest_logistics_event": event.description if event else None,
            "occurred_at": event.occurred_at.isoformat() if event else None,
        }
        return {"ok": bool(event), "summary": event.description if event else "没有可用物流记录", "data": data}

    messages = list(
        db.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        ).all()
    )
    customer_messages = [message for message in messages if message.sender_type == "customer"]

    if action == "get_ticket_messages":
        data = {
            "customer_message_count": len(customer_messages),
            "messages": [
                {"sender_type": message.sender_type, "content": message.content[:500]}
                for message in messages[-12:]
            ],
        }
        return {"ok": True, "summary": f"已读取 {len(messages)} 条工单消息", "data": data}

    if action == "list_customer_evidence":
        matched = [
            message.content[:500]
            for message in customer_messages
            if any(keyword in message.content for keyword in EVIDENCE_KEYWORDS)
        ]
        data = {
            "customer_message_count": len(customer_messages),
            "evidence_present": bool(matched),
            "evidence_mentions": matched,
        }
        summary = f"发现 {len(matched)} 条客户材料说明" if matched else "客户尚未提供照片、视频或检测说明"
        return {"ok": True, "summary": summary, "data": data}

    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("search_policy requires a non-empty query")
    category = str(arguments.get("category", "after_sales")).strip() or "after_sales"
    if category not in {"after_sales", "logistics"}:
        raise ValueError(f"unsupported policy category: {category}")
    sources = retrieve_knowledge(db, query, category=category)
    rows = source_payload(sources)
    return {
        "ok": bool(rows),
        "summary": f"命中 {len(rows)} 条售后规则",
        "query": query,
        "data": {"sources": rows, "source_count": len(rows)},
    }
