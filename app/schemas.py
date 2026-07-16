from __future__ import annotations

from pydantic import BaseModel, Field


class DirectoryIngestRequest(BaseModel):
    path: str | None = None
    recursive: bool = True


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key. Reuse it when retrying the same turn.",
        max_length=200,
    )


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=4, ge=1, le=50)


class ClearMemoriesRequest(BaseModel):
    confirm: bool = False

