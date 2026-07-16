from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx


class APIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AgentAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def _client(self, timeout: float | httpx.Timeout = 30.0) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=self._transport,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float | httpx.Timeout = 30.0,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            with self._client(timeout) as client:
                response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise APIError(
                f"无法连接 FastAPI 服务（{self.base_url}）。请使用 run.ps1 或 python streamlit_app.py 启动项目。"
            ) from exc
        self._raise_for_status(response)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
            detail = body.get("detail", body)
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("code") or str(detail)
            else:
                message = str(detail)
        except (ValueError, TypeError):
            message = response.text or f"HTTP {response.status_code}"
        raise APIError(message, response.status_code)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=5.0).json()

    def list_documents(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/documents").json()

    def upload_documents(self, files: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        payload = [("files", (name, content, mime_type)) for name, content, mime_type in files]
        return self._request(
            "POST",
            "/api/v1/documents/upload",
            timeout=httpx.Timeout(120.0),
            files=payload,
        ).json()

    def delete_document(self, source_id: str) -> None:
        self._request("DELETE", f"/api/v1/documents/{source_id}")

    def list_conversations(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/conversations").json()

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/conversations/{conversation_id}").json()

    def delete_conversation(self, conversation_id: str) -> None:
        self._request("DELETE", f"/api/v1/conversations/{conversation_id}")

    def list_memories(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        return self._request(
            "GET", "/api/v1/memories", params={"offset": offset, "limit": limit}
        ).json()

    def search_memories(self, query: str, limit: int = 10) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/memories/search",
            timeout=httpx.Timeout(60.0),
            json={"query": query, "limit": limit},
        ).json()

    def delete_memory(self, memory_id: str) -> None:
        self._request("DELETE", f"/api/v1/memories/{memory_id}")

    def clear_memories(self) -> int:
        response = self._request(
            "DELETE", "/api/v1/memories", json={"confirm": True}
        )
        return int(response.json().get("deleted", 0))

    def stream_chat(
        self,
        question: str,
        conversation_id: str | None,
        request_id: str,
    ) -> Iterator[dict[str, Any]]:
        payload = {
            "question": question,
            "conversation_id": conversation_id,
            "request_id": request_id,
        }
        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
        try:
            with self._client(timeout) as client:
                with client.stream("POST", "/api/v1/chat/stream", json=payload) as response:
                    self._raise_for_status(response)
                    event_name = "message"
                    data_lines: list[str] = []
                    for line in response.iter_lines():
                        if not line:
                            if data_lines:
                                raw = "\n".join(data_lines)
                                try:
                                    data = json.loads(raw)
                                except json.JSONDecodeError:
                                    data = {"text": raw}
                                yield {"event": event_name, "data": data}
                            event_name = "message"
                            data_lines = []
                        elif line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                    if data_lines:
                        raw = "\n".join(data_lines)
                        yield {"event": event_name, "data": json.loads(raw)}
        except httpx.HTTPError as exc:
            raise APIError(
                f"与 FastAPI 服务的连接中断（{self.base_url}）。"
            ) from exc
