from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from app.config import AppSettings
from app.errors import ModelNotConfiguredError
from app.services.documents import DocumentService
from app.services.memory import MemoryService


SYSTEM_PROMPT = """你是项目内的 AI 助手。你有两个只读检索工具：
1. search_knowledge_base：查询项目资料。
2. search_long_term_memory：查询过去会话形成的长期记忆。

规则：
- 涉及项目事实、规则或历史上下文时，先调用对应工具，不要编造工具结果。
- 引用项目知识库时，用 [来源: 文件名] 标注。
- 长期记忆只作为历史对话线索；如果与用户当前消息冲突，以当前消息为准。
- 检索信息不足时可以使用通用知识，但必须明确写“以下为通用知识补充”。
- 不要声称检索到未出现在工具结果中的内容，也不要输出密钥或认证信息。
- 回答使用与用户相同的语言，清晰、直接。
"""


def _text_from_chunk(chunk: Any) -> str:
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _answer_from_output(output: Any) -> str:
    if isinstance(output, dict) and isinstance(output.get("messages"), list):
        for message in reversed(output["messages"]):
            if getattr(message, "type", None) == "ai":
                return _text_from_chunk(message)
    return ""


class AgentService:
    def __init__(
        self,
        settings: AppSettings,
        documents: DocumentService,
        memories: MemoryService,
    ):
        self.settings = settings
        self.documents = documents
        self.memories = memories

    def _model(self) -> ChatOpenAI:
        if not self.settings.model_configured:
            raise ModelNotConfiguredError("Qwen model credentials are not configured")
        return ChatOpenAI(
            model=self.settings.llm.model,
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
            temperature=self.settings.llm.temperature,
            timeout=self.settings.llm.timeout_seconds,
            max_retries=self.settings.llm.max_retries,
            streaming=True,
        )

    async def stream(
        self,
        question: str,
        history: list[dict[str, str]],
        recent_turn_ids: set[str],
    ) -> AsyncIterator[dict[str, Any]]:
        captured_sources: list[dict[str, Any]] = []

        @tool("search_knowledge_base")
        def search_knowledge_base(query: str) -> str:
            """检索项目文档、业务规则和项目知识；项目相关问题应优先使用。"""
            results = self.documents.search(query)
            captured_sources.extend(results)
            return json.dumps({"results": results}, ensure_ascii=False)

        @tool("search_long_term_memory")
        def search_long_term_memory(query: str) -> str:
            """检索过去会话内容，用于回忆用户以前说过或讨论过的事项。"""
            results = self.memories.search(query, excluded_turn_ids=recent_turn_ids)
            captured_sources.extend(results)
            return json.dumps({"results": results}, ensure_ascii=False)

        agent = create_agent(
            model=self._model(),
            tools=[search_knowledge_base, search_long_term_memory],
            system_prompt=SYSTEM_PROMPT,
            name="project_rag_agent",
        )
        messages = [{"role": item["role"], "content": item["content"]} for item in history]
        messages.append({"role": "user", "content": question})

        emitted_sources = 0
        streamed_answer: list[str] = []
        final_candidate = ""
        async for event in agent.astream_events({"messages": messages}, version="v2"):
            event_name = event.get("event")
            if event_name == "on_tool_start":
                yield {
                    "event": "status",
                    "data": {"stage": "tool", "tool": event.get("name"), "message": "正在检索…"},
                }
            elif event_name == "on_tool_end" and len(captured_sources) > emitted_sources:
                fresh = captured_sources[emitted_sources:]
                emitted_sources = len(captured_sources)
                yield {"event": "sources", "data": {"items": fresh}}
            elif event_name == "on_chat_model_stream":
                token = _text_from_chunk((event.get("data") or {}).get("chunk"))
                if token:
                    streamed_answer.append(token)
                    yield {"event": "token", "data": {"text": token}}
            elif event_name == "on_chain_end":
                candidate = _answer_from_output((event.get("data") or {}).get("output"))
                if candidate:
                    final_candidate = candidate

        answer = "".join(streamed_answer).strip() or final_candidate.strip()
        if not answer:
            raise RuntimeError("The model returned an empty answer")
        yield {
            "event": "complete",
            "data": {
                "answer": answer,
                "used_knowledge_base": any(item.get("type") == "knowledge" for item in captured_sources),
                "used_long_term_memory": any(item.get("type") == "memory" for item in captured_sources),
            },
        }

