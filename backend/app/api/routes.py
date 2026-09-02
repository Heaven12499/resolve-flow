from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.core.auth import Actor, authenticate, issue_access_token, require_roles
from app.core.config import settings
from app.models import AgentRun, ApprovalTask, AuditLog, KnowledgeDocument, KnowledgeEvaluationRun, Order, Ticket, TicketMessage, utc_now
from app.schemas import (
    KnowledgeDocumentRead,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    ApprovalDecision,
    ApprovalQueueItem,
    AgentRunQueueItem,
    KnowledgeReindexResult,
    KnowledgeIngestionResult,
    KnowledgeEvaluationRunRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    OrderDetail,
    TicketCreate,
    TicketDetail,
    TicketRead,
    AccessTokenRead,
    LoginRequest,
)
from app.services.knowledge_service import (
    clean_document_text,
    content_fingerprint,
    prepare_uploaded_corpus,
    reindex_knowledge,
    retrieve_knowledge,
)
from app.services.rag_evaluation import run_rag_evaluation
from app.services.processing_queue import enqueue_ticket_processing, run_ticket_processing_job


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
            selectinload(Ticket.processing_job),
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
        "auth_enabled": settings.auth_enabled,
    }


@router.post("/auth/login", response_model=AccessTokenRead)
def login(payload: LoginRequest) -> AccessTokenRead:
    if not settings.auth_enabled:
        raise HTTPException(status_code=409, detail="本地演示模式未启用登录")
    actor = authenticate(payload.username, payload.password)
    if not actor:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    return AccessTokenRead(
        access_token=issue_access_token(actor),
        expires_in=settings.auth_token_ttl_minutes * 60,
        username=actor.username,
        role=actor.role,
    )


@router.post(
    "/tickets",
    response_model=TicketDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
def create_ticket(payload: TicketCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> Ticket:
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
    enqueue_ticket_processing(db, ticket)
    db.commit()
    background_tasks.add_task(run_ticket_processing_job, ticket.id)
    return get_ticket_detail(db, ticket.id)


@router.get("/tickets", response_model=list[TicketRead], dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def list_tickets(db: Session = Depends(get_db)) -> list[Ticket]:
    return list(db.scalars(select(Ticket).order_by(Ticket.created_at.desc())).all())


@router.get("/tickets/{ticket_id}", response_model=TicketDetail, dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def read_ticket(ticket_id: int, db: Session = Depends(get_db)) -> Ticket:
    return get_ticket_detail(db, ticket_id)


@router.get("/agent-runs", response_model=list[AgentRunQueueItem], dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def list_agent_runs(
    limit: int = Query(default=100, ge=1, le=300), db: Session = Depends(get_db)
) -> list[AgentRunQueueItem]:
    runs = list(
        db.scalars(
            select(AgentRun)
            .options(joinedload(AgentRun.ticket))
            .order_by(AgentRun.started_at.desc(), AgentRun.sequence.asc())
            .limit(limit)
        ).all()
    )
    return [
        AgentRunQueueItem(
            id=run.id,
            sequence=run.sequence,
            agent_name=run.agent_name,
            status=run.status,
            provider=run.provider,
            model=run.model,
            input_data=run.input_data,
            output_data=run.output_data,
            error=run.error,
            duration_ms=run.duration_ms,
            started_at=run.started_at,
            finished_at=run.finished_at,
            ticket_id=run.ticket_id,
            ticket_no=run.ticket.ticket_no,
            ticket_title=run.ticket.title,
            ticket_status=run.ticket.status,
        )
        for run in runs
    ]


@router.post("/tickets/{ticket_id}/process", response_model=TicketDetail, dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def run_ticket_processing(ticket_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id, for_update=True)
    if not enqueue_ticket_processing(db, ticket):
        raise HTTPException(status_code=409, detail="工单正在处理、已完成或已达到最大重试次数")
    db.commit()
    background_tasks.add_task(run_ticket_processing_job, ticket.id)
    return get_ticket_detail(db, ticket_id)


@router.post("/tickets/{ticket_id}/approve-coupon", response_model=TicketDetail)
def approve_coupon_compensation(ticket_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require_roles("supervisor", "admin"))) -> Ticket:
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
    task.decision_data = {"coupon_code": coupon_code, "approved_by": actor.username}
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
            operator_type=actor.role,
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


@router.get("/approvals", response_model=list[ApprovalQueueItem], dependencies=[Depends(require_roles("supervisor", "admin"))])
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
def approve_coupon_from_workbench(task_id: int, db: Session = Depends(get_db), actor: Actor = Depends(require_roles("supervisor", "admin"))) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    if task.task_type != "coupon_compensation":
        raise HTTPException(status_code=409, detail="该任务不是优惠券补偿审批")
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    amount = task.proposed_data["coupon_amount"]
    coupon_code = f"RF{amount}-{uuid4().hex[:8].upper()}"
    task.status = "approved"
    task.decision_data = {"coupon_code": coupon_code, "approved_by": actor.username}
    task.decided_at = utc_now()
    ticket.status = "resolved"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content=f"您的{amount}元补偿优惠券已发放，券码：{coupon_code}。"))
    db.add(AuditLog(ticket_id=ticket.id, action="approve_coupon_from_workbench", operator_type=actor.role, input_data={"approval_task_id": task.id, "coupon_amount": amount}, output_data={"coupon_code": coupon_code, "status": "granted", "approved_by": actor.username}))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.post("/approvals/{task_id}/reject", response_model=TicketDetail)
def reject_approval_task(
    task_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), actor: Actor = Depends(require_roles("supervisor", "admin"))
) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    task.status = "rejected"
    task.decision_data = {"rejected_by": actor.username, "reason": payload.reason or "不满足当前审批条件"}
    task.decided_at = utc_now()
    ticket.status = "resolved"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content=f"抱歉，本次申请未获批准。原因：{task.decision_data['reason']}。"))
    db.add(AuditLog(ticket_id=ticket.id, action="reject_approval_task", operator_type=actor.role, input_data={"approval_task_id": task.id, "task_type": task.task_type}, output_data=task.decision_data))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.post("/approvals/{task_id}/assign-supervisor", response_model=TicketDetail)
