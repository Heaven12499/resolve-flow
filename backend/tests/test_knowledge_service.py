from app.services.knowledge_service import embed_texts, split_document


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
