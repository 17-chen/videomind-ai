# VideoMind AI 当前技术架构

> 核对日期：2026-10-21。描述仓库中的实现与已知边界；不把规划功能写成已完成。

## 系统总览

```text
浏览器 / Next.js 16 前端
    │  HTTP + 可选 Supabase access token
    ▼
FastAPI /api/v1
    ├─ PostgreSQL：用户、视频、转写、摘要、任务、向量 ID 映射
    ├─ 独立 Worker：领取持久任务、维护租约、按阶段执行
    ├─ 本地文件：视频、音频、Markdown 笔记
    ├─ yt-dlp + ffmpeg：下载和音频提取
    ├─ DeepSeek：视频分析与问答生成
    └─ ChromaDB + local_hash（默认）或 bge_zh（可选）：当前 RAG 检索
```

本地开发由 `docker-compose.yml` 编排 PostgreSQL、Adminer、后端、前端和 Worker；Chroma 默认嵌入后端，可选独立服务。前端使用 Next.js 16.3.3、React 19、TypeScript、Tailwind；后端使用 Python 3.12、FastAPI、SQLAlchemy、Alembic、LangGraph。前端容器访问后端可用 `INTERNAL_API_BASE_URL`，浏览器使用 `NEXT_PUBLIC_API_BASE_URL`。

资料编辑使用 `Video.user_category` 覆盖 AI 分类，`Summary.note_is_manual` 标记手工笔记；再次 AI 分析保留手工内容。已入库资料更新时先提交 PostgreSQL 并标记 `index_sync_error`，再更新 Chroma；失败保留旧向量并提供重试。跨存储不具原子性，运行中的单视频编辑会被拒绝。

## 业务流程与状态

1. 前端提交 Bilibili/抖音 URL 或分享文本，或上传本地视频；后端创建归属于当前用户的 Video 记录。上传使用服务端 ID 命名、哈希防本人重复及 ffprobe 内容校验。
2. `POST /videos/{id}/process` 创建持久任务，由 Worker 执行：URL 视频由 yt-dlp 下载并优先解析字幕；本地上传直接读取本人已保存文件。没有字幕时提取音频并调用配置的 ASR Provider；转写存入 Transcript。
3. `POST /videos/{id}/analyze` 使用 LangGraph Video Analysis Agent 和 DeepSeek，生成结构化 Summary 与 Markdown 笔记。
4. `POST /videos/{id}/embed` 拼接视频、转写和摘要文本，默认用 local_hash 生成向量；可选 bge_zh 对长文档分段。向量写入 Chroma，PostgreSQL 保存视频级向量 ID。
5. `POST /chat` 按 user_id 检索 Chroma 结果，再调用 DeepSeek 生成中文回答并返回视频来源。

视频详情可调用 `POST /videos/{id}/run` 创建完整任务；分步处理、分析、入库也走同一队列。`VideoTask` 记录归属、阶段、尝试次数、租约和取消请求。多个 Worker 通过 PostgreSQL `FOR UPDATE SKIP LOCKED` 竞争领取，Worker 失联后由租约恢复；可能已经计费且未落库的分析/云端转写不会自动重试。取消在阶段边界检查，不能中断进行中的外部调用。状态枚举还包括 cancelled；真实付费服务与多实例长期运行仍待验收。

视频删除使用 `DELETE /videos/{id}`：先锁定本人且非处理中的记录，以视频 ID 和 user_id 清理 Chroma，随后删除数据库记录与关联内容，最后清理本地生成文件。向量库不可用时会保留数据库记录；跨存储尚无原子事务，数据库失败后可重新索引。

## 模块和数据

| 层 | 主要文件 | 当前职责 |
| --- | --- | --- |
| 页面与交互 | `frontend/app/`、`frontend/components/` | 首页、Dashboard、Library、视频详情、Chat、认证页面 |
| 前端 API 与会话 | `frontend/lib/api.ts`、`frontend/lib/supabase/` | API 地址、Bearer token、Supabase 客户端 |
| HTTP API | `backend/app/api/v1/routes/` | 视频、聊天和健康检查 |
| 视频处理 | `backend/app/services/video_processing/` | 下载、字幕解析、音频提取、转写、状态更新 |
| AI 与检索 | `backend/app/agents/`、`backend/app/services/{analysis,rag,embeddings,vector_store}.py` | 分析、笔记、向量化和问答 |
| 持久化 | `backend/app/models/`、`backend/alembic/` | VideoTask、其他业务模型、迁移和独立 Worker |

