# VideoMind AI

VideoMind AI 是一个 AI 视频知识管理平台，目标是把“收藏但没时间看的视频”自动转化为可搜索、可回顾、可对话的个人知识资产。

项目核心流程：

```text
视频 URL（本地上传待实现）
-> 下载并获取字幕；无字幕时按 ASR 配置转写（当前默认关闭）
-> 使用 LLM 理解视频内容
-> 生成结构化 Markdown 笔记
-> 存入个人视频知识库
-> 基于 RAG 实现 Chat With My Videos
```

> 项目资料建议先读：[文档入口](docs/PROJECT_MATERIALS.md) · [当前状态](PROJECT_CONTEXT.md) · [项目交接](PROJECT_HANDOFF.md) · [阶段路线图](docs/roadmap.md)。以下 README 中早期阶段描述以这些当前核对文档为准。

## 当前阶段

当前完成：

- **Phase 1：项目初始化**
- **Phase 2：Backend 基础 API**
- **Phase 3：视频处理 Pipeline 基础实现**
- **Phase 4：AI 视频分析 Agent 基础实现**
- **Phase 5：RAG 问答基础实现**
- **Phase 6：前端 UI 基础实现**
- **Phase 7：本地生产化基础已实现，真实视频闭环待验收**
- **Sprint 02：Supabase 用户系统接入中，代码尚未提交及运行验收**

已完成内容：

- 使用 monorepo 组织前端、后端、文档和本地存储目录。
- 前端使用 Next.js 16.3.3、React 19、TypeScript 和 Tailwind CSS。
- 后端规划为 Python FastAPI、SQLAlchemy、PostgreSQL。
- 使用 Docker Compose 管理 PostgreSQL、Adminer 和应用服务；本地 Chroma 默认嵌入后端，独立服务按需启用。
- 实现 URL 视频下载、字幕优先解析和音频提取；ASR 默认为关闭，暂无可用的本地转写 fallback。
- 实现 DeepSeek 视频分析 Agent、Markdown 笔记生成、ChromaDB 写入和 Chat With My Videos API。
- 实现中文优先的 Next.js 前端：工作台、知识库、视频详情、视频问答和快速添加入口。
- 提供 `.env.example` 作为环境变量模板。
- 提供后端和前端 Dockerfile。
- 提供架构文档和 API 规划文档。
- 预留视频、音频、转写文本、笔记和临时文件目录。

视频详情可一键处理字幕、生成 AI 笔记并写入知识库，也可分别执行各阶段；失败后的一键重试复用已完成阶段。此流程目前由本地 BackgroundTasks 执行，真实视频与服务商调用尚未验收。

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

## 当前技术栈

### Frontend

- Next.js 16.3.3
- React 19
- TypeScript
- Tailwind CSS 与项目内 UI 组件

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

### 用户认证模式

本地默认使用演示用户，不需要注册即可开发：

```env
AUTH_MODE=demo
```

接入 Supabase 后，在 `.env` 填写以下配置并重启前后端：

```env
AUTH_MODE=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-public-anon-key
```

后端使用 `SUPABASE_URL` 和 `SUPABASE_ANON_KEY` 向 Supabase Auth 验证用户令牌；前端使用 `NEXT_PUBLIC_` 变量。两侧必须指向同一个项目。登录和注册页面位于 `http://localhost:3000/auth`。

## Docker 命令说明

启动 Phase 1 的基础设施：

```bash
docker compose up -d postgres adminer
```

这条命令的意思是：

- `docker compose`：读取当前目录下的 `docker-compose.yml`。
- `up`：创建并启动服务。
- `-d`：后台运行，也叫 detached mode，所以终端不会一直打印日志。
- `postgres adminer`：启动数据库和管理界面；本地向量库默认嵌入后端并持久化到 `storage/chroma/`，无需单独启动 Chroma 容器。

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

## 初始开发路线图

下列内容是早期规划；当前验收状态请以 [阶段路线图](docs/roadmap.md) 为准。

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
- [分阶段任务路线图](docs/roadmap.md)
- [部署审计报告](docs/deployment-audit.md)

## 数据库迁移

新环境使用 Alembic 创建和升级数据库结构：

```bash
cd backend
alembic upgrade head
```

本地开发默认保留 `AUTO_CREATE_DATABASE_TABLES=true`，方便首次启动。生产环境必须设置为 `false`，并在应用启动前执行 `alembic upgrade head`。

如果本地数据库已经由旧版本自动建表且结构与当前模型一致，可以先备份数据，再执行：

```bash
cd backend
alembic stamp head
```

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

当前默认使用 demo user；Supabase 认证代码正在接入，真实配置和多用户隔离尚待验收。

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

本地仓库已实现前后端基础功能和 Phase 7 生产化基础，真实视频端到端流程与 Supabase 用户系统尚待验收。最新 Git 和运行状态见 [项目上下文](PROJECT_CONTEXT.md)。

## 用户语言与自带模型密钥（2026-10-08）

网站右上角可切换中文和英文；`/settings` 为产品设置页。截图中的英文 Preferences 属于 Next.js 开发工具，已通过 `devIndicators: false` 从本地预览隐藏。

登录用户可以在 `/settings` 选择 DeepSeek 或 OpenAI、自填 Chat Completions 模型名和 API Key，并可另填 OpenAI 音频转写 Key。后端把密钥用 `USER_API_KEY_ENCRYPTION_KEY` 加密后存入 PostgreSQL；读取接口只返回是否已设置，密钥不会回传浏览器。分析、视频问答和缺字幕时的转写按当前用户的配置调用服务商，费用由用户在各自的服务商账户承担。已认证用户没有密钥时会得到设置提示，不会使用项目所有者的 `.env` Key。服务商地址由后端固定，用户不能填写任意 URL。

生成一次 Fernet Key 并保存在未提交的 `.env` 中；之后不要轮换或丢失，否则已保存的用户密钥无法解密。生产环境需要先配置 `AUTH_MODE=supabase`、两端 Supabase 环境变量，再执行 Alembic 迁移。当前本地 `demo` 模式所有访问者共用同一演示账户，设置页只供预览，API 拒绝保存个人密钥；不要作为开放注册服务使用。真实 Supabase 双用户登录、服务商真实计费与视频全链路仍待验收。

## 本地向量库（2026-10-08）

默认 `CHROMA_MODE=embedded`，后端使用 Chroma PersistentClient，数据保存在已挂载的 `storage/chroma/`，不用拉取单独的 Chroma 镜像。`/api/v1/health/ready` 同时检查 PostgreSQL 和向量库。需要独立服务时，在 `.env` 设置 `CHROMA_MODE=http` 并运行 `docker compose --profile remote-chroma up -d chroma`；生产环境应使用服务端向量库和持久卷。嵌入式模式只面向本地单实例开发。
