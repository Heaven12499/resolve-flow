"""Atomic read-only tools hidden behind the shared Agent Skill layer."""

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LogisticsEvent, Order, TicketEvidence, TicketMessage, utc_now
from app.services.knowledge_service import KnowledgeSource, retrieve_knowledge


READ_ONLY_CASE_TOOLS = {
    "get_order",
    "analyze_delivery_timeline",
    "search_policy",
    "get_ticket_messages",
    "inspect_customer_evidence",
}

EVIDENCE_KEYWORDS = ("照片", "图片", "视频", "附件", "检测报告", "故障录屏", "证据")
DELIVERED_STATUSES = {"delivered", "signed", "completed"}
COLLECTED_STATUSES = {"collected", "picked_up", "in_transit", *DELIVERED_STATUSES}
SUPPORTED_EVIDENCE_TYPES = {"image/jpeg", "image/png", "video/mp4", "application/pdf"}


def _hours_between(later, earlier) -> float:
    return round(max(0.0, (later - earlier).total_seconds() / 3600), 1)


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
            "shipped_at": order.shipped_at.isoformat() if order and order.shipped_at else None,
            "promised_delivery_at": (
                order.promised_delivery_at.isoformat()
                if order and order.promised_delivery_at
                else None
            ),
        }
        return {"ok": bool(order), "summary": "订单已找到" if order else "未找到关联订单", "data": data}

    if action == "analyze_delivery_timeline":
        order = db.get(Order, order_id) if order_id else None
        events = list(db.scalars(
            select(LogisticsEvent)
            .where(LogisticsEvent.order_id == order_id)
            .order_by(LogisticsEvent.occurred_at.asc(), LogisticsEvent.id.asc())
        ).all()) if order_id else []
        latest = events[-1] if events else None
        delivered = next((event for event in reversed(events) if event.status in DELIVERED_STATUSES), None)
        first_collected = next((event for event in events if event.status in COLLECTED_STATUSES), None)
        now = utc_now()
        stagnant_hours = _hours_between(now, latest.occurred_at) if latest else None
        comparison_time = delivered.occurred_at if delivered else now
        delay_hours = (
            _hours_between(comparison_time, order.promised_delivery_at)
            if order and order.promised_delivery_at and comparison_time > order.promised_delivery_at
            else 0.0
        )
        is_overdue = delay_hours > 0
        conflicts: list[str] = []
        if order and order.status in DELIVERED_STATUSES and not delivered:
            conflicts.append("order_marked_delivered_without_delivery_event")
        if order and delivered and order.status not in DELIVERED_STATUSES:
            conflicts.append("tracking_delivered_but_order_not_completed")

        if not events:
            anomaly_type = "missing_tracking"
        elif conflicts:
            anomaly_type = "status_mismatch"
        elif (
            order
            and order.shipped_at
            and not first_collected
            and _hours_between(now, order.shipped_at) >= 48
        ):
            anomaly_type = "not_collected"
        elif not delivered and stagnant_hours is not None and stagnant_hours >= 72:
            anomaly_type = "tracking_stagnation"
        elif is_overdue:
            anomaly_type = "delivery_overdue"
        else:
            anomaly_type = "none"

        data = {
            "latest_logistics_status": latest.status if latest else None,
            "latest_logistics_event": latest.description if latest else None,
            "occurred_at": latest.occurred_at.isoformat() if latest else None,
            "timeline": [
                {
                    "event_id": event.id,
                    "status": event.status,
                    "description": event.description,
                    "occurred_at": event.occurred_at.isoformat(),
                }
                for event in events
            ],
            "first_collected_at": first_collected.occurred_at.isoformat() if first_collected else None,
            "stagnant_hours": stagnant_hours,
            "delay_hours": delay_hours,
            "is_overdue": is_overdue,
            "anomaly_type": anomaly_type,
            "conflicts": conflicts,
            "evidence_refs": [f"tracking:{event.id}" for event in events],
        }
        summary = (
            f"物流时序分析完成：{anomaly_type}，共 {len(events)} 个节点"
            if events
            else "未找到物流轨迹，已标记 missing_tracking"
        )
        return {"ok": bool(order and events), "summary": summary, "data": data}

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

    if action == "inspect_customer_evidence":
        declarations = [
            message.content[:500]
            for message in customer_messages
            if any(keyword in message.content for keyword in EVIDENCE_KEYWORDS)
        ]
        evidence_rows = list(
            db.scalars(
                select(TicketEvidence)
                .where(TicketEvidence.ticket_id == ticket_id)
                .order_by(TicketEvidence.created_at.asc(), TicketEvidence.id.asc())
            ).all()
        )
        sha_counts = Counter(item.sha256 for item in evidence_rows)
        items = []
        valid_refs = []
        unsupported_files = []
        unrelated_files = []
        for item in evidence_rows:
            supported = item.media_type in SUPPORTED_EVIDENCE_TYPES
            order_matched = order_id is not None and item.order_id == order_id
            reference = f"evidence:{item.id}"
            if not supported:
                unsupported_files.append(reference)
            if not order_matched:
                unrelated_files.append(reference)
            if supported and order_matched:
                valid_refs.append(reference)
            items.append(
                {
                    "evidence_id": item.id,
                    "file_name": item.file_name,
                    "media_type": item.media_type,
                    "storage_uri": item.storage_uri,
                    "sha256": item.sha256,
                    "uploaded_by": item.uploaded_by,
                    "created_at": item.created_at.isoformat(),
                    "order_matched": order_matched,
                    "supported": supported,
                    "reference": reference,
                }
            )
        data = {
            "customer_message_count": len(customer_messages),
            "evidence_present": bool(valid_refs),
            "items": items,
            "evidence_declarations": declarations,
            "unsupported_files": unsupported_files,
            "unrelated_files": unrelated_files,
            "duplicate_count": sum(count - 1 for count in sha_counts.values() if count > 1),
            "evidence_refs": valid_refs,
        }
        summary = (
            f"发现 {len(valid_refs)} 份可验证客户材料"
            if valid_refs
            else "未发现与当前订单关联的可验证客户材料"
        )
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
