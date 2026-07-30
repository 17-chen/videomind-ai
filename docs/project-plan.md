# VideoMind AI 项目书

## 1. 项目概述

VideoMind AI 是一个 AI 视频知识管理平台，目标是把用户收藏但没有时间观看的视频，自动转化为结构化笔记、可检索知识库和可对话的个人知识资产。

核心价值：

- 降低长视频学习成本。
- 将分散在抖音、Bilibili、YouTube 等平台的视频内容统一沉淀。
- 用 AI 自动生成摘要、关键词、时间线和行动建议。
- 用 RAG 支持用户跨视频提问和复盘。

## 2. 目标用户

- 经常收藏课程、访谈、创业、技术、财经类视频的学习者。
- 希望把视频内容整理成笔记的内容创作者和研究者。
- 需要管理大量视频资料的产品经理、开发者、学生和知识工作者。

## 3. MVP 范围

MVP 重点不是做一个泛视频下载器，而是跑通“视频输入 -> 转写 -> AI 理解 -> 知识库 -> 对话”的完整闭环。

第一版支持：

- Bilibili / 抖音 URL 提交。
- 视频下载与音频提取。
- 字幕优先，缺失字幕时使用 Whisper ASR。
- 结构化 AI 分析 JSON。
- Markdown 笔记生成。
- PostgreSQL 保存视频、转写、摘要。
- ChromaDB 保存向量。
- Chat With My Videos。
- Next.js SaaS 风格前端。

## 4. 技术架构

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
- Loguru
- Alembic

### AI / Pipeline

- yt-dlp：视频下载与元信息获取
- ffmpeg：音频提取
- 字幕优先：优先使用平台字幕生成 transcript
- ASR：默认不使用 OpenAI；后续可接本地 Whisper / faster-whisper
- DeepSeek LLM：内容理解和笔记生成
- LangGraph：Agent Pipeline 编排
- ChromaDB：向量检索

## 5. 数据模型

- User：用户账号
- Video：视频元信息、来源、处理状态、文件路径
- Transcript：视频转写文本
- Summary：AI 摘要、关键词、分类、Markdown 笔记
- Embedding：向量数据库 ID 映射

## 6. 开发阶段

### Phase 1：项目初始化

- 建立 monorepo 项目结构
- Docker Compose
- 环境变量模板
- README
- 架构与 API 文档

### Phase 2：Backend 基础 API

- FastAPI 应用入口
- 配置系统
- 日志系统
- 错误处理
- PostgreSQL 连接
- SQLAlchemy 模型
- `POST /api/v1/videos`
- `GET /api/v1/videos`
- `GET /api/v1/videos/{id}`

### Phase 3：视频处理 Pipeline

- URL 视频下载
- 视频元信息提取
- 字幕文件获取和解析
- ffmpeg 音频提取
- Whisper ASR fallback
- Transcript 入库
- 处理状态更新

### Phase 4：AI Agent

- LangGraph Pipeline
- Video Analysis Agent
- 独立 prompt 文件
- JSON 分析结果
- Markdown 笔记生成

当前基础实现：

- `backend/app/prompts/analysis_prompt.txt`
- `backend/app/agents/video_analysis_agent.py`
- `POST /api/v1/videos/{id}/analyze`

### Phase 5：RAG 系统

- Embedding 生成
- ChromaDB 写入
- 语义检索
- Chat With My Videos

当前基础实现：

- `backend/app/services/embeddings.py`
- `backend/app/services/vector_store.py`
- `backend/app/services/rag.py`
- `POST /api/v1/videos/{id}/embed`
- `POST /api/v1/chat`

说明：DeepSeek 当前用于 LLM 分析和问答。Embedding 层先使用本地 deterministic hash embedding，保证不依赖 OpenAI，也方便后续替换为更强的中文向量模型。

### Phase 6：Frontend

- Landing Page
- Dashboard
- Library Page
- Video Detail Page
- Chat Page
- 响应式 UI

当前基础实现：

- `frontend/app/page.tsx`
- `frontend/app/dashboard/page.tsx`
- `frontend/app/library/page.tsx`
- `frontend/app/videos/[id]/page.tsx`
- `frontend/app/chat/page.tsx`
- `frontend/components/*`

说明：Phase 6 先实现中文优先、可运行、可演示的应用骨架。视觉风格保持克制，后续可以在此基础上继续向 Notion、Linear、Perplexity 的方向精修。

## 7. 当前风险

- 抖音和 Bilibili 的下载能力依赖平台策略、登录状态和 yt-dlp 支持情况。
- DeepSeek API Key 用于 Phase 4 的 AI 分析和 Phase 5 的 RAG 回答生成。
- DeepSeek 官方接口主要用于 Chat/Reasoner 场景；Embedding 层暂不假设 DeepSeek 提供能力。
- DeepSeek 不提供 Whisper 风格音频转写；没有字幕的视频需要后续接本地 ASR。
- 当前任务执行使用 FastAPI BackgroundTasks，适合 MVP；生产环境应升级为 Celery、RQ 或 Dramatiq。
- 当前开发阶段使用 `create_all` 自动建表，生产环境应切换到 Alembic migration。
- 视频文件本地存储适合开发和 Demo，生产环境应迁移到对象存储。

## 8. 验收标准

Phase 5 完成后应满足：

- 可以创建视频记录。
- 可以触发视频处理任务。
- 系统能下载视频或返回明确失败原因。
- 系统能优先读取字幕。
- 无字幕时能提取音频并调用 Whisper。
- Transcript 能保存到数据库。
- Video 状态能从 `queued` 到 `processing`，最终变为 `completed` 或 `failed`。
- 可以基于 transcript/summary 写入 ChromaDB。
- 可以通过 `/api/v1/chat` 向个人视频知识库提问。
