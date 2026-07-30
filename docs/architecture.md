# VideoMind AI 架构设计

## 产品目标

VideoMind AI converts collected videos into durable personal knowledge assets:

```text
Input -> Processing -> Understanding -> Notes -> Library -> RAG Chat
```

## 系统边界

- **Frontend:** Next.js 15、React、TypeScript、Tailwind CSS、shadcn/ui。
- **Backend:** Python FastAPI，服务层使用 Type Hint 保持边界清晰。
- **Database:** PostgreSQL + SQLAlchemy。
- **Vector Database:** ChromaDB 优先，后续通过适配层扩展 Pinecone。
- **AI Providers:** 默认 DeepSeek；通过 provider 封装保留未来接入 Gemini、Claude、OpenAI-compatible 服务的空间。
- **Embedding:** Phase 5 使用本地 deterministic hash embedding 跑通闭环，后续建议升级为 bge-m3 或 sentence-transformers 中文向量模型。
- **Agent Runtime:** LangGraph 用于视频理解工作流。

## 后端模块规划

```text
app/
├── api/          HTTP routes and dependencies
├── agents/       LangGraph workflows and agent state
├── core/         settings, logging, security, errors
├── database/     engine, sessions, migrations, repositories
├── models/       SQLAlchemy models
├── prompts/      versioned prompt templates
├── schemas/      Pydantic request/response schemas
├── services/     video, transcript, AI, embedding, RAG services
└── utils/        shared helpers
```

## 数据模型规划

- **User:** 视频知识库的归属用户。
- **Video:** 视频 URL 或上传元信息、处理状态、标题、时长、封面。
- **Transcript:** 标准化视频转写文本。
- **Summary:** 结构化 AI 分析、关键词、分类和 Markdown 笔记。
- **Embedding:** 视频记录与向量数据库 ID 的映射。

## Agent 工作流规划

```text
Input Agent
-> Transcript Agent
-> Analysis Agent
-> Summary Agent
-> Embedding Agent
-> Knowledge Agent
```

每一步尽量保持幂等，方便失败任务从已完成节点继续恢复。

## 存储规划

开发阶段使用本地存储：

- `storage/videos`
- `storage/audio`
- `storage/transcripts`
- `storage/notes`
- `storage/tmp`

生产环境应把大文件迁移到对象存储。

## 错误处理和日志

- 后端异常统一通过 FastAPI exception handlers 输出。
- 服务层抛出业务异常，避免泄漏底层 provider 细节。
- 日志应尽量包含 video id、user id、provider 和处理阶段。
- API Key、密码哈希等敏感值不能写入日志。

## 扩展点

- 视频源适配：抖音、Bilibili 优先，后续 TikTok、YouTube。
- AI provider 适配：DeepSeek 默认，后续 Gemini、Claude、OpenAI-compatible 服务。
- 向量库适配：ChromaDB 优先，后续 Pinecone。
- 浏览器收藏：未来 Chrome Extension 可复用 `/videos` API。
- 多模态理解：后续抽帧和视觉分析结果可以附加到 transcript 上下文。
