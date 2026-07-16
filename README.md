# Custom Agent（Project Mind）

一个面向项目知识管理的本地 AI Agent。项目使用 FastAPI 提供后端 API，Streamlit 提供网页界面，并通过 Qwen、LangChain、Chroma 和 SQLite 实现知识库检索、流式对话、会话历史与长期记忆。

## 功能特性

- **流式 AI 对话**：通过 SSE 实时输出模型回答。
- **项目知识库**：上传或批量导入 Markdown、TXT 文档，自动分块并向量化。
- **长期记忆**：每轮成功对话都会保存为独立的语义记忆，可在后续对话中检索。
- **会话管理**：使用 SQLite 持久化会话及消息，支持查看、继续和删除历史会话。
- **来源展示**：回答使用知识库或长期记忆时，网页会展示相关检索片段。
- **幂等请求**：重复使用同一个 `request_id` 时，不会重复保存同一轮对话。
- **敏感信息保护**：长期记忆写入前会过滤常见 API Key、Bearer Token 和密码格式。
- **数据隔离**：项目知识与长期记忆分别存放在独立的 Chroma Collection 中。

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- Streamlit
- LangChain
- Qwen（OpenAI 兼容接口）
- `text-embedding-v4`
- ChromaDB
- SQLite

## 项目结构

```text
Custom-agent/
├─ app/
│  ├─ main.py                 # FastAPI 应用与 API 路由
│  ├─ config.py               # 配置加载与校验
│  ├─ database.py             # SQLite 会话存储
│  ├─ launcher.py             # 前后端一键启动器
│  ├─ vectorstores.py         # Chroma 与 Embeddings 配置
│  ├─ services/
│  │  ├─ agent.py             # LangChain Agent 与流式事件
│  │  ├─ documents.py         # 文档导入、分块与检索
│  │  └─ memory.py            # 长期记忆管理与脱敏
│  └─ ui/
│     ├─ api_client.py        # Streamlit API 客户端
│     └─ styles.py            # 页面样式
├─ tests/                     # 自动化测试
├─ config.yaml                # 模型、检索、文档和存储参数
├─ streamlit_app.py           # 网页入口
├─ run.ps1                    # Windows 一键启动脚本
├─ pyproject.toml             # 依赖与项目元数据
└─ .env.example               # 环境变量模板
```

## 快速开始

### 1. 创建虚拟环境

在项目根目录执行：

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
```

### 2. 配置模型

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
DASHSCOPE_API_KEY=你的阿里云百炼_API_Key
DASHSCOPE_BASE_URL=你的工作空间_OpenAI_兼容接口地址
```

API Key 与 Base URL 必须属于同一个地域和工作空间。请以阿里云百炼控制台显示的 OpenAI 兼容接口地址为准。

> `.env` 已加入 `.gitignore`，不要将真实密钥提交到 Git 仓库或发送给他人。

### 3. 启动项目

Windows 推荐使用一键启动脚本：

```powershell
.\run.ps1
```

也可以通过 Python 启动器运行：

```powershell
& ".\.venv\Scripts\python.exe" streamlit_app.py
```

启动后打开：

- 网页界面：<http://127.0.0.1:8501>
- Swagger API 文档：<http://127.0.0.1:8000/docs>
- 后端健康检查：<http://127.0.0.1:8000/health>

### 分别启动前后端

终端一：

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二：

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.port 8501
```

## PyCharm 启动配置

项目包含共享运行配置 **FastAPI (Uvicorn)**。在 PyCharm 顶部的运行配置下拉框中选择它，然后点击运行按钮即可启动后端。

如需手动创建配置，请使用以下参数：

- 配置类型：Python
- Module name：`uvicorn`
- Parameters：`app.main:app --reload`
- Working directory：项目根目录
- Python interpreter：项目的 `.venv`

Streamlit 前端可使用下面的命令创建另一个 Python Module 配置：

```text
streamlit run streamlit_app.py --server.port 8501
```

## 使用方法

### 对话

打开网页后进入“对话”页面，在底部输入问题。Agent 会根据问题决定是否检索项目知识库或长期记忆，并实时展示回答。

### 导入知识库

可以在网页的“知识库”页面上传 `.md`、`.markdown` 或 `.txt` 文件，也可以调用目录导入接口：

```powershell
$body = @{ path = "data/documents"; recursive = $true } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/documents/ingest-directory" `
  -ContentType "application/json" `
  -Body $body
```

