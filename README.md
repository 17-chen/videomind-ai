# VideoMind AI

VideoMind AI 是一个 AI 视频知识管理平台，目标是把“收藏但没时间看的视频”自动转化为可搜索、可回顾、可对话的个人知识资产。

项目核心流程：

```text
视频链接或本地上传
-> 获取视频信息、下载视频或提取音频、获取字幕或 Whisper 转写
-> 使用 LLM 理解视频内容
-> 生成结构化 Markdown 笔记
-> 存入个人视频知识库
-> 基于 RAG 实现 Chat With My Videos
```

## 当前阶段

当前完成：

- **Phase 1：项目初始化**
- **Phase 2：Backend 基础 API**
- **Phase 3：视频处理 Pipeline 基础实现**
- **Phase 4：AI 视频分析 Agent 基础实现**
- **Phase 5：RAG 问答基础实现**
- **Phase 6：前端 UI 基础实现**

已完成内容：

- 使用 monorepo 组织前端、后端、文档和本地存储目录。
- 前端规划为 Next.js 15、React、TypeScript、Tailwind CSS、shadcn/ui。
- 后端规划为 Python FastAPI、SQLAlchemy、PostgreSQL。
- 使用 Docker Compose 管理 PostgreSQL、ChromaDB、Adminer。
- 实现 URL 视频下载、字幕优先解析、音频提取、Whisper fallback 的后端 Pipeline。
- 实现 DeepSeek 视频分析 Agent、Markdown 笔记生成、ChromaDB 写入和 Chat With My Videos API。
- 实现中文优先的 Next.js 前端：工作台、知识库、视频详情、视频问答和快速添加入口。
- 提供 `.env.example` 作为环境变量模板。
- 提供后端和前端 Dockerfile。
- 提供架构文档和 API 规划文档。
- 预留视频、音频、转写文本、笔记和临时文件目录。

后续阶段会继续做 UI 视觉精修、文件上传、本地 ASR 和更强的中文向量模型。

## 项目结构

```text
videomind-ai/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── agents/
│   │   ├── core/
│   │   ├── database/
│   │   ├── models/
│   │   ├── prompts/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── utils/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── styles/
│   ├── Dockerfile
│   └── package.json
├── docs/
│   ├── api.md
│   └── architecture.md
├── scripts/
├── storage/
│   ├── audio/
│   ├── notes/
│   ├── tmp/
│   ├── transcripts/
│   └── videos/
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## 技术栈规划

### Frontend

- Next.js 15
- React
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend

- Python 3.12+
- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- LangGraph

### AI / Data

- DeepSeek API
- 可插拔 ASR，当前默认关闭；后续推荐接本地 faster-whisper
- 本地 hash embedding，后续可替换为 bge-m3 / sentence-transformers
- ChromaDB
- 后续可扩展 Gemini、Claude、Pinecone

## 本地运行准备

请先安装：

- Docker Desktop
- Docker Compose v2
- Node.js 20+，用于后续前端本地开发
- Python 3.12+，用于后续后端本地开发

复制环境变量文件：

```bash
cp .env.example .env
```

## Docker 命令说明

启动 Phase 1 的基础设施：

```bash
docker compose up -d postgres chroma adminer
```

这条命令的意思是：

- `docker compose`：读取当前目录下的 `docker-compose.yml`。
- `up`：创建并启动服务。
- `-d`：后台运行，也叫 detached mode，所以终端不会一直打印日志。
- `postgres chroma adminer`：只启动这三个基础设施服务，不启动还没正式实现的 frontend/backend 应用服务。

如果你运行后“没有反应”，通常有几种情况：

1. **正常情况：服务已经在后台启动**

   因为用了 `-d`，Docker 会在后台运行容器。可以用下面命令查看：

   ```bash
   docker compose ps
   ```

2. **Docker Desktop 没有启动**

   请先打开 Docker Desktop，等它显示 Docker Engine 已运行，再重新执行命令。

3. **当前目录不对**

   需要先进入项目根目录：

   ```bash
   cd "/Users/chenxin/Documents/Codex 2/videomind-ai"
   ```

4. **想看实时日志**

   不加 `-d` 就会在终端显示启动日志：

   ```bash
   docker compose up postgres chroma adminer
   ```

5. **想查看后台日志**

   ```bash
   docker compose logs -f
   ```

服务启动后可以访问：

- PostgreSQL: `localhost:5432`
- ChromaDB: `http://localhost:8001`
- Adminer: `http://localhost:8080`