def assign_refund_review_to_supervisor(
    task_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), actor: Actor = Depends(require_roles("supervisor", "admin"))
) -> Ticket:
    task = get_approval_task_or_404(db, task_id)
    if task.task_type != "refund_review":
        raise HTTPException(status_code=409, detail="该任务不是退款复核任务")
    ticket = get_ticket_or_404(db, task.ticket_id, for_update=True)
    task.status = "in_review"
    task.decision_data = {"assigned_to": actor.username, "note": payload.reason or "已转主管复核"}
    task.decided_at = utc_now()
    ticket.status = "escalated"
    db.add(TicketMessage(ticket_id=ticket.id, sender_type="agent", content="您的退款诉求已转交主管复核，我们将在核验材料后反馈处理结果。"))
    db.add(AuditLog(ticket_id=ticket.id, action="assign_refund_review_to_supervisor", operator_type=actor.role, input_data={"approval_task_id": task.id}, output_data=task.decision_data))
    db.commit()
    return get_ticket_detail(db, ticket.id)


@router.get("/knowledge/documents", response_model=list[KnowledgeDocumentRead], dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def list_knowledge_documents(db: Session = Depends(get_db)) -> list[KnowledgeDocument]:
    return list(
        db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.id)).all()
    )


def get_knowledge_document_or_404(db: Session, document_id: int) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    return document


