import pytest

from app.services.knowledge_service import embed_texts, prepare_uploaded_corpus, split_document


def test_split_document_preserves_content_and_overlap() -> None:
    content = "甲" * 300

    chunks = split_document(content, chunk_size=120, overlap=20)

    assert len(chunks) == 3
    assert chunks[0] == "甲" * 120
    assert chunks[1] == "甲" * 120
    assert len(chunks[-1]) == 100


def test_local_embeddings_are_normalized_and_repeatable() -> None:
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
