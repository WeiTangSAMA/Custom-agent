from __future__ import annotations

from unittest.mock import patch

from app.vectorstores import VectorStores


def test_collections_are_isolated_and_persistent(settings) -> None:
    vectors = VectorStores(settings)
    vectors.knowledge_collection.add(
        ids=["knowledge-1"],
        documents=["project fact"],
        metadatas=[{"source_id": "source-1"}],
        embeddings=[[1.0, 0.0]],
    )
    vectors.memory_collection.add(
        ids=["memory-1"],
        documents=["old conversation"],
        metadatas=[{"memory_id": "memory-1"}],
        embeddings=[[0.0, 1.0]],
    )
    assert vectors.counts() == {"knowledge_chunks": 1, "long_term_memories": 1}
    assert vectors.knowledge_collection.get(ids=["memory-1"])["ids"] == []
    assert vectors.memory_collection.get(ids=["knowledge-1"])["ids"] == []

    reopened = VectorStores(settings)
    assert reopened.counts() == {"knowledge_chunks": 1, "long_term_memories": 1}


def test_embeddings_send_text_to_bailian_compatible_endpoint(settings) -> None:
    settings.api_key = "test-key"
    settings.base_url = "https://example.com/compatible-mode/v1"

    with patch("app.vectorstores.OpenAIEmbeddings") as embeddings:
        VectorStores(settings)._require_embeddings()

    assert embeddings.call_args.kwargs["check_embedding_ctx_length"] is False
