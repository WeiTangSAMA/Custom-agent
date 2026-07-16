from __future__ import annotations

from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from app.config import AppSettings
from app.errors import ModelNotConfiguredError


class VectorStores:
    """Owns two isolated Chroma collections and lazily attaches embeddings."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        settings.storage.chroma_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(settings.storage.chroma_directory))
        metadata = {"hnsw:space": "cosine"}
        self.knowledge_collection = self.client.get_or_create_collection(
            settings.storage.knowledge_collection, metadata=metadata
        )
        self.memory_collection = self.client.get_or_create_collection(
            settings.storage.memory_collection, metadata=metadata
        )
        self._embeddings: OpenAIEmbeddings | None = None
        self._knowledge_store: Chroma | None = None
        self._memory_store: Chroma | None = None

    def _require_embeddings(self) -> OpenAIEmbeddings:
        if not self.settings.model_configured:
            raise ModelNotConfiguredError(
                "Set DASHSCOPE_API_KEY and DASHSCOPE_BASE_URL before using model-backed operations"
            )
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=self.settings.embedding.model,
                dimensions=self.settings.embedding.dimensions,
                chunk_size=self.settings.embedding.batch_size,
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                max_retries=self.settings.llm.max_retries,
                request_timeout=self.settings.llm.timeout_seconds,
                # Bailian's OpenAI-compatible endpoint accepts text (or a list
                # of texts), but not the token-id arrays LangChain otherwise
                # creates while checking the embedding context length.
                check_embedding_ctx_length=False,
            )
        return self._embeddings

    @property
    def knowledge_store(self) -> Chroma:
        if self._knowledge_store is None:
            self._knowledge_store = Chroma(
                client=self.client,
                collection_name=self.settings.storage.knowledge_collection,
                embedding_function=self._require_embeddings(),
            )
        return self._knowledge_store

    @property
    def memory_store(self) -> Chroma:
        if self._memory_store is None:
            self._memory_store = Chroma(
                client=self.client,
                collection_name=self.settings.storage.memory_collection,
                embedding_function=self._require_embeddings(),
            )
        return self._memory_store

    def counts(self) -> dict[str, int]:
        return {
            "knowledge_chunks": self.knowledge_collection.count(),
            "long_term_memories": self.memory_collection.count(),
        }

    @staticmethod
    def records(collection: Any) -> list[dict[str, Any]]:
        raw = collection.get(include=["documents", "metadatas"])
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []
        return [
            {"id": item_id, "document": documents[index], "metadata": metadatas[index] or {}}
            for index, item_id in enumerate(raw.get("ids") or [])
        ]
