from __future__ import annotations

import httpx
import pytest

from app.ui.api_client import APIError, AgentAPIClient


def test_health_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "model_configured": False})

    client = AgentAPIClient("http://agent.test", transport=httpx.MockTransport(handler))
    assert client.health()["status"] == "ok"


def test_stream_chat_parses_sse_events() -> None:
    body = (
        'event: meta\ndata: {"conversation_id":"c1","turn_id":"t1"}\n\n'
        'event: token\ndata: {"text":"你好"}\n\n'
        'event: done\ndata: {"memory_saved":true}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/stream"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = AgentAPIClient("http://agent.test", transport=httpx.MockTransport(handler))
    events = list(client.stream_chat("hello", None, "request-1"))
    assert [item["event"] for item in events] == ["meta", "token", "done"]
    assert events[1]["data"]["text"] == "你好"


def test_api_errors_surface_backend_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"detail": {"code": "MODEL_NOT_CONFIGURED", "message": "configure model"}},
        )

    client = AgentAPIClient("http://agent.test", transport=httpx.MockTransport(handler))
    with pytest.raises(APIError, match="configure model"):
        client.health()


def test_network_errors_are_translated() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = AgentAPIClient("http://agent.test", transport=httpx.MockTransport(handler))
    with pytest.raises(APIError, match="无法连接 FastAPI"):
        client.health()
