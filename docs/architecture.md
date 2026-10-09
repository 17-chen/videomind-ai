# VideoMind AI 当前技术架构

> 核对日期：2026-10-08。描述仓库中的实现与已知边界；不把规划功能写成已完成。

## 系统总览

```text
浏览器 / Next.js 16 前端
    │  HTTP + 可选 Supabase access token
    ▼
FastAPI /api/v1
    ├─ PostgreSQL：用户、视频、转写、摘要、向量 ID 映射
    ├─ 本地文件：视频、音频、Markdown 笔记
    ├─ yt-dlp + ffmpeg：下载和音频提取
    ├─ DeepSeek：视频分析与问答生成
    └─ ChromaDB + local_hash embedding：当前 RAG 检索
```

本地开发由 `docker-compose.yml` 默认编排 PostgreSQL、Adminer、后端和前端；Chroma 默认嵌入后端，可选独立服务。前端使用 Next.js 16.3.3、React 19、TypeScript、Tailwind；后端使用 Python 3.12、FastAPI、SQLAlchemy、Alembic、LangGraph。前端容器访问后端可用 `INTERNAL_API_BASE_URL`，浏览器使用 `NEXT_PUBLIC_API_BASE_URL`。

## 业务流程与状态

1. 前端提交 Bilibili/抖音 URL 或分享文本；后端创建归属于当前用户的 Video 记录。
2. `POST /videos/{id}/process` 启动 BackgroundTask：yt-dlp 下载视频及字幕；有字幕时解析字幕，没有时提取音频并调用配置的 ASR Provider；转写存入 Transcript。
3. `POST /videos/{id}/analyze` 使用 LangGraph Video Analysis Agent 和 DeepSeek，生成结构化 Summary 与 Markdown 笔记。
4. `POST /videos/{id}/embed` 拼接视频、转写和摘要文本，用 local_hash 生成向量并写入 Chroma，同时在 PostgreSQL 保存向量 ID。
5. `POST /chat` 按 user_id 检索 Chroma 结果，再调用 DeepSeek 生成中文回答并返回视频来源。

视频详情现在也可调用 `POST /videos/{id}/run`，由单个 BackgroundTask 依次执行上述三步；重复启动通过数据库状态原子校验拒绝，失败后重试复用已保存的转写与笔记。这个任务不具备跨进程或重启后的恢复能力。状态枚举包括 created、queued、processing、downloading、transcribing、analyzing、embedding、completed、failed；“有状态字段”不等于每个阶段均经真实视频验证。

## 模块和数据

| 层 | 主要文件 | 当前职责 |
| --- | --- | --- |
| 页面与交互 | `frontend/app/`、`frontend/components/` | 首页、Dashboard、Library、视频详情、Chat、认证页面 |
| 前端 API 与会话 | `frontend/lib/api.ts`、`frontend/lib/supabase/` | API 地址、Bearer token、Supabase 客户端 |
| HTTP API | `backend/app/api/v1/routes/` | 视频、聊天和健康检查 |
| 视频处理 | `backend/app/services/video_processing/` | 下载、字幕解析、音频提取、转写、状态更新 |
| AI 与检索 | `backend/app/agents/`、`backend/app/services/{analysis,rag,embeddings,vector_store}.py` | 分析、笔记、向量化和问答 |
| 持久化 | `backend/app/models/`、`backend/alembic/` | User、Video、Transcript、Summary、Embedding 模型与迁移 |

User 与 Video 是一对多；Video 与 Transcript、Summary、Embedding 是一对一。视频列表和详情按当前用户查询；Chroma 查询也带 user_id 过滤。真实多用户隔离尚需双用户运行测试。

## 认证边界

- 默认 `AUTH_MODE=demo`：请求使用自动创建的 demo user，方便本地开发；不适合公开多用户服务。
- 待接入的 `AUTH_MODE=supabase`：前端注册/登录与会话，后端向 Supabase Auth `/auth/v1/user` 验证 Bearer token，按 `auth_subject` 映射本地 User；邮箱冲突不会自动合并。相关代码目前未提交，且本地 Supabase 配置缺失。
- 后端需要 `SUPABASE_URL` 与 `SUPABASE_ANON_KEY`，不再要求 JWT Secret；每次认证请求依赖 Supabase Auth 可用。接入真实项目后须做令牌刷新与双用户隔离测试。

## 当前限制

- `ASR_PROVIDER=disabled` 为默认值；Supabase 用户可在设置中提供自己的 OpenAI 转写密钥处理无字幕视频，真实外部调用尚未验收。`faster-whisper` 属计划，不是已接入能力。
- `local_hash` 仅是确定性向量方案，用于流程验证；中文语义检索效果待更合适的模型验证。
- BackgroundTasks 不提供跨重启持久化、可靠重试或队列隔离；长视频生产处理待改造。
- 本地 `storage/` 不等于云端持久对象存储；Chroma 生产持久化/pgvector 迁移未完成。
- 上传本地视频文件接口、笔记编辑、自动分类修改等初始需求尚未实现或未验收。
- 视频下载依赖平台规则、网络、Cookie 和 yt-dlp 版本；必须用真实 URL 验证。

## 下一步技术演进

按 [阶段路线图](roadmap.md) 完成认证和真实视频闭环，再补 ASR、中文 embedding、可靠队列与云端持久化。长期选择以 [技术决策日志](../DECISION_LOG.md) 为准。

## 用户模型配置（2026-10-08）

`GET/PUT/DELETE /api/v1/settings/ai` 只面向当前认证用户。`ai_settings` 表以 `user_id` 唯一关联 User；DeepSeek/OpenAI 端点固定在服务端，用户可选择模型名并提交自己的 API Key。密钥由独立的 `USER_API_KEY_ENCRYPTION_KEY` 用 Fernet 加密，响应只返回配置状态，不返回明文。分析、RAG 问答和无字幕转写从关联用户读取配置。`AUTH_MODE=supabase` 下若用户未配置，调用失败并提示设置，绝不回退到服务器 `.env` 的项目所有者 Key；`demo` 模式仅用于本地测试，设置写入接口拒绝保存个人密钥。

## 本地向量库模式（2026-10-08）

本地默认 `CHROMA_MODE=embedded`，`ChromaVectorStore` 使用 `PersistentClient`，数据落在 `storage/chroma/`。独立 Chroma 服务仍可通过 `CHROMA_MODE=http` 与 Compose `remote-chroma` profile 使用。就绪检查包括 PostgreSQL 与向量库；嵌入式模式仅用于单实例本地开发，生产需要评估服务端部署及持久卷。
