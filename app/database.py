from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.errors import NotFoundError


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ChatDatabase:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed')),
                    error TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(turn_id, role),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                    ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_conversation(self, conversation_id: str, question: str) -> dict[str, Any]:
        now = utc_now()
        title = question.strip().replace("\n", " ")[:80] or "New conversation"
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title, now, now),
            )
        return self.get_conversation(conversation_id, include_messages=False)

    def start_turn(self, conversation_id: str, turn_id: str, question: str) -> None:
        self.create_conversation(conversation_id, question)
        now = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO messages
                    (id, conversation_id, turn_id, role, content, status, created_at)
                VALUES (?, ?, ?, 'user', ?, 'pending', ?)
                """,
                (str(uuid4()), conversation_id, turn_id, question, now),
            )
            self._connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )

    def complete_turn(self, conversation_id: str, turn_id: str, answer: str) -> None:
        now = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE messages SET status = 'completed', error = NULL WHERE turn_id = ? AND role = 'user'",
                (turn_id,),
            )
            self._connection.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, turn_id, role, content, status, created_at)
                VALUES (?, ?, ?, 'assistant', ?, 'completed', ?)
                ON CONFLICT(turn_id, role) DO UPDATE SET
                    content = excluded.content, status = 'completed', error = NULL
                """,
                (str(uuid4()), conversation_id, turn_id, answer, now),
            )
            self._connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )

    def fail_turn(self, turn_id: str, error: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE messages SET status = 'failed', error = ? WHERE turn_id = ? AND role = 'user'",
                (error[:1000], turn_id),
            )

    def completed_answer(self, turn_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT content FROM messages WHERE turn_id = ? AND role = 'assistant' AND status = 'completed'",
            (turn_id,),
        ).fetchone()
        return str(row["content"]) if row else None

    def recent_messages(self, conversation_id: str, limit: int) -> list[dict[str, str]]:
        rows = self._connection.execute(
            """
            SELECT role, content, turn_id FROM messages
            WHERE conversation_id = ? AND status = 'completed'
            ORDER BY created_at DESC LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def list_conversations(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT c.*, COUNT(m.id) AS message_count
            FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id ORDER BY c.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str, include_messages: bool = True) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not row:
            raise NotFoundError("Conversation not found")
        result = dict(row)
        if include_messages:
            messages = self._connection.execute(
                "SELECT id, turn_id, role, content, status, error, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()
            result["messages"] = [dict(item) for item in messages]
        return result

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            if cursor.rowcount == 0:
                raise NotFoundError("Conversation not found")

    def healthy(self) -> bool:
        try:
            self._connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

