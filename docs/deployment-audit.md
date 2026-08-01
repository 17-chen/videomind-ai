# VideoMind AI 部署审计报告

> 日期：2026-08-01
> 阶段：Deployment Phase 1 - Audit
> 结论：项目具备作品集展示和本地演示基础，但还没有达到完整生产 SaaS 上线状态。建议先部署前端 Demo 和后端 API Demo，再逐步补数据库迁移、任务队列、认证和生产向量库。

## 1. 项目结构审计

当前结构符合前后端分离：

```text
videomind-ai/
├── frontend/
├── backend/
├── docs/
├── docker-compose.yml
├── README.md
└── .env.example
```

证据：

- 前端入口：`frontend/app/*`
- 后端入口：`backend/app/main.py`
- Docker 编排：`docker-compose.yml`
- 环境变量模板：`.env.example`

风险：

- `storage/` 是本地运行目录，生产应使用对象存储或明确持久化卷。
- 当前没有 CI/CD 配置。
- 当前没有生产专用 Compose 或部署平台配置。

## 2. Frontend 审计

技术栈：

- Next.js 15.5.22
- React 19.2.8
- TypeScript
- Tailwind CSS

已验证：

```bash
cd frontend
npm run typecheck
npm run build
```

结果：

- TypeScript 检查通过。
- Next.js 生产构建通过。
- 本地 `/`、`/dashboard`、`/library`、`/chat` 返回 200。

环境变量：

- 浏览器 API 地址：`NEXT_PUBLIC_API_BASE_URL`
- Next server component 内部 API 地址：`INTERNAL_API_BASE_URL`

主要风险：

- 前端 Dockerfile 当前使用 `npm run dev`，不适合生产。
- Vercel 部署时必须设置 `NEXT_PUBLIC_API_BASE_URL` 为线上后端地址。
- 如果 frontend 和 backend 分开部署，CORS 必须同步更新。

## 3. Backend 审计

技术栈：

- FastAPI
- SQLAlchemy
- PostgreSQL
- Loguru
- LangGraph
- DeepSeek OpenAI-compatible API client
- ChromaDB client

已验证：

```bash
python3 -m compileall backend/app
```

结果：

- 后端 Python 代码可编译。

API 能力：

- `POST /api/v1/videos`
- `GET /api/v1/videos`
- `GET /api/v1/videos/{id}`
- `POST /api/v1/videos/{id}/process`
- `POST /api/v1/videos/{id}/analyze`
- `POST /api/v1/videos/{id}/embed`
- `POST /api/v1/chat`

主要风险：

- Backend Dockerfile 当前使用 `uvicorn ... --reload`，不适合生产。
- 数据库初始化使用 `create_all`，还没有正式 Alembic migration。
- BackgroundTasks 适合 MVP，不适合长视频处理和生产任务重试。
- 当前 demo user 机制不是完整认证系统。
- ASR 默认关闭，无字幕视频无法完整处理，除非接入本地 ASR 或其他转写服务。

## 4. Docker / 本地运行审计

当前 Compose 服务：

- PostgreSQL
- ChromaDB
- Adminer
- Backend
- Frontend

风险：

- `frontend` 和 `backend` 都是开发模式启动。
- ChromaDB 镜像拉取和运行需要网络环境稳定。
- 云平台如果不支持 Docker Compose，则需要拆分服务部署。

建议：

- 本地 Demo：继续使用 Docker Compose。
- 生产 Demo：前端 Vercel，后端 Render/Railway，数据库 Supabase，Chroma 暂用后端服务内可访问的持久化部署或后续替换。
- 如果要最大限度少折腾：单 VPS Docker Compose 一次性部署 frontend/backend/postgres/chroma。

## 5. 数据库生产化审计

当前状态：

- PostgreSQL 数据模型存在。
- SQLAlchemy ORM 已接入。
- Alembic 依赖已安装，但尚未初始化 migrations。

风险：

- `create_all` 无法可靠管理生产 schema 版本。
- `ensure_development_schema` 是 MVP 兼容措施，不应作为长期生产迁移方案。

建议：

1. 初始化 Alembic。
2. 生成首个 migration。
3. 部署时执行 migration。
4. 如果选择 Supabase，确认 `DATABASE_URL` 使用 `postgresql+psycopg://...` 格式。

## 6. AI Pipeline / Debug 审计

当前状态：

- 视频下载：yt-dlp
- 音频提取：ffmpeg
- 字幕解析：已实现
- ASR：可插拔，但默认 disabled
- LLM：DeepSeek
- RAG：ChromaDB + 本地 hash embedding

风险：

- 处理状态只有 `queued / processing / completed / failed`，不够细。
- 用户无法看到 `DOWNLOADING / TRANSCRIBING / ANALYZING / EMBEDDING` 等具体阶段。
- 云环境运行 yt-dlp 可能受到平台限制。
- AI 调用缺 token/latency 记录。

建议：

- 引入更细的视频处理状态。
- 后端增加处理阶段日志字段。
- 记录 AI provider、model、耗时、失败原因。
- 生产环境不要把 prompt 全量写入公开日志。

## 7. 部署路线建议

### 路线 A：作品集最快上线

- Frontend：Vercel
- Backend：Render 或 Railway
- Database：Supabase PostgreSQL
- Vector：暂时保留 ChromaDB 为后端侧服务或后续替换

优点：速度快，GitHub 展示好。

风险：视频处理和 Chroma 持久化需要额外处理。

### 路线 B：完整 Docker 一体化上线

- 单台 VPS
- Docker Compose 启动 frontend、backend、postgres、chroma
- Nginx / Caddy 做 HTTPS 和反向代理

优点：最贴近当前项目结构，Chroma 和 ffmpeg/yt-dlp 好控制。

风险：需要服务器运维，域名和 HTTPS 配置需要手动处理。

### 路线 C：生产 SaaS 路线

- Frontend：Vercel
- Backend Worker/API：Railway/Render/Fly.io
- Database：Supabase
- Queue：Redis + RQ/Celery
- Storage：S3/R2
- Vector：Pinecone 或托管向量库

优点：长期可扩展。

风险：改动较大，不适合马上一步到位。

## 8. 下一阶段建议

建议先选择路线：

1. 如果目标是作品集展示：选择路线 A。
2. 如果目标是完整跑通视频处理：选择路线 B。
3. 如果目标是长期 SaaS：从路线 A 起步，逐步演进到路线 C。

待确认问题：

- 是否已有域名？
- 是否愿意使用 Vercel / Render / Railway / Supabase？
- 是否接受第一版线上只做 Demo，视频处理能力后续增强？
- DeepSeek Key 是否已经轮换并准备配置到生产平台？
- ChromaDB 生产阶段是继续用 Chroma，还是暂时关闭 RAG 写入功能？