停止服务：

```bash
docker compose down
```

停止服务并删除本地数据库 / 向量库数据卷：

```bash
docker compose down -v
```

## 开发路线图

1. **Phase 1：项目初始化**
   - 项目目录设计
   - Docker 配置
   - 环境变量模板
   - README 和架构文档

2. **Phase 2：Backend 开发**
   - FastAPI 应用入口
   - PostgreSQL 连接
   - SQLAlchemy 模型
   - `/videos` API

3. **Phase 3：视频处理 Pipeline**
   - 视频链接解析
   - 视频下载
   - 音频提取
   - 字幕获取
   - Whisper ASR

4. **Phase 4：AI Agent**
   - Video Analysis Agent
   - Prompt 工程
   - JSON 结构化分析输出
   - Markdown 笔记生成

5. **Phase 5：RAG 系统**
   - Embedding 生成
   - ChromaDB 向量存储
   - 语义检索
   - Chat With My Videos

6. **Phase 6：Frontend**
   - Landing Page
   - Dashboard
   - Library Page
   - Video Detail Page
   - Chat Page
   - 响应式 SaaS UI

## 环境变量说明

项目默认使用 DeepSeek 作为 LLM Provider。`DEEPSEEK_API_KEY` 在 `.env.example` 中故意留空，Phase 4 运行 AI 视频分析前，需要在 `.env` 中填入自己的 DeepSeek API Key。

`DATABASE_URL` 默认使用 Docker Compose 内部服务名 `postgres`。如果你在宿主机直接运行后端，可以改成：

```text
postgresql+psycopg://videomind:videomind_dev_password@localhost:5432/videomind
```

## 文档

- [架构设计](docs/architecture.md)
- [API 规划](docs/api.md)
- [项目书](docs/project-plan.md)
- [当前自查记录](docs/self-review.md)

FastAPI 的 OpenAPI 文档会在 Phase 2 后端启动后开放：

```text
http://localhost:8000/docs
```

## Phase 2 后端接口

Phase 2 已实现：

- `GET /health`
- `GET /api/v1/health`
- `POST /api/v1/videos`
- `GET /api/v1/videos`
- `GET /api/v1/videos/{id}`
- `POST /api/v1/videos/{id}/process`
- `POST /api/v1/videos/{id}/analyze`
- `POST /api/v1/videos/{id}/embed`
- `POST /api/v1/chat`

当前阶段先使用 demo user 自动创建用户记录，正式认证系统会在后续 SaaS 用户体系中接入。

启动完整后端服务：

```bash
docker compose --profile app up -d postgres chroma adminer backend
```

Phase 4 的 AI 分析需要配置：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

默认配置：

```text
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
EMBEDDING_PROVIDER=local_hash
```

说明：DeepSeek 不提供 Whisper 风格的音频转写 API。当前默认 `ASR_PROVIDER=disabled`，系统会优先使用视频字幕；没有字幕的视频暂时不会调用 OpenAI Whisper。

提交并处理一个视频的流程：

```bash
curl -X POST http://localhost:8000/api/v1/videos \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.bilibili.com/video/...","tags":["AI Agent"]}'
```

然后把返回结果里的 `id` 用于触发处理：

```bash
curl -X POST http://localhost:8000/api/v1/videos/{id}/process
```

视频完成转写和分析后，写入向量知识库：

```bash
curl -X POST http://localhost:8000/api/v1/videos/{id}/embed
```

向个人视频知识库提问：

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"我之前收藏过哪些关于 AI Agent 创业的视频？","limit":5}'
```

## Phase 6 前端运行

进入前端目录安装依赖：

```bash
cd frontend
npm install
```

启动本地前端：

```bash
npm run dev
```

访问：

```text
http://localhost:3000
```

已实现页面：

- `/`：首页和快速添加视频
- `/dashboard`：工作台
- `/library`：视频知识库
- `/videos/{id}`：视频详情、处理、分析、写入知识库
- `/chat`：视频知识库问答

质量检查：

```bash
npm run typecheck
npm run build
```

## GitHub 状态

当前项目仍处于早期开发阶段，已完成项目初始化、后端基础 API、视频处理 Pipeline、AI Agent、RAG 基础闭环和前端基础 UI。后续会继续提交视觉精修、文件上传、本地 ASR 和生产级任务队列。
