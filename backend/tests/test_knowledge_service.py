import pytest

from app.core.config import settings
from app.db import Base, SessionLocal, engine
from app.models import KnowledgeChunk, KnowledgeDocument, KnowledgeIndexState
from app.services import knowledge_service
from app.services.knowledge_service import embed_texts, expand_retrieval_query, prepare_uploaded_corpus, split_document


@pytest.fixture(autouse=True)
def fake_bge_model(monkeypatch):
    """Keep unit tests deterministic and independent of Hugging Face downloads."""
    class FakeBgeModel:
        def encode(self, texts, **_):
            return [[1.0] + [0.0] * 511 for _ in texts]

    monkeypatch.setattr(knowledge_service, "get_embedding_model", lambda: FakeBgeModel())


def test_split_document_preserves_content_and_overlap() -> None:
    content = "甲" * 300

    chunks = split_document(content, chunk_size=120, overlap=20)

    assert len(chunks) == 3
    assert chunks[0] == "甲" * 120
    assert chunks[1] == "甲" * 120
    assert len(chunks[-1]) == 100


def test_bge_embeddings_are_normalized_and_repeatable() -> None:
    first, second = embed_texts(["物流延迟补偿", "物流延迟补偿"])

    assert len(first) == 512
    assert first == second
    assert round(sum(value * value for value in first), 6) == 1.0


def test_prepare_csv_corpus_tracks_source_and_creates_preview_chunks() -> None:
    prepared = prepare_uploaded_corpus(
        "after-sales-faq.csv",
        "问题,处理规范\n商品损坏,请客户提供照片并转主管复核\n颜色不符,核验订单后处理\n".encode("utf-8"),
    )

    assert prepared.source_type == "csv"
    assert prepared.source_metadata["row_count"] == 2
    assert prepared.source_metadata["columns"] == ["问题", "处理规范"]
    assert "商品损坏" in prepared.cleaned_content
    assert prepared.chunks


def test_prepare_corpus_rejects_unsupported_file_type() -> None:
    with pytest.raises(ValueError, match="仅支持"):
        prepare_uploaded_corpus("policy.pdf", b"not-a-pdf")


def test_query_expansion_adds_auditable_business_synonyms() -> None:
    expanded = expand_retrieval_query("物流三天没有更新，商品坏了需要什么材料")

    assert "物流停滞" in expanded
    assert "商品质量问题" in expanded
    assert "订单信息" in expanded


def test_retrieval_applies_limit_after_category_filter(monkeypatch) -> None:
    class FakeCollection:
        def query(self, **_: object) -> dict[str, list[list[object]]]:
            return {
                "ids": [[str(first_chunk_id), str(second_chunk_id), str(third_chunk_id)]],
                "distances": [[0.1, 0.2, 0.3]],
            }

    class FakeChromaClient:
        def get_collection(self, _: str) -> FakeCollection:
            return FakeCollection()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        documents = [
            KnowledgeDocument(title=f"limit-test-{index}", content="规则", category="limit_test")
            for index in range(3)
        ]
        db.add_all(documents)
        db.flush()
        chunks = [KnowledgeChunk(document_id=document.id, chunk_index=0, content=document.title) for document in documents]
        db.add_all(chunks)
        db.commit()
        first_chunk_id, second_chunk_id, third_chunk_id = (chunk.id for chunk in chunks)

        monkeypatch.setattr(settings, "rag_enabled", True)
        monkeypatch.setattr(knowledge_service, "get_chroma_client", FakeChromaClient)
        results = knowledge_service.retrieve_knowledge(db, "补偿规则", limit=2, category="limit_test")

    assert [result.chunk_id for result in results] == [first_chunk_id, second_chunk_id]


def test_reindex_builds_chroma_collection_before_switching_active_pointer(monkeypatch) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.added: dict[str, object] | None = None

        def add(self, **kwargs: object) -> None:
            self.added = kwargs

    class FakeChromaClient:
        def __init__(self) -> None:
            self.created_name: str | None = None
            self.collection = FakeCollection()

        def create_collection(self, *, name: str, metadata: dict[str, str]) -> FakeCollection:
            self.created_name = name
            assert metadata["hnsw:space"] == "cosine"
            return self.collection

    client = FakeChromaClient()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        document = KnowledgeDocument(
            title="chroma-reindex-test",
            content="物流延迟补偿必须由人工审批后才能发放优惠券。",
            category="logistics",
        )
        db.add(document)
        db.commit()
        monkeypatch.setattr(knowledge_service, "get_chroma_client", lambda: client)

        _, chunk_count, collection_name, generation = knowledge_service.reindex_knowledge(db)
        state = db.get(KnowledgeIndexState, 1)

    assert chunk_count > 0
    assert client.created_name == collection_name
    assert client.collection.added is not None
    assert state is not None
    assert state.collection_name == collection_name
    assert state.generation == generation
