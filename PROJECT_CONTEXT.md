# 项目上下文

> 最后更新：2026-08-26
> 来源以仓库代码、配置、构建结果和 Git 历史为准；不记录任何真实密钥。

## 项目基本信息

- 项目名称：VideoMind AI
- 项目目标：把用户收藏但没时间看的视频转化为结构化笔记、个人视频知识库和可对话的 AI 记忆空间。
- 目标用户：学习者、内容创作者、产品/技术研究者，以及需要沉淀视频资料的知识工作者。

## 当前阶段

- 已完成 Phase 1-6：项目初始化、后端基础 API、视频处理 Pipeline、AI Agent、RAG 基础能力、前端 UI 基础与视觉重构。
- 当前进入 Phase 7：本地生产化基础。
- 部署路线：本地优先，随后采用 Vercel + Render + Supabase 上线作品集版本，再演进到任务队列和正式多用户 SaaS。
- 最新 GitHub 同步提交：`ffc556c Add deployment audit and project context`。

## 技术架构

- Frontend：Next.js 16.3.3、React 19、TypeScript、Tailwind CSS、lucide-react。
- Backend：Python 3.12、FastAPI、SQLAlchemy、PostgreSQL、Loguru、LangGraph。
- AI Provider：默认 DeepSeek，OpenAI SDK 仅作为 OpenAI-compatible client 使用。
- ASR：默认 `ASR_PROVIDER=disabled`；无字幕视频后续建议接本地 faster-whisper。
- Vector Store：ChromaDB；Embedding 当前为本地 deterministic hash embedding，后续建议替换为中文向量模型。
- 本地编排：Docker Compose 管理 PostgreSQL、ChromaDB、Adminer、backend、frontend。

## 已验证

- `frontend`: `npm run typecheck` 通过。
- `frontend`: `npm run build` 通过。
- `frontend`: `npm run lint` 通过，`npm audit --omit=dev` 为 0 vulnerabilities。
- `backend`: `python3 -m compileall backend/app` 通过。
- `backend`: Docker 内 pytest 4 项通过；全新 PostgreSQL Alembic 首次迁移通过。
- Docker：frontend/backend 生产镜像构建通过；前端生产容器 `/` 和 `/library` 返回 200。
- 本地前端主要页面 `/`、`/dashboard`、`/library`、`/chat` 返回 200。
- GitHub remote：`git@github.com:17-chen/videomind-ai.git`。

## 已知风险

- Alembic 首次迁移和生产 Docker 镜像已经通过本地验收。
- 后台任务使用 FastAPI BackgroundTasks，生产环境应改为队列系统。
- ChromaDB 尚未确认生产托管方式；可先本地/单机 Docker，正式环境需选择托管或持久化策略。
- 视频下载依赖 yt-dlp、ffmpeg 和目标平台策略，云平台运行时可能需要额外系统依赖、cookie 或代理策略。
- 当前 demo user 机制不等于生产认证；多用户 SaaS 还需要正式登录、权限隔离和密钥管理。

## 下一步

- [ ] 完成 Phase 7 的 migration、生产镜像和本地闭环验收。
- [ ] Phase 8 接入本地 ASR 和中文 Embedding。
- [ ] Phase 9 配置 Vercel、Render、Supabase、Storage 和 pgvector。
- [ ] Phase 10 引入认证、任务队列、监控和配额。
