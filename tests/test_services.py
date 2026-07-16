from __future__ import annotations

from langchain_core.embeddings import DeterministicFakeEmbedding

from app.services.documents import DocumentService
from app.services.memory import MemoryService
from app.vectorstores import VectorStores


def configured_vectors(settings):
    configured = settings.model_copy(deep=True)
    configured.api_key = "fake-key"
    configured.base_url = "https://example.invalid/v1"
    vectors = VectorStores(configured)
    vectors._embeddings = DeterministicFakeEmbedding(size=16)
    return configured, vectors


def test_document_ingest_deduplicates_and_updates(settings) -> None:
    configured, vectors = configured_vectors(settings)
    service = DocumentService(configured, vectors)

    created = service.ingest_bytes("first version".encode(), "guide.md")
    skipped = service.ingest_bytes("first version".encode(), "guide.md")
    updated = service.ingest_bytes("second version".encode(), "guide.md")

    assert created["status"] == "created"
    assert skipped["status"] == "skipped"
    assert updated["status"] == "updated"
    assert len(service.list_sources()) == 1
    assert vectors.memory_collection.count() == 0


def test_memory_is_idempotent_searchable_and_isolated(settings) -> None:
    configured, vectors = configured_vectors(settings)
    service = MemoryService(configured, vectors)

    memory_id = service.store_turn(
        "conversation-1", "turn-1", "remember api_key=sk-abcdefghijklmnop", "saved"
    )
    service.store_turn(
        "conversation-1", "turn-1", "remember api_key=sk-abcdefghijklmnop", "saved"
    )

    assert vectors.memory_collection.count() == 1
    assert vectors.knowledge_collection.count() == 0
    record = vectors.memory_collection.get(ids=[memory_id], include=["documents"])
    assert "sk-abcdefghijklmnop" not in record["documents"][0]
    assert service.search("remember", excluded_turn_ids={"turn-1"}) == []

    service.delete_conversation("conversation-1")
    assert vectors.memory_collection.count() == 0