User 与 Video 是一对多；Video 与 Transcript、Summary、Embedding 是一对一。视频列表和详情按当前用户查询；Chroma 查询也带 user_id 过滤。真实多用户隔离尚需双用户运行测试。

## 认证边界

- 默认 `AUTH_MODE=demo`：请求使用自动创建的 demo user，方便本地开发；不适合公开多用户服务。
- 已实现的 `AUTH_MODE=supabase`：前端注册/登录与会话，后端向 Supabase Auth `/auth/v1/user` 验证 Bearer token，按 `auth_subject` 映射本地 User；邮箱冲突不会自动合并。代码已提交，真实 Supabase 项目仍待配置与验收。
- 后端需要 `SUPABASE_URL` 与 `SUPABASE_ANON_KEY`，不再要求 JWT Secret；每次认证请求依赖 Supabase Auth 可用。接入真实项目后须做令牌刷新与双用户隔离测试。

## 当前限制

- `ASR_PROVIDER=disabled` 为默认值；可选 faster-whisper 本地转写已有接入，或使用当前用户的 OpenAI 转写密钥。真实音频与外部调用尚未验收。
- `local_hash` 仅是确定性向量方案，用于流程验证；中文语义检索效果待更合适的模型验证。
- 可选 `bge_zh` 使用单独集合和分段向量；切换模型后需要运行重新入库脚本，真实中文检索质量仍待评测。
- PostgreSQL 任务队列已提供跨 API 重启持久化和独立 Worker；真实 Worker 强制中断、长任务心跳、生产多实例和付费步骤恢复仍待完整演练。
- 本地 `storage/` 不等于云端持久对象存储；Chroma 生产持久化/pgvector 迁移未完成。
- 本地上传和资料编辑已有实现；上传到真实 ASR、笔记、入库仍待实际服务验收。
- 视频下载依赖平台规则、网络、Cookie 和 yt-dlp 版本；必须用真实 URL 验证。

## 下一步技术演进

按 [阶段路线图](roadmap.md) 完成认证和真实视频闭环，再补 ASR、中文 embedding、可靠队列与云端持久化。长期选择以 [技术决策日志](../DECISION_LOG.md) 为准。

## 检索评测边界

`scripts.evaluate_retrieval` 通过客户端注入，使用独立的 Chroma EphemeralClient 和固定语料，结束后清理内存集合。该命令不使用数据库和持久向量数据，只评估视频级检索与用户隔离。默认 `ChromaVectorStore()` 仍使用上述嵌入式或 HTTP 生产配置；评测不是公开 HTTP 功能。指标和语料边界见 [中文检索评测](RETRIEVAL_EVALUATION.md)。

## 用户模型配置（2026-10-08）

`GET/PUT/DELETE /api/v1/settings/ai` 只面向当前认证用户。`ai_settings` 表以 `user_id` 唯一关联 User；DeepSeek/OpenAI 端点固定在服务端，用户可选择模型名并提交自己的 API Key。密钥由独立的 `USER_API_KEY_ENCRYPTION_KEY` 用 Fernet 加密，响应只返回配置状态，不返回明文。分析、RAG 问答和无字幕转写从关联用户读取配置。`AUTH_MODE=supabase` 下若用户未配置，调用失败并提示设置，绝不回退到服务器 `.env` 的项目所有者 Key；`demo` 模式仅用于本地测试，设置写入接口拒绝保存个人密钥。

## 本地向量库模式（2026-10-08）

本地默认 `CHROMA_MODE=embedded`，`ChromaVectorStore` 使用 `PersistentClient`，数据落在 `storage/chroma/`。独立 Chroma 服务仍可通过 `CHROMA_MODE=http` 与 Compose `remote-chroma` profile 使用。就绪检查包括 PostgreSQL 与向量库；嵌入式模式仅用于单实例本地开发，生产需要评估服务端部署及持久卷。