@router.post("/knowledge/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles("admin"))])
def create_knowledge_document(
    payload: KnowledgeDocumentCreate, db: Session = Depends(get_db)
) -> KnowledgeDocument:
    cleaned_content = clean_document_text(payload.content)
    document = KnowledgeDocument(
        **payload.model_dump(exclude={"content"}),
        content=cleaned_content,
        source_name="运营手工录入",
        source_type="manual",
        source_metadata={"cleaning": "unicode_nfkc/control_characters/blank_lines"},
        content_hash=content_fingerprint(cleaned_content),
        ingestion_status="published" if payload.is_active else "draft",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.post(
    "/knowledge/documents/ingest",
    response_model=KnowledgeIngestionResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("admin"))],
)
async def ingest_knowledge_document(
    file: UploadFile = File(...),
    category: str = Form(default="after_sales"),
    version: str = Form(default="v1.0"),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> KnowledgeIngestionResult:
    filename = file.filename or "untitled.txt"
    try:
        prepared = prepare_uploaded_corpus(filename, await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fingerprint = content_fingerprint(prepared.cleaned_content)
    duplicate = db.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.content_hash == fingerprint))
    if duplicate:
        raise HTTPException(status_code=409, detail="检测到相同内容已导入知识库")

    document_title = (title or filename.rsplit(".", 1)[0]).strip()
    if len(document_title) < 2 or len(document_title) > 255:
        raise HTTPException(status_code=400, detail="文档标题长度应为 2 到 255 个字符")
    if not category.strip() or len(category) > 50 or not version.strip() or len(version) > 50:
        raise HTTPException(status_code=400, detail="分类或版本格式不正确")

    document = KnowledgeDocument(
        title=document_title,
        content=prepared.cleaned_content,
        category=category.strip(),
        version=version.strip(),
        is_active=False,
        source_name=filename,
        source_type=prepared.source_type,
        source_metadata=prepared.source_metadata,
        content_hash=fingerprint,
        ingestion_status="draft",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return KnowledgeIngestionResult(
        document=document,
        cleaned_characters=len(prepared.cleaned_content),
        chunk_count=len(prepared.chunks),
        preview_chunks=prepared.chunks[:3],
    )


@router.patch("/knowledge/documents/{document_id}", response_model=KnowledgeDocumentRead, dependencies=[Depends(require_roles("admin"))])
def update_knowledge_document(
    document_id: int, payload: KnowledgeDocumentUpdate, db: Session = Depends(get_db)
) -> KnowledgeDocument:
    document = get_knowledge_document_or_404(db, document_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    if "content" in changes:
        changes["content"] = clean_document_text(changes["content"])
        changes["content_hash"] = content_fingerprint(changes["content"])
    if "is_active" in changes:
        changes["ingestion_status"] = "published" if changes["is_active"] else "draft"
    for field, value in changes.items():
        setattr(document, field, value)
    db.commit()
    db.refresh(document)
    return document


@router.post("/knowledge/reindex", response_model=KnowledgeReindexResult, dependencies=[Depends(require_roles("admin"))])
def sync_knowledge_index(db: Session = Depends(get_db)) -> KnowledgeReindexResult:
    try:
        document_count, chunk_count, collection_name, generation = reindex_knowledge(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"知识库同步失败：{type(exc).__name__}") from exc
    return KnowledgeReindexResult(
        document_count=document_count,
        chunk_count=chunk_count,
        collection_name=collection_name,
        generation=generation,
    )


@router.post("/knowledge/evaluations", response_model=KnowledgeEvaluationRunRead, dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def evaluate_knowledge_index(db: Session = Depends(get_db)) -> KnowledgeEvaluationRun:
    try:
        return run_rag_evaluation(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"知识库评测失败：{type(exc).__name__}") from exc


@router.get("/knowledge/evaluations", response_model=list[KnowledgeEvaluationRunRead], dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def list_knowledge_evaluations(
    limit: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)
) -> list[KnowledgeEvaluationRun]:
    return list(
        db.scalars(
            select(KnowledgeEvaluationRun)
            .order_by(KnowledgeEvaluationRun.created_at.desc())
            .limit(limit)
        ).all()
    )


@router.post("/knowledge/search", response_model=list[KnowledgeSearchResult], dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
def search_knowledge(
    payload: KnowledgeSearchRequest, db: Session = Depends(get_db)
) -> list[KnowledgeSearchResult]:
    return [
        KnowledgeSearchResult(**source.__dict__)
        for source in retrieve_knowledge(
            db, payload.query, payload.limit, category=payload.category
        )
    ]


@router.get("/orders/{order_no}", response_model=OrderDetail, dependencies=[Depends(require_roles("agent", "supervisor", "admin"))])
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
