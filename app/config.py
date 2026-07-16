from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LLMConfig(BaseModel):
    model: str = "qwen3.7-plus"
    temperature: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 2


class EmbeddingConfig(BaseModel):
    model: str = "text-embedding-v4"
    dimensions: int = 1024
    batch_size: int = 10


class DocumentsConfig(BaseModel):
    source_directory: Path = Path("data/documents")
    max_file_size_mb: int = 10
    chunk_size: int = 800
    chunk_overlap: int = 120
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".markdown", ".txt"]
    )

    @model_validator(mode="after")
    def validate_chunks(self) -> "DocumentsConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("documents.chunk_overlap must be smaller than chunk_size")
        self.allowed_extensions = [ext.lower() for ext in self.allowed_extensions]
        return self


class RetrievalConfig(BaseModel):
    knowledge_top_k: int = 5
    memory_top_k: int = 4


class StorageConfig(BaseModel):
    chroma_directory: Path = Path("data/chroma")
    knowledge_collection: str = "project_knowledge"
    memory_collection: str = "agent_long_term_memory"
    sqlite_path: Path = Path("data/chat_history.db")

    @model_validator(mode="after")
    def collections_must_differ(self) -> "StorageConfig":
        if self.knowledge_collection == self.memory_collection:
            raise ValueError("knowledge and memory collections must be different")
        return self


class ChatConfig(BaseModel):
    recent_message_limit: int = 20


class AppSettings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    documents: DocumentsConfig = Field(default_factory=DocumentsConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    project_root: Path = PROJECT_ROOT
    api_key: str = ""
    base_url: str = ""

    @property
    def model_configured(self) -> bool:
        return bool(self.api_key.strip() and self.base_url.strip())

    def resolve_paths(self) -> None:
        for owner, field_name in (
            (self.documents, "source_directory"),
            (self.storage, "chroma_directory"),
            (self.storage, "sqlite_path"),
        ):
            value = getattr(owner, field_name)
            if not value.is_absolute():
                setattr(owner, field_name, (self.project_root / value).resolve())


def load_settings(config_path: Path | None = None) -> AppSettings:
    load_dotenv(PROJECT_ROOT / ".env")
    selected = config_path or Path(os.getenv("APP_CONFIG", PROJECT_ROOT / "config.yaml"))
    if not selected.is_absolute():
        selected = (PROJECT_ROOT / selected).resolve()
    raw: dict[str, Any] = {}
    if selected.exists():
        raw = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    settings = AppSettings(
        **raw,
        project_root=PROJECT_ROOT,
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv("DASHSCOPE_BASE_URL", ""),
    )
    settings.resolve_paths()
    return settings
