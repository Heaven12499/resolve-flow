from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.core.config import settings
from app.models import ApprovalTask, AuditLog, KnowledgeDocument, Order, Ticket, TicketMessage, utc_now
from app.schemas import (
    KnowledgeDocumentRead,
    ApprovalDecision,
    ApprovalQueueItem,
    KnowledgeReindexResult,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    OrderDetail,
    TicketCreate,
    TicketDetail,
    TicketRead,
)
from app.services.knowledge_service import reindex_knowledge, retrieve_knowledge
from app.services.ticket_processor import process_ticket


router = APIRouter(prefix="/api")


def get_ticket_or_404(db: Session, ticket_id: int, *, for_update: bool = False) -> Ticket:
    statement = select(Ticket).where(Ticket.id == ticket_id)
    if for_update:
        statement = statement.with_for_update()
    ticket = db.scalar(statement)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ticket


def get_ticket_detail(db: Session, ticket_id: int) -> Ticket:
    statement = (
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.messages),
            selectinload(Ticket.audit_logs),
            selectinload(Ticket.approval_tasks),
            selectinload(Ticket.agent_runs),
        )
    )
    ticket = db.scalar(statement)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    ticket.messages.sort(key=lambda message: message.created_at)
    ticket.audit_logs.sort(key=lambda log: log.created_at)
    ticket.approval_tasks.sort(key=lambda task: task.created_at)
    ticket.agent_runs.sort(key=lambda run: run.sequence)
    return ticket


@router.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "ai_provider": settings.ai_provider,
        "deepseek_api_key_configured": bool(settings.deepseek_api_key),
    }


@router.post(
    "/tickets",
    response_model=TicketDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)) -> Ticket:
    order = db.scalar(select(Order).where(Order.order_no == payload.order_no))
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    now = datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_no=f"TK{now:%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}",
        customer_id=order.customer_id,
        order_id=order.id,
        title=payload.title or payload.content[:50],
        content=payload.content,
        status="new",
    )
    db.add(ticket)
    db.flush()
    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_type="customer",
            content=payload.content,
        )
    )
    db.add(
        AuditLog(
            ticket_id=ticket.id,
            action="create_ticket",
            operator_type="customer",
            input_data={"order_no": payload.order_no},
            output_data={"ticket_no": ticket.ticket_no},
        )
    )
    # The demo uses synchronous orchestration so the customer immediately receives
    # an outcome. Production would enqueue this work and notify the same ticket.
    process_ticket(db, ticket)
    return get_ticket_detail(db, ticket.id)


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(db: Session = Depends(get_db)) -> list[Ticket]:
    return list(db.scalars(select(Ticket).order_by(Ticket.created_at.desc())).all())


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def read_ticket(ticket_id: int, db: Session = Depends(get_db)) -> Ticket:
    return get_ticket_detail(db, ticket_id)


@router.post("/tickets/{ticket_id}/process", response_model=TicketDetail)
def run_ticket_processing(ticket_id: int, db: Session = Depends(get_db)) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id, for_update=True)
    process_ticket(db, ticket)
    return get_ticket_detail(db, ticket_id)


@router.post("/tickets/{ticket_id}/approve-coupon", response_model=TicketDetail)
def approve_coupon_compensation(ticket_id: int, db: Session = Depends(get_db)) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id, for_update=True)
    task = db.scalar(
        select(ApprovalTask)
        .where(
            ApprovalTask.ticket_id == ticket_id,
            ApprovalTask.task_type == "coupon_compensation",
            ApprovalTask.status == "pending",
        )
        .with_for_update()
    )
    if not task:
        raise HTTPException(status_code=409, detail="没有待审批的优惠券补偿任务")

    amount = task.proposed_data["coupon_amount"]
    coupon_code = f"RF{amount}-{uuid4().hex[:8].upper()}"
    task.status = "approved"
    task.decision_data = {"coupon_code": coupon_code, "approved_by": "demo_agent"}
    task.decided_at = utc_now()
    ticket.status = "resolved"
    db.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_type="agent",
            content=f"您的{amount}元补偿优惠券已发放，券码：{coupon_code}。",
        )
    )
    db.add(
        AuditLog(
            ticket_id=ticket.id,
            action="approve_coupon_compensation",
            operator_type="agent",
            input_data={"approval_task_id": task.id, "coupon_amount": amount},
            output_data={"coupon_code": coupon_code, "status": "granted"},
        )
    )
    db.commit()
    return get_ticket_detail(db, ticket_id)


def get_approval_task_or_404(db: Session, task_id: int) -> ApprovalTask:
    task = db.scalar(
        select(ApprovalTask).where(ApprovalTask.id == task_id).with_for_update()
    )
    if not task:
        raise HTTPException(status_code=404, detail="审批任务不存在")
    if task.status != "pending":
        raise HTTPException(status_code=409, detail="该审批任务已被处理")
    return task


