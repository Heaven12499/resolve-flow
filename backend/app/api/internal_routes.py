import secrets
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.internal_schemas import CaseAnalysisRequest, CaseAnalysisResult
from app.models import AiAnalysisRun
from app.schemas import (
    AgentRunQueueItem,
    KnowledgeDocumentCreate,
    KnowledgeDocumentRead,
    KnowledgeDocumentUpdate,
    KnowledgeIngestionResult,
    KnowledgeReindexResult,
)
from app.services.snapshot_analysis import analyze_case_snapshot
from app.api.routes import (
    create_knowledge_document,
    ingest_knowledge_document,
    list_knowledge_documents,
    sync_knowledge_index,
    update_knowledge_document,
)


router = APIRouter(prefix="/internal/v1", tags=["internal-ai"])


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    expected = settings.internal_api_token
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal service token",
        )


@router.post("/ai/analyze", response_model=CaseAnalysisResult)
def analyze_case(
    payload: CaseAnalysisRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
) -> CaseAnalysisResult:
    input_data = payload.model_dump(mode="json")
    existing = db.scalar(select(AiAnalysisRun).where(AiAnalysisRun.task_id == payload.task_id))
    if existing and existing.input_data != input_data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task_id is already bound to a different snapshot",
        )
    if existing and existing.status == "completed" and existing.output_data:
        return CaseAnalysisResult.model_validate(existing.output_data)
    if existing and existing.status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI task is already running")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing:
        run = existing
        run.status = "running"
        run.input_data = input_data
        run.output_data = None
        run.error = None
        run.duration_ms = 0
        run.started_at = now
        run.finished_at = None
    else:
        run = AiAnalysisRun(
            task_id=payload.task_id,
            ticket_id=payload.ticket_id,
            business_version=payload.business_version,
            status="running",
            input_data=input_data,
            started_at=now,
        )
        db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(AiAnalysisRun).where(AiAnalysisRun.task_id == payload.task_id)
        )
        if concurrent and concurrent.status == "completed" and concurrent.output_data:
            return CaseAnalysisResult.model_validate(concurrent.output_data)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI task is already running")

    started = perf_counter()
    try:
        result = analyze_case_snapshot(payload)
        run.provider = result.model_source
        run.output_data = result.model_dump(mode="json")
        run.status = "completed"
        run.duration_ms = max(0, round((perf_counter() - started) * 1000))
        run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        failed_run = db.scalar(
            select(AiAnalysisRun).where(AiAnalysisRun.task_id == payload.task_id)
        )
        if failed_run:
            failed_run.status = "failed"
            failed_run.error = f"{type(exc).__name__}: {exc}"[:500]
            failed_run.duration_ms = max(0, round((perf_counter() - started) * 1000))
            failed_run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
        raise


@router.get("/admin/agent-runs", response_model=list[AgentRunQueueItem])
def internal_agent_runs(
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
) -> list[AgentRunQueueItem]:
    runs = db.scalars(
        select(AiAnalysisRun).order_by(AiAnalysisRun.started_at.desc()).limit(limit)
    ).all()
    return [
        AgentRunQueueItem(
            id=run.id,
            sequence=1,
            agent_name="snapshot_analysis",
            status=run.status,
            provider=run.provider or "unknown",
            model=run.model,
            input_data=run.input_data,
            output_data=run.output_data,
            error=run.error,
            duration_ms=run.duration_ms,
            started_at=run.started_at,
            finished_at=run.finished_at,
            ticket_id=run.ticket_id,
            ticket_no=run.input_data.get("order", {}).get("order_no", run.task_id),
            ticket_title=run.input_data.get("ticket", {}).get("title", "AI 分析任务"),
            ticket_status="analyzed" if run.status == "completed" else run.status,
        )
        for run in runs
    ]


@router.get("/admin/knowledge/documents", response_model=list[KnowledgeDocumentRead])
def internal_knowledge_documents(
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return list_knowledge_documents(db=db)


@router.post(
    "/admin/knowledge/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def internal_create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return create_knowledge_document(payload=payload, db=db)


@router.patch("/admin/knowledge/documents/{document_id}", response_model=KnowledgeDocumentRead)
def internal_update_knowledge_document(
    document_id: int,
    payload: KnowledgeDocumentUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return update_knowledge_document(document_id=document_id, payload=payload, db=db)


@router.post("/admin/knowledge/documents/ingest", response_model=KnowledgeIngestionResult, status_code=status.HTTP_201_CREATED)
async def internal_ingest_knowledge_document(
    file: UploadFile = File(...),
    category: str = Form(default="after_sales"),
    version: str = Form(default="v1.0"),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return await ingest_knowledge_document(
        file=file, category=category, version=version, title=title, db=db
    )


@router.post("/admin/knowledge/reindex", response_model=KnowledgeReindexResult)
def internal_reindex_knowledge(
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    return sync_knowledge_index(db=db)
