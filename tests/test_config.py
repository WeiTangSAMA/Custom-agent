from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import AppSettings


def test_collections_must_be_isolated() -> None:
    with pytest.raises(ValidationError):
        AppSettings(
            storage={
                "knowledge_collection": "same",
                "memory_collection": "same",
            }
        )


def test_missing_credentials_do_not_prevent_settings(settings: AppSettings) -> None:
    assert settings.model_configured is False
    assert settings.embedding.model == "text-embedding-v4"
    assert settings.embedding.dimensions == 1024
    assert settings.embedding.batch_size == 10
