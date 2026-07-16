from __future__ import annotations

import os
import html
from typing import Any
from uuid import uuid4

import httpx
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx


if __name__ == "__main__" and get_script_run_ctx(suppress_warning=True) is None:
    from app.launcher import launch

    raise SystemExit(launch())

from app.ui.api_client import APIError, AgentAPIClient
from app.ui.styles import APP_CSS


st.set_page_config(
    page_title="Project Mind",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "api_url": os.getenv("AGENT_API_URL", "http://127.0.0.1:8000"),
        "conversation_id": None,
        "memory_search_results": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_data(ttl=4, show_spinner=False)
def cached_health(base_url: str) -> dict[str, Any]:
    return AgentAPIClient(base_url).health()


def page_heading(title: str, description: str) -> None:
    st.markdown(
        f'<div class="page-heading"><h1>{title}</h1><p>{description}</p></div>',
        unsafe_allow_html=True,
    )


def empty_state(title: str, description: str) -> None:
    st.markdown(
        f'<div class="empty-state"><strong>{title}</strong>{description}</div>',
        unsafe_allow_html=True,
    )


def display_sources(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    seen: set[str] = set()
    labels: list[str] = []
    for item in items:
        if item.get("type") == "knowledge":
            label = item.get("filename") or "知识库片段"
        else:
            created = str(item.get("created_at") or "")[:10]
            label = f"长期记忆 · {created}" if created else "长期记忆"
        if label not in seen:
            seen.add(label)
            labels.append(label)
    st.markdown(
        "".join(f'<span class="source-chip">{html.escape(label)}</span>' for label in labels),
        unsafe_allow_html=True,
    )
    with st.expander("查看检索片段"):
        for index, item in enumerate(items, start=1):
            title = item.get("filename") or item.get("created_at") or f"片段 {index}"
            st.markdown(f"**{title}**")
            st.caption(str(item.get("content") or "")[:1200])


def render_sidebar(client: AgentAPIClient) -> tuple[str, dict[str, Any] | None]:
    with st.sidebar:
        st.markdown(
            """
            <div class="app-brand">
              <div class="app-mark">PM</div>
              <div><strong>Project Mind</strong><span>项目知识与记忆助手</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        try:
            health = cached_health(st.session_state.api_url)
            if health.get("model_configured"):
                status_class, status_text = "", "服务与模型已连接"
            else:
                status_class, status_text = "warning", "服务在线，等待模型配置"
        except (APIError, OSError, ValueError):
            health = None
            status_class, status_text = "offline", "后端服务未连接"
        st.markdown(
            f'<div class="status-line"><span class="status-dot {status_class}"></span>{status_text}</div>',
            unsafe_allow_html=True,
        )
        if health:
            st.markdown(
                "<div class='metric-strip'>"
                f"<span><strong>{health.get('document_sources', 0)}</strong> 份资料</span>"
                f"<span><strong>{health.get('long_term_memories', 0)}</strong> 条记忆</span>"
                "</div>",
                unsafe_allow_html=True,
            )

        page = st.radio(
            "导航",
            ["对话", "知识库", "会话", "记忆"],
            key="navigation",
            label_visibility="collapsed",
        )
        st.divider()
        with st.expander("连接设置"):
            api_url = st.text_input("FastAPI 地址", value=st.session_state.api_url)
            if api_url.rstrip("/") != st.session_state.api_url.rstrip("/"):
                st.session_state.api_url = api_url.rstrip("/")
                cached_health.clear()
                st.rerun()
            st.caption("API Key 只保存在后端 `.env`，不会进入浏览器或 Streamlit 状态。")
        if health is None:
            st.info("先运行 `uvicorn app.main:app --port 8000`，再刷新页面。")
        elif not health.get("model_configured"):
            st.warning("请在项目 `.env` 中填写百炼 API Key 与 Base URL。")
    return page, health


def chat_page(client: AgentAPIClient, health: dict[str, Any] | None) -> None:
    page_heading("与项目对话", "Agent 会按需检索项目资料与跨会话记忆，并实时展示回答。")

    try:
        conversations = client.list_conversations().get("items", [])
    except APIError:
        conversations = []

    controls = st.columns([4, 1])
    with controls[0]:
        options = {item["id"]: item.get("title") or "未命名会话" for item in conversations}
        option_ids = [None, *options.keys()]
        current = st.session_state.conversation_id
        selected_index = option_ids.index(current) if current in option_ids else 0
        selected = st.selectbox(
            "当前会话",
            option_ids,
            index=selected_index,
            format_func=lambda value: "新会话" if value is None else options.get(value, "历史会话"),
        )
        if selected != current:
            st.session_state.conversation_id = selected
            st.rerun()
    with controls[1]:
        st.write("")
        if st.button("新建会话", use_container_width=True):
            st.session_state.conversation_id = None
            st.rerun()

    messages: list[dict[str, Any]] = []
    if st.session_state.conversation_id:
        try:
            messages = client.get_conversation(st.session_state.conversation_id).get("messages", [])
        except APIError as exc:
            st.error(f"无法读取会话：{exc}")

    if not messages:
        empty_state("从一个具体问题开始", "例如：项目的核心规则是什么？或者：还记得我们上次确定的方案吗？")
    else:
        for message in messages:
            if message.get("status") != "completed":
                continue
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    disabled = not health or not health.get("model_configured")
    prompt = st.chat_input("询问项目资料或继续之前的话题…", disabled=disabled)
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        status_slot = st.empty()
        answer_slot = st.empty()
        answer = ""
        sources: list[dict[str, Any]] = []
        try:
            for event in client.stream_chat(
                prompt,
                st.session_state.conversation_id,
                request_id=str(uuid4()),
            ):
                event_name, data = event["event"], event["data"]
                if event_name == "meta":
                    st.session_state.conversation_id = data.get("conversation_id")
                elif event_name == "status":
                    status_slot.caption(data.get("message", "正在处理…"))
                elif event_name == "sources":
                    sources.extend(data.get("items", []))
                elif event_name == "token":
                    answer += data.get("text", "")
                    answer_slot.markdown(answer + " ▌")
                elif event_name == "error":
                    raise APIError(data.get("message", "Agent 请求失败"))
            status_slot.empty()
            answer_slot.markdown(answer)
            display_sources(sources)
            cached_health.clear()
        except (APIError, httpx.HTTPError) as exc:  # type: ignore[name-defined]
            status_slot.empty()
            st.error(f"回答失败：{exc}")


def knowledge_page(client: AgentAPIClient, health: dict[str, Any] | None) -> None:
    page_heading("知识库", "上传 Markdown 或 TXT 项目资料。内容会分块向量化，并与长期记忆严格隔离。")
    uploaded = st.file_uploader(
        "上传资料",
        type=["md", "markdown", "txt"],
        accept_multiple_files=True,
        help="仅支持 UTF-8 文本，单文件最大 10 MB。",
    )
    if st.button(
        "导入知识库",
        type="primary",
        disabled=not uploaded or not health or not health.get("model_configured"),
    ):
        files = [(item.name, item.getvalue(), item.type or "text/plain") for item in uploaded]
        try:
            with st.status("正在分块并生成向量…", expanded=True) as status:
                result = client.upload_documents(files)
                for item in result.get("results", []):
                    st.write(f"{item.get('filename')} · {item.get('status')}")
                status.update(label="导入完成", state="complete", expanded=False)
            cached_health.clear()
            st.rerun()
        except APIError as exc:
            st.error(f"导入失败：{exc}")

    st.subheader("已导入资料")
    try:
        documents = client.list_documents().get("items", [])
    except APIError as exc:
        st.error(f"无法读取知识库：{exc}")
        return
    if not documents:
        empty_state("知识库还是空的", "上传项目说明、业务规则或技术文档后，Agent 才能引用项目事实。")
        return
    for item in documents:
        with st.container(border=True):
            info, action = st.columns([8, 1])
            with info:
                st.markdown(f"**{item.get('filename', '未命名文档')}**")
                st.caption(f"{item.get('chunks', 0)} 个片段 · {str(item.get('imported_at', ''))[:19]}")
            with action:
                if st.button("删除", key=f"doc-{item['source_id']}"):
                    try:
                        client.delete_document(item["source_id"])
                        cached_health.clear()
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))


def conversations_page(client: AgentAPIClient) -> None:
    page_heading("会话记录", "查看完整聊天历史，继续某次讨论，或删除会话及其关联长期记忆。")
    try:
        conversations = client.list_conversations().get("items", [])
    except APIError as exc:
        st.error(f"无法读取会话：{exc}")
        return
    if not conversations:
        empty_state("还没有会话", "完成第一轮对话后，聊天记录会永久保存在 SQLite。")
        return

    def open_conversation(conversation_id: str) -> None:
        st.session_state.conversation_id = conversation_id
        st.session_state.navigation = "对话"

    for item in conversations:
        with st.container(border=True):
            info, open_col, delete_col = st.columns([7, 1.2, 1.2])
            with info:
                st.markdown(f"**{item.get('title') or '未命名会话'}**")
                updated = str(item.get("updated_at") or "")[:19].replace("T", " ")
                st.caption(f"{item.get('message_count', 0)} 条消息 · 更新于 {updated}")
            with open_col:
                st.button(
                    "打开",
                    key=f"open-{item['id']}",
                    use_container_width=True,
                    on_click=open_conversation,
                    args=(item["id"],),
                )
            with delete_col:
                if st.button("删除", key=f"conv-{item['id']}", use_container_width=True):
                    try:
                        client.delete_conversation(item["id"])
                        if st.session_state.conversation_id == item["id"]:
                            st.session_state.conversation_id = None
                        cached_health.clear()
                        st.rerun()
                    except APIError as exc:
                        st.error(str(exc))


def memories_page(client: AgentAPIClient, health: dict[str, Any] | None) -> None:
    page_heading("永久记忆", "每轮成功对话都会脱敏后写入独立 Chroma collection，可跨会话语义召回。")
    search_col, button_col = st.columns([5, 1])
    with search_col:
        query = st.text_input("语义搜索", placeholder="搜索过去讨论过的方案、偏好或决定")
    with button_col:
        st.write("")
        search_clicked = st.button(
            "搜索",
            type="primary",
            use_container_width=True,
            disabled=not query or not health or not health.get("model_configured"),
        )
    if search_clicked:
        try:
            st.session_state.memory_search_results = client.search_memories(query, 10)
        except APIError as exc:
            st.error(f"搜索失败：{exc}")

    try:
        payload = st.session_state.memory_search_results or client.list_memories(limit=100)
        memories = payload.get("items", [])
    except APIError as exc:
        st.error(f"无法读取记忆：{exc}")
        return

    label = "搜索结果" if st.session_state.memory_search_results else "全部记忆"
    st.subheader(f"{label} · {len(memories)}")
    if not memories:
        empty_state("没有可显示的记忆", "完成一次对话后，问题和回答会作为一条长期语义记忆保存。")
    for item in memories:
        memory_id = item.get("memory_id") or item.get("id")
        created = str(item.get("created_at") or "")[:19].replace("T", " ")
        with st.expander(created or "长期记忆"):
            st.markdown(str(item.get("content") or ""))
            if st.button("删除这条记忆", key=f"memory-{memory_id}"):
                try:
                    client.delete_memory(memory_id)
                    st.session_state.memory_search_results = None
                    cached_health.clear()
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))

    st.divider()
    with st.expander("清空全部长期记忆"):
        st.warning("此操作不可撤销，但不会删除 SQLite 中的完整会话记录。")
        confirm = st.checkbox("我确认清空全部长期记忆")
        if st.button("永久清空", disabled=not confirm):
            try:
                deleted = client.clear_memories()
                st.session_state.memory_search_results = None
                cached_health.clear()
                st.success(f"已删除 {deleted} 条记忆")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))


def main() -> None:
    init_state()
    client = AgentAPIClient(st.session_state.api_url)
    page, health = render_sidebar(client)
    if page == "对话":
        chat_page(client, health)
    elif page == "知识库":
        knowledge_page(client, health)
    elif page == "会话":
        conversations_page(client)
    else:
        memories_page(client, health)


if __name__ == "__main__":
    main()
