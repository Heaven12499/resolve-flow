import logging
import hashlib
import math
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeSource:
    chunk_id: int
    document_id: int
    title: str
    category: str
    version: str
    content: str
    score: float


def split_document(content: str, chunk_size: int = 240, overlap: int = 40) -> list[str]:
    normalized = "".join(line.strip() for line in content.splitlines() if line.strip())
    if len(normalized) <= chunk_size:
        return [normalized] if normalized else []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - overlap
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Create deterministic Chinese character n-gram vectors without external models.

    This keeps the interview demo fully local while preserving the RAG flow:
    query -> vector -> Milvus similarity search -> cited knowledge rule.
    """
    if not texts:
        return []
    vectors: list[list[float]] = []
    for text in texts:
        normalized = "".join(text.split()).lower()
        vector = [0.0] * settings.embedding_dimension
        grams = [normalized[index : index + width]
                 for width in (1, 2, 3)
                 for index in range(max(0, len(normalized) - width + 1))]
        for gram in grams or [normalized]:
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % settings.embedding_dimension
            vector[bucket] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        vectors.append([value / magnitude for value in vector] if magnitude else vector)
    return vectors


def get_milvus_client():
    from pymilvus import MilvusClient

    return MilvusClient(uri=settings.milvus_uri)


def reindex_knowledge(db: Session) -> tuple[int, int]:
    """Replace the demo knowledge index after a user explicitly requests a sync."""
    documents = list(
        db.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.is_active.is_(True))
            .order_by(KnowledgeDocument.id)
        ).all()
    )
    chunk_specs = [
        (document, index, chunk)
        for document in documents
        for index, chunk in enumerate(split_document(document.content))
    ]
    vectors = embed_texts([chunk for _, _, chunk in chunk_specs])
    if any(len(vector) != settings.embedding_dimension for vector in vectors):
        raise ValueError("嵌入模型向量维度与配置不一致")

    db.execute(delete(KnowledgeChunk))
    db.flush()
    chunks = [
        KnowledgeChunk(document_id=document.id, chunk_index=index, content=chunk)
        for document, index, chunk in chunk_specs
    ]
    db.add_all(chunks)
    db.flush()

    client = get_milvus_client()
    if client.has_collection(settings.milvus_collection_name):
        client.drop_collection(settings.milvus_collection_name)
    client.create_collection(
        collection_name=settings.milvus_collection_name,
        dimension=settings.embedding_dimension,
        metric_type="COSINE",
        auto_id=False,
    )
    client.insert(
        collection_name=settings.milvus_collection_name,
        data=[
            {"id": chunk.id, "vector": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )
    db.commit()
    return len(documents), len(chunks)


def retrieve_knowledge(db: Session, query: str, limit: int = 3) -> list[KnowledgeSource]:
    if not settings.rag_enabled:
        return []
    try:
        client = get_milvus_client()
        if not client.has_collection(settings.milvus_collection_name):
            return []
        query_vector = embed_texts([query])[0]
        hits = client.search(
            collection_name=settings.milvus_collection_name,
            data=[query_vector],
            limit=limit,
        )[0]
        scores = {int(hit["id"]): float(hit.get("distance", 0.0)) for hit in hits}
        if not scores:
            return []
        rows = list(
            db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.id.in_(scores))
                .options(selectinload(KnowledgeChunk.document))
            ).all()
        )
        return [
            KnowledgeSource(
                chunk_id=chunk.id,
                document_id=chunk.document.id,
                title=chunk.document.title,
                category=chunk.document.category,
                version=chunk.document.version,
                content=chunk.content,
                score=scores[chunk.id],
            )
            for chunk in sorted(rows, key=lambda item: scores[item.id], reverse=True)
        ]
    except Exception as exc:  # RAG is advisory; a vector outage must not block support.
        logger.warning("Knowledge retrieval unavailable: %s", type(exc).__name__)
        return []
