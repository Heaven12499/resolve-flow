import logging
import hashlib
import math
import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexState, utc_now


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


@dataclass(frozen=True)
class PreparedCorpus:
    cleaned_content: str
    source_type: str
    source_metadata: dict[str, object]
    chunks: list[str]


SUPPORTED_CORPUS_SUFFIXES = {".txt": "text", ".md": "markdown", ".csv": "csv"}
MAX_CORPUS_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 2_000


def expand_retrieval_query(query: str) -> str:
    """Add explicit business synonyms before local n-gram retrieval.

    This is a deterministic query-rewrite layer for the lightweight local
    embedder. It is intentionally auditable and does not alter the customer
    message or any risk decision.
    """
    additions: list[str] = []
    rewrite_rules = (
        (("没有更新", "未更新", "卡住"), "物流停滞 72小时 未更新"),
        (("三天", "三日"), "72小时 配送延迟"),
        (("坏了", "坏的", "破损", "损坏"), "商品质量问题 损坏 证据照片视频"),
        (("什么材料", "提供材料", "补充材料"), "订单信息 证据 照片 视频 签收情况"),
        (("颜色不一样", "货不对板", "发错"), "颜色型号规格不符 错发漏发"),
        (("没有揽收", "未揽收"), "发货 揽收异常 物流记录"),
    )
    for keywords, expansion in rewrite_rules:
        if any(keyword in query for keyword in keywords):
            additions.append(expansion)
    return f"{query} {' '.join(additions)}".strip()


def clean_document_text(content: str) -> str:
    """Normalize a human-authored policy while preserving paragraphs for audit."""
    normalized = unicodedata.normalize("NFKC", content).replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\ufeff", "").replace("\u200b", "")
    normalized = "".join(character for character in normalized if character == "\n" or character == "\t" or ord(character) >= 32)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def content_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _decode_corpus(payload: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("文件编码无法识别，请保存为 UTF-8 或 GB18030 后重试")


def _csv_to_text(content: str) -> tuple[str, int, list[str]]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV 至少需要一行表头")
    rows: list[str] = []
    for row_number, row in enumerate(reader, start=1):
        if row_number > MAX_CSV_ROWS:
            raise ValueError(f"CSV 行数超过 {MAX_CSV_ROWS} 条限制")
        fields = [f"{key}：{value.strip()}" for key, value in row.items() if key and value and value.strip()]
        if fields:
            rows.append("；".join(fields))
    if not rows:
        raise ValueError("CSV 中没有可用的文本内容")
    return "\n".join(rows), len(rows), [field.strip() for field in reader.fieldnames if field.strip()]


def prepare_uploaded_corpus(filename: str, payload: bytes) -> PreparedCorpus:
    """Parse supported business corpus files into a reviewable draft document."""
    suffix = Path(filename).suffix.lower()
    source_type = SUPPORTED_CORPUS_SUFFIXES.get(suffix)
    if not source_type:
        raise ValueError("仅支持 .txt、.md、.csv 格式")
    if not payload:
        raise ValueError("上传文件为空")
    if len(payload) > MAX_CORPUS_BYTES:
        raise ValueError("单个语料文件不能超过 2MB")

    decoded, encoding = _decode_corpus(payload)
    row_count: int | None = None
    columns: list[str] | None = None
    if source_type == "csv":
        decoded, row_count, columns = _csv_to_text(decoded)
    cleaned = clean_document_text(decoded)
    if len(cleaned) < 10:
        raise ValueError("清洗后有效文本不足 10 个字符")
    chunks = split_document(cleaned)
    return PreparedCorpus(
        cleaned_content=cleaned,
        source_type=source_type,
        source_metadata={
            "original_filename": filename,
            "size_bytes": len(payload),
            "encoding": encoding,
            "row_count": row_count,
            "columns": columns,
            "cleaning": "unicode_nfkc/control_characters/blank_lines",
            "chunking": {"chunk_size": 240, "overlap": 40},
        },
        chunks=chunks,
    )


def split_document(content: str, chunk_size: int = 240, overlap: int = 40) -> list[str]:
    normalized = clean_document_text(content)
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


def reindex_knowledge(db: Session) -> tuple[int, int, str, str]:
    """Build a fresh index generation, then atomically switch future reads to it."""
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

    generation = utc_now().strftime("%Y%m%d%H%M%S%f")
    collection_name = f"{settings.milvus_collection_name}_{generation}"
    chunks = [
        KnowledgeChunk(document_id=document.id, chunk_index=index, index_generation=generation, content=chunk)
        for document, index, chunk in chunk_specs
    ]
    db.add_all(chunks)
    db.flush()

    client = get_milvus_client()
    client.create_collection(
        collection_name=collection_name,
        dimension=settings.embedding_dimension,
        metric_type="COSINE",
        auto_id=False,
    )
    client.insert(
        collection_name=collection_name,
        data=[
            {"id": chunk.id, "vector": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )
    # Insert acknowledgement does not guarantee that a new Milvus collection is
    # immediately searchable.  Finish persistence and loading before moving the
    # active-index pointer; otherwise a reindex followed by an evaluation can
    # observe an empty collection.
    client.flush(collection_name)
    client.load_collection(collection_name)
    state = db.get(KnowledgeIndexState, 1)
    if state:
        state.collection_name = collection_name
        state.generation = generation
        state.document_count = len(documents)
        state.chunk_count = len(chunks)
    else:
        db.add(KnowledgeIndexState(id=1, collection_name=collection_name, generation=generation, document_count=len(documents), chunk_count=len(chunks)))
    db.commit()
    return len(documents), len(chunks), collection_name, generation


def retrieve_knowledge(
    db: Session, query: str, limit: int = 3, category: str | None = None
) -> list[KnowledgeSource]:
    if not settings.rag_enabled:
        return []
    try:
        client = get_milvus_client()
        state = db.get(KnowledgeIndexState, 1)
        collection_name = state.collection_name if state else settings.milvus_collection_name
        if not client.has_collection(collection_name):
            return []
        query_vector = embed_texts([expand_retrieval_query(query)])[0]
        hits = client.search(
            collection_name=collection_name,
            data=[query_vector],
            # Retrieve a wider global candidate pool before applying the MySQL
            # category filter, otherwise relevant category hits can be lost.
            limit=max(limit * 4, 12),
        )[0]
        scores = {
            int(hit["id"]): float(hit.get("distance", 0.0))
            for hit in hits
            if float(hit.get("distance", 0.0)) >= settings.rag_min_score
        }
        if not scores:
            return []
        statement = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.id.in_(scores))
            .options(selectinload(KnowledgeChunk.document))
        )
        if state:
            statement = statement.where(KnowledgeChunk.index_generation == state.generation)
        if category:
            statement = statement.where(
                KnowledgeChunk.document.has(KnowledgeDocument.category == category)
            )
        rows = list(db.scalars(statement).all())
        ranked_rows = sorted(rows, key=lambda item: scores[item.id], reverse=True)[:limit]
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
            for chunk in ranked_rows
        ]
    except Exception as exc:  # RAG is advisory; a vector outage must not block support.
        logger.warning("Knowledge retrieval unavailable: %s", type(exc).__name__)
        return []
