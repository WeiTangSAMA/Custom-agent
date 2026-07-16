from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from app.config import AppSettings
from app.errors import NotFoundError
from app.vectorstores import VectorStores


SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{10,}={0,2}"),
    re.compile(r"(?i)(password|passwd|pwd|api[_-]?key)\s*[:=]\s*([^\s,;]+)"),
)


def redact_secrets(text: str) -> str:
    sanitized = SECRET_PATTERNS[0].sub("[REDACTED_API_KEY]", text)
    sanitized = SECRET_PATTERNS[1].sub("Bearer [REDACTED_TOKEN]", sanitized)
    sanitized = SECRET_PATTERNS[2].sub(lambda match: f"{match.group(1)}=[REDACTED]", sanitized)
    return sanitized


class MemoryService:
    def __init__(self, settings: AppSettings, vectors: VectorStores):
        self.settings = settings
        self.vectors = vectors

    @staticmethod
    def memory_id(conversation_id: str, turn_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"memory:{conversation_id}:{turn_id}"))

    def store_turn(self, conversation_id: str, turn_id: str, question: str, answer: str) -> str:
        memory_id = self.memory_id(conversation_id, turn_id)
        content = redact_secrets(f"User: {question}\nAssistant: {answer}")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        created_at = datetime.now(UTC).isoformat()
        document = Document(
            page_content=content,
            metadata={
                "memory_id": memory_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "created_at": created_at,
                "content_hash": content_hash,
                "memory_type": "conversation_turn",
            },
        )
        self.vectors.memory_collection.delete(ids=[memory_id])
        self.vectors.memory_store.add_documents([document], ids=[memory_id])
        return memory_id

    def search(self, query: str, limit: int | None = None, excluded_turn_ids: set[str] | None = None) -> list[dict[str, Any]]:
        excluded = excluded_turn_ids or set()
        requested = limit or self.settings.retrieval.memory_top_k
        candidates = self.vectors.memory_store.similarity_search_with_relevance_scores(
            query, k=max(requested + len(excluded), requested * 2)
        )
        results: list[dict[str, Any]] = []
        for doc, score in candidates:
            if doc.metadata.get("turn_id") in excluded:
                continue
            results.append(
                {
                    "type": "memory",
                    "content": doc.page_content,
                    "score": score,
                    "memory_id": doc.metadata.get("memory_id"),
                    "conversation_id": doc.metadata.get("conversation_id"),
                    "turn_id": doc.metadata.get("turn_id"),
                    "created_at": doc.metadata.get("created_at"),
                }
            )
            if len(results) >= requested:
                break
        return results

    def list_memories(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        records = self.vectors.records(self.vectors.memory_collection)
        records.sort(key=lambda item: item["metadata"].get("created_at", ""), reverse=True)
        items = [
            {"memory_id": item["id"], "content": item["document"], **item["metadata"]}
            for item in records[offset : offset + limit]
        ]
        return {"total": len(records), "offset": offset, "limit": limit, "items": items}

    def delete_memory(self, memory_id: str) -> None:
        existing = self.vectors.memory_collection.get(ids=[memory_id])
        if not existing.get("ids"):
            raise NotFoundError("Memory not found")
        self.vectors.memory_collection.delete(ids=[memory_id])

    def delete_conversation(self, conversation_id: str) -> None:
        self.vectors.memory_collection.delete(where={"conversation_id": conversation_id})

    def clear(self) -> int:
        count = self.vectors.memory_collection.count()
        records = self.vectors.memory_collection.get()
        if records.get("ids"):
            self.vectors.memory_collection.delete(ids=records["ids"])
        return count

