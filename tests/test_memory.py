from __future__ import annotations

from app.services.memory import MemoryService, redact_secrets


def test_secret_redaction() -> None:
    text = "api_key=sk-abcdefghijklmnopqrstuvwxyz Bearer abcdefghijklmnop password: hunter2"
    redacted = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("REDACTED") >= 3


def test_memory_id_is_deterministic() -> None:
    first = MemoryService.memory_id("conversation", "turn")
    second = MemoryService.memory_id("conversation", "turn")
    other = MemoryService.memory_id("conversation", "other-turn")
    assert first == second
    assert first != other

