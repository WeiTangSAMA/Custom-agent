from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import AppSettings
from app.errors import NotFoundError
from app.vectorstores import VectorStores


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DocumentService:
    def __init__(self, settings: AppSettings, vectors: VectorStores):
        self.settings = settings
        self.vectors = vectors
        self.source_directory = settings.documents.source_directory
        self.source_directory.mkdir(parents=True, exist_ok=True)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.documents.chunk_size,
            chunk_overlap=settings.documents.chunk_overlap,
            separators=["\n\n", "\n", "。", ". ", " ", ""],
        )

    def _validate_path(self, path: Path) -> None:
        if path.suffix.lower() not in self.settings.documents.allowed_extensions:
            raise ValueError(f"Unsupported file extension: {path.suffix}")

    def ingest_bytes(self, content: bytes, filename: str, source_path: Path | None = None) -> dict[str, Any]:
        safe_name = Path(filename).name
        path = (source_path or (self.source_directory / safe_name)).resolve()
        self._validate_path(path)
        max_bytes = self.settings.documents.max_file_size_mb * 1024 * 1024
        if not content:
            raise ValueError("File is empty")
        if len(content) > max_bytes:
            raise ValueError(f"File exceeds {self.settings.documents.max_file_size_mb} MB")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Only UTF-8 text files are supported") from exc
        if not text.strip():
            raise ValueError("File contains no text")

        content_hash = hashlib.sha256(content).hexdigest()
        source_id = str(uuid5(NAMESPACE_URL, str(path).lower()))
        existing = self.vectors.knowledge_collection.get(
            where={"source_id": source_id}, include=["metadatas"]
        )
        existing_metadata = (existing.get("metadatas") or [])
        if existing_metadata and existing_metadata[0].get("content_hash") == content_hash:
            return {
                "filename": safe_name,
                "source_id": source_id,
                "status": "skipped",
                "chunks": len(existing.get("ids") or []),
            }

        status = "updated" if existing.get("ids") else "created"
        chunks = self.splitter.split_text(text)
        imported_at = _now()
        docs: list[Document] = []
        ids: list[str] = []
        for index, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(f"{source_id}:{content_hash}:{index}".encode()).hexdigest()
            ids.append(chunk_id)
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source_id": source_id,
                        "filename": safe_name,
                        "source_path": str(path),
                        "content_hash": content_hash,
                        "chunk_index": index,
                        "imported_at": imported_at,
                    },
                )
            )

        if existing.get("ids"):
            self.vectors.knowledge_collection.delete(where={"source_id": source_id})
        self.vectors.knowledge_store.add_documents(docs, ids=ids)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {"filename": safe_name, "source_id": source_id, "status": status, "chunks": len(docs)}

    def ingest_file(self, path: Path) -> dict[str, Any]:
        path = path.resolve()
        self._validate_path(path)
        return self.ingest_bytes(path.read_bytes(), path.name, source_path=path)

    def ingest_directory(self, path: Path | None, recursive: bool) -> dict[str, Any]:
        directory = (path or self.source_directory).resolve()
        if not directory.exists() or not directory.is_dir():
            raise ValueError("Directory does not exist")
        pattern = "**/*" if recursive else "*"
        files = sorted(
            item for item in directory.glob(pattern)
            if item.is_file() and item.suffix.lower() in self.settings.documents.allowed_extensions
        )
        results: list[dict[str, Any]] = []
        for item in files:
            try:
                results.append(self.ingest_file(item))
            except Exception as exc:  # keep batch ingestion going
                results.append({"filename": item.name, "status": "failed", "error": str(exc)})
        summary = {status: sum(1 for item in results if item.get("status") == status) for status in ("created", "updated", "skipped", "failed")}
        return {"directory": str(directory), "summary": summary, "results": results}

    def list_sources(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for record in self.vectors.records(self.vectors.knowledge_collection):
            metadata = record["metadata"]
            source_id = metadata["source_id"]
            item = grouped.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "filename": metadata.get("filename"),
                    "source_path": metadata.get("source_path"),
                    "content_hash": metadata.get("content_hash"),
                    "imported_at": metadata.get("imported_at"),
                    "chunks": 0,
                },
            )
            item["chunks"] += 1
        return sorted(grouped.values(), key=lambda item: item.get("imported_at") or "", reverse=True)

    def delete_source(self, source_id: str) -> None:
        existing = self.vectors.knowledge_collection.get(where={"source_id": source_id})
        if not existing.get("ids"):
            raise NotFoundError("Document source not found")
        self.vectors.knowledge_collection.delete(where={"source_id": source_id})

    def search(self, query: str, limit: int | None = None) -> list[dict[str, Any]]:
        matches = self.vectors.knowledge_store.similarity_search_with_relevance_scores(
            query, k=limit or self.settings.retrieval.knowledge_top_k
        )
        return [
            {
                "type": "knowledge",
                "content": doc.page_content,
                "score": score,
                "source_id": doc.metadata.get("source_id"),
                "filename": doc.metadata.get("filename"),
                "chunk_index": doc.metadata.get("chunk_index"),
            }
            for doc, score in matches
        ]

