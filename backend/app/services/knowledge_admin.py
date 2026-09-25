import logging

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeDocument
from app.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeIngestionResult,
    KnowledgeReindexResult,
)
from app.services.knowledge_service import (
    clean_document_text,
    content_fingerprint,
    prepare_uploaded_corpus,
    reindex_knowledge,
)


logger = logging.getLogger(__name__)


def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.id)).all())


def get_document(db: Session, document_id: int) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    return document


def create_document(payload: KnowledgeDocumentCreate, db: Session) -> KnowledgeDocument:
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


async def ingest_document(
    file: UploadFile,
    category: str,
    version: str,
    title: str | None,
    db: Session,
) -> KnowledgeIngestionResult:
    filename = file.filename or "untitled.txt"
    try:
        prepared = prepare_uploaded_corpus(filename, await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fingerprint = content_fingerprint(prepared.cleaned_content)
    duplicate = db.scalar(
        select(KnowledgeDocument.id).where(KnowledgeDocument.content_hash == fingerprint)
    )
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


def update_document(
    document_id: int, payload: KnowledgeDocumentUpdate, db: Session
) -> KnowledgeDocument:
    document = get_document(db, document_id)
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


def rebuild_index(db: Session) -> KnowledgeReindexResult:
    try:
        document_count, chunk_count, collection_name, generation = reindex_knowledge(db)
    except Exception as exc:
        db.rollback()
        logger.exception("Knowledge index rebuild failed")
        raise HTTPException(status_code=503, detail=f"知识库同步失败：{type(exc).__name__}") from exc
    return KnowledgeReindexResult(
        document_count=document_count,
        chunk_count=chunk_count,
        collection_name=collection_name,
        generation=generation,
    )