def approval_queue_item(task: ApprovalTask) -> ApprovalQueueItem:
    return ApprovalQueueItem(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        proposed_data=task.proposed_data,
        decision_data=task.decision_data,
        created_at=task.created_at,
        decided_at=task.decided_at,
        ticket_id=task.ticket_id,
        ticket_no=task.ticket.ticket_no,
        ticket_title=task.ticket.title,
        ticket_content=task.ticket.content,
        ticket_status=task.ticket.status,
        risk_level=task.ticket.risk_level,
    )


@router.get("/approvals", response_model=list[ApprovalQueueItem])
def list_pending_approvals(db: Session = Depends(get_db)) -> list[ApprovalQueueItem]:
    tasks = list(
        db.scalars(
            select(ApprovalTask)
            .where(ApprovalTask.status.in_(["pending", "in_review"]))
            .options(joinedload(ApprovalTask.ticket))
            .order_by(ApprovalTask.created_at.asc())
        ).all()
    )
    return [approval_queue_item(task) for task in tasks]


@router.post("/approvals/{task_id}/approve-coupon", response_model=TicketDetail)
def approve_coupon_from_workbench(task_id: int, db: Session = Depends(get_db)) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    if task.task_type != "coupon_compensation":
        raise HTTPException(status_code=409, detail="该任务不是优惠券补偿审批")
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    amount = task.proposed_data["coupon_amount"]
    coupon_code = f"RF{amount}-{uuid4().hex[:8].upper()}"
    task.status = "approved"
    task.decision_data = {"coupon_code": coupon_code, "approved_by": "demo_reviewer"}
    task.decided_at = utc_now()
    ticket.status = "resolved"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content=f"您的{amount}元补偿优惠券已发放，券码：{coupon_code}。"))
    db.add(AuditLog(ticket_id=ticket.id, action="approve_coupon_from_workbench", operator_type="reviewer", input_data={"approval_task_id": task.id, "coupon_amount": amount}, output_data={"coupon_code": coupon_code, "status": "granted"}))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.post("/approvals/{task_id}/reject", response_model=TicketDetail)
def reject_approval_task(
    task_id: int, payload: ApprovalDecision, db: Session = Depends(get_db)
) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    task.status = "rejected"
    task.decision_data = {"rejected_by": "demo_reviewer", "reason": payload.reason or "不满足当前审批条件"}
    task.decided_at = utc_now()
    ticket.status = "resolved"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content=f"抱歉，本次申请未获批准。原因：{task.decision_data['reason']}。"))
    db.add(AuditLog(ticket_id=ticket.id, action="reject_approval_task", operator_type="reviewer", input_data={"approval_task_id": task.id, "task_type": task.task_type}, output_data=task.decision_data))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.post("/approvals/{task_id}/assign-supervisor", response_model=TicketDetail)
def assign_refund_review_to_supervisor(
    task_id: int, payload: ApprovalDecision, db: Session = Depends(get_db)
) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    if task.task_type != "refund_review":
        raise HTTPException(status_code=409, detail="该任务不是退款复核任务")
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    task.status = "in_review"
    task.decision_data = {"assigned_to": "supervisor", "note": payload.reason or "已转主管复核"}
    task.decided_at = utc_now()
    ticket.status = "escalated"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content="您的退款诉求已转交主管复核，我们将在核验材料后反馈处理结果。"))
    db.add(AuditLog(ticket_id=ticket.id, action="assign_refund_review_to_supervisor", operator_type="reviewer", input_data={"approval_task_id": task.id}, output_data=task.decision_data))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.get("/knowledge/documents", response_model=list[KnowledgeDocumentRead])
def list_knowledge_documents(db: Session = Depends(get_db)) -> list[KnowledgeDocument]:
    return list(
        db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.id)).all()
    )


@router.post("/knowledge/reindex", response_model=KnowledgeReindexResult)
def sync_knowledge_index(db: Session = Depends(get_db)) -> KnowledgeReindexResult:
    try:
        document_count, chunk_count = reindex_knowledge(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"知识库同步失败：{type(exc).__name__}") from exc
    return KnowledgeReindexResult(
        document_count=document_count,
        chunk_count=chunk_count,
        collection_name=settings.milvus_collection_name,
    )


@router.post("/knowledge/search", response_model=list[KnowledgeSearchResult])
def search_knowledge(
    payload: KnowledgeSearchRequest, db: Session = Depends(get_db)
) -> list[KnowledgeSearchResult]:
    return [
        KnowledgeSearchResult(**source.__dict__)
        for source in retrieve_knowledge(db, payload.query, payload.limit)
    ]


@router.get("/orders/{order_no}", response_model=OrderDetail)
def read_order(order_no: str, db: Session = Depends(get_db)) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.order_no == order_no)
        .options(selectinload(Order.logistics_events))
    )
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    order.logistics_events.sort(key=lambda event: event.occurred_at)
    return order
