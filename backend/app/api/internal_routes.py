import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.internal_schemas import CaseAnalysisRequest, CaseAnalysisResult
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
    list_agent_runs,
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
    _: None = Depends(require_internal_token),
) -> CaseAnalysisResult:
    return analyze_case_snapshot(payload)


@router.get("/admin/agent-runs", response_model=list[AgentRunQueueItem])
def internal_agent_runs(
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    _: None = Depends(require_internal_token),
) -> list[AgentRunQueueItem]:
    return list_agent_runs(limit=limit, db=db)


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