默认单文件最大 10 MB，文档分块大小和重叠长度可在 `config.yaml` 中修改。

### 流式对话 API

```powershell
$body = @{
  question   = "这个项目的主要功能是什么？"
  request_id = [guid]::NewGuid().ToString()
} | ConvertTo-Json

Invoke-WebRequest `
  -UseBasicParsing `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/chat/stream" `
  -ContentType "application/json; charset=utf-8" `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

服务端会依次返回以下 SSE 事件：

- `meta`：会话 ID 和本轮 ID。
- `status`：Agent 当前处理阶段。
- `sources`：本轮检索到的知识或记忆来源。
- `token`：模型生成的文本片段。
- `done`：回答完成及记忆保存结果。
- `error`：请求失败信息。

## 主要 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 查看后端、模型和存储状态 |
| `POST` | `/api/v1/chat/stream` | 发起 SSE 流式对话 |
| `POST` | `/api/v1/documents/upload` | 上传知识库文件 |
| `POST` | `/api/v1/documents/ingest-directory` | 导入指定目录 |
| `GET` | `/api/v1/documents` | 查看知识来源 |
| `DELETE` | `/api/v1/documents/{source_id}` | 删除知识来源 |
| `GET` | `/api/v1/conversations` | 查看会话列表 |
| `GET` | `/api/v1/conversations/{conversation_id}` | 查看完整会话 |
| `DELETE` | `/api/v1/conversations/{conversation_id}` | 删除会话及相关记忆 |
| `GET` | `/api/v1/memories` | 查看长期记忆 |
| `POST` | `/api/v1/memories/search` | 语义搜索长期记忆 |
| `DELETE` | `/api/v1/memories/{memory_id}` | 删除单条记忆 |
| `DELETE` | `/api/v1/memories` | 确认后清空长期记忆 |

完整请求与响应结构请查看 Swagger：<http://127.0.0.1:8000/docs>。

## 配置说明

主要运行参数位于 `config.yaml`：

```yaml
llm:
  model: qwen3.7-plus
  temperature: 0.2
  timeout_seconds: 60
  max_retries: 2

embedding:
  model: text-embedding-v4
  dimensions: 1024
  batch_size: 10

retrieval:
  knowledge_top_k: 5
  memory_top_k: 4
```

修改模型、向量维度或存储配置后，需要重启 FastAPI 后端。

## 本地数据

运行数据默认存储在以下目录：

| 数据 | 路径 |
| --- | --- |
| Chroma 向量库 | `data/chroma/` |
| SQLite 会话数据库 | `data/chat_history.db` |
| 待导入文档 | `data/documents/` |

这些运行数据均已加入 `.gitignore`，不会随源码提交。

## 测试

安装开发依赖后运行：

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
```

测试默认使用临时数据库和模拟模型请求，不会调用真实的百炼 API。

## 常见问题

### 网页输入框无法输入

前端会在后端离线或 `model_configured=false` 时禁用聊天输入框。请检查：

1. FastAPI 是否正在监听 `127.0.0.1:8000`。
2. `.env` 中是否同时设置了 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`。
3. 修改 `.env` 后是否重启了 FastAPI。
4. `/health` 是否返回 `"model_configured": true`。

### 页面提示 `Agent request failed`

先查看 FastAPI 终端中的真实异常。常见原因包括 API Key 或 Base URL 不匹配、模型无权限、网络请求失败，以及 Embeddings 参数与接口不兼容。

本项目已针对百炼工作空间的 OpenAI 兼容 Embeddings 接口关闭 LangChain 的 token ID 预转换，确保 `text-embedding-v4` 接收文本输入。

### 直接运行 `app/main.py` 后立即退出

`app/main.py` 只负责创建 FastAPI 应用对象，不会自行启动 Web 服务器。请使用：

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

## 安全建议

- 不要提交 `.env`、真实 API Key、本地数据库或向量库。
- 部署到公网前应增加身份认证、访问控制、HTTPS、请求限流和文件内容检查。
- 上传目录接口仅应在可信环境中开放。
- 定期检查长期记忆，删除不再需要或不应持久化的内容。

## License

当前仓库尚未声明开源许可证。在添加许可证前，默认保留所有权利。
