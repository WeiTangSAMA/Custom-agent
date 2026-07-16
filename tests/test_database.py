from __future__ import annotations

from pathlib import Path

from app.database import ChatDatabase


def test_chat_history_is_persistent_and_turn_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "chat.db"
    database = ChatDatabase(path)
    database.start_turn("conversation-1", "turn-1", "hello")
    database.start_turn("conversation-1", "turn-1", "hello")
    database.complete_turn("conversation-1", "turn-1", "world")
    database.close()

    reopened = ChatDatabase(path)
    conversation = reopened.get_conversation("conversation-1")
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert reopened.completed_answer("turn-1") == "world"
    reopened.close()


def test_failed_turn_has_no_assistant_message(tmp_path: Path) -> None:
    database = ChatDatabase(tmp_path / "chat.db")
    database.start_turn("conversation-1", "turn-1", "hello")
    database.fail_turn("turn-1", "client_disconnected")
    conversation = database.get_conversation("conversation-1")
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["status"] == "failed"
    database.close()

