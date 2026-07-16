from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppSettings


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    value = AppSettings(
        storage={
            "chroma_directory": tmp_path / "chroma",
            "sqlite_path": tmp_path / "chat.db",
            "knowledge_collection": "project_knowledge",
            "memory_collection": "agent_long_term_memory",
        },
        documents={"source_directory": tmp_path / "documents"},
        project_root=tmp_path,
        api_key="",
        base_url="",
    )
    value.resolve_paths()
    return value

