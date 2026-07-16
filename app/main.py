from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import AppSettings, load_settings
from app.database import ChatDatabase
from app.errors import ModelNotConfiguredError, NotFoundError
from app.schemas import ChatRequest, ClearMemoriesRequest, DirectoryIngestRequest, MemorySearchRequest
from app.services.agent import AgentService
from app.services.documents import DocumentService
from app.services.memory import MemoryService
from app.vectorstores import VectorStores


logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.database = ChatDatabase(settings.storage.sqlite_path)
        self.vectors = VectorStores(settings)
        self.documents = DocumentService(settings, self.vectors)
        self.memories = MemoryService(settings, self.vectors)
        self.agent = AgentService(settings, self.documents, self.memories)

    def close(self) -> None:
        self.database.close()


def _runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def _require_model(runtime: Runtime) -> None:
    if not runtime.settings.model_configured:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_NOT_CONFIGURED",
                "message": "Set DASHSCOPE_API_KEY and DASHSCOPE_BASE_URL in .env",
            },
        )


def _valid_conversation_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="conversation_id must be a UUID") from exc


def _turn_id(conversation_id: str, request_id: str | None) -> str:
    if request_id:
        return str(uuid5(NAMESPACE_URL, f"turn:{conversation_id}:{request_id}"))
    return str(uuid4())


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(settings: AppSettings | None = None) -> FastAPI:
    selected_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = Runtime(selected_settings)
        yield
        app.state.runtime.close()

    app = FastAPI(
        title="Qwen RAG Agent",
        version="0.1.0",
        description="LangChain agent with project RAG and durable semantic memory",
        lifespan=lifespan,
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        runtime = _runtime(request)
        return {
            "status": "ok" if runtime.database.healthy() else "degraded",
            "model_configured": runtime.settings.model_configured,
            "sqlite": runtime.database.healthy(),
            "collections": {
                "knowledge": runtime.settings.storage.knowledge_collection,
                "memory": runtime.settings.storage.memory_collection,
            },
            **runtime.vectors.counts(),
            "document_sources": len(runtime.documents.list_sources()),
        }

    @app.post("/api/v1/documents/upload")
    async def upload_documents(request: Request, files: list[UploadFile] = File(...)) -> dict[str, Any]:
        runtime = _runtime(request)
        _require_model(runtime)
        results: list[dict[str, Any]] = []
        max_bytes = runtime.settings.documents.max_file_size_mb * 1024 * 1024
        for upload in files:
            try:
                content = await upload.read(max_bytes + 1)
                results.append(runtime.documents.ingest_bytes(content, upload.filename or "unnamed.txt"))
            except Exception as exc:
                results.append({"filename": upload.filename, "status": "failed", "error": str(exc)})
            finally:
                await upload.close()
        return {"results": results}

    @app.post("/api/v1/documents/ingest-directory")
    def ingest_directory(payload: DirectoryIngestRequest, request: Request) -> dict[str, Any]:
        runtime = _runtime(request)
        _require_model(runtime)
        path = Path(payload.path) if payload.path else None
        if path is not None and not path.is_absolute():
            path = runtime.settings.project_root / path
        try:
            return runtime.documents.ingest_directory(path, payload.recursive)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/documents")
    def list_documents(request: Request) -> dict[str, Any]:
        items = _runtime(request).documents.list_sources()
        return {"total": len(items), "items": items}

    @app.delete("/api/v1/documents/{source_id}", status_code=204)
    def delete_document(source_id: str, request: Request) -> None:
        _runtime(request).documents.delete_source(source_id)

    @app.post("/api/v1/chat/stream")
    async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
        runtime = _runtime(request)
        _require_model(runtime)
        conversation_id = _valid_conversation_id(payload.conversation_id)
        turn_id = _turn_id(conversation_id, payload.request_id)
        cached_answer = runtime.database.completed_answer(turn_id)
        history = runtime.database.recent_messages(
            conversation_id, runtime.settings.chat.recent_message_limit
        ) if payload.conversation_id else []
        recent_turn_ids = {item["turn_id"] for item in history}
        runtime.database.start_turn(conversation_id, turn_id, payload.question)

        async def events():
            yield _sse("meta", {"conversation_id": conversation_id, "turn_id": turn_id})
            if cached_answer is not None:
                yield _sse("token", {"text": cached_answer})
                yield _sse("done", {"cached": True, "memory_saved": True})
                return

            answer = ""
            completion: dict[str, Any] = {}
            try:
                async for item in runtime.agent.stream(payload.question, history, recent_turn_ids):
                    if await request.is_disconnected():
                        raise asyncio.CancelledError()
                    if item["event"] == "complete":
                        completion = item["data"]
                        answer = completion.pop("answer")
                    else:
                        yield _sse(item["event"], item["data"])
                yield _sse(
                    "status",
                    {"stage": "memory", "message": "正在保存本轮记忆…"},
                )
                memory_id = runtime.memories.store_turn(
                    conversation_id, turn_id, payload.question, answer
                )
                try:
                    runtime.database.complete_turn(conversation_id, turn_id, answer)
                except Exception:
                    runtime.memories.delete_memory(memory_id)
                    raise
                yield _sse(
                    "done",
                    {**completion, "cached": False, "memory_saved": True, "memory_id": memory_id},
                )
            except asyncio.CancelledError:
                runtime.database.fail_turn(turn_id, "client_disconnected")
                raise
            except Exception as exc:
                logger.exception("Agent turn failed", exc_info=exc)
                runtime.database.fail_turn(turn_id, type(exc).__name__)
                yield _sse(
                    "error",
                    {"code": "AGENT_RUN_FAILED", "message": "Agent request failed; no long-term memory was saved"},
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/conversations")
    def list_conversations(request: Request) -> dict[str, Any]:
        items = _runtime(request).database.list_conversations()
        return {"total": len(items), "items": items}

    @app.get("/api/v1/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
        return _runtime(request).database.get_conversation(conversation_id)

    @app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str, request: Request) -> None:
        runtime = _runtime(request)
        runtime.database.get_conversation(conversation_id, include_messages=False)
        runtime.memories.delete_conversation(conversation_id)
        runtime.database.delete_conversation(conversation_id)

    @app.get("/api/v1/memories")
    def list_memories(
        request: Request,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        return _runtime(request).memories.list_memories(offset, limit)

    @app.post("/api/v1/memories/search")
    def search_memories(payload: MemorySearchRequest, request: Request) -> dict[str, Any]:
        runtime = _runtime(request)
        _require_model(runtime)
        items = runtime.memories.search(payload.query, payload.limit)
        return {"total": len(items), "items": items}

    @app.delete("/api/v1/memories/{memory_id}", status_code=204)
    def delete_memory(memory_id: str, request: Request) -> None:
        _runtime(request).memories.delete_memory(memory_id)

    @app.delete("/api/v1/memories")
    def clear_memories(payload: ClearMemoriesRequest, request: Request) -> dict[str, Any]:
        if not payload.confirm:
            raise HTTPException(status_code=400, detail="Set confirm=true to clear memories")
        deleted = _runtime(request).memories.clear()
        return {"deleted": deleted}

    return app


app = create_app()
