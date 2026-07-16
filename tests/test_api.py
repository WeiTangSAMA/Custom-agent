from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_works_without_credentials(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["model_configured"] is False
        assert response.json()["collections"]["knowledge"] == "project_knowledge"


def test_model_backed_routes_return_503_without_credentials(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"question": "hello"},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


def test_clear_memory_requires_confirmation(settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.request(
            "DELETE", "/api/v1/memories", json={"confirm": False}
        )
        assert response.status_code == 400

