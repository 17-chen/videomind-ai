# VideoMind AI 项目交接

> 生成：2026-10-08。供一段时间未开发后恢复工作；以本地代码和当时的实测结果为准。

## 项目介绍

把 Bilibili、抖音等收藏视频转成转写文本、AI 笔记、个人知识库和可引用来源的视频问答。当前产品主要是本地 Demo，计划逐步上线作品集版本。

## 当前目标与阶段

- Phase 1–6 的基础实现已有代码：项目骨架、视频 API、字幕优先处理、AI 分析、RAG 基础和中文前端。
- Phase 7 的 Alembic、生产构建和健康检查基础此前已验证；真实视频全流程仍待验收。
- 当前 Sprint 02：Supabase 认证与用户隔离。2026-10-08 已补 Auth 服务校验、邮箱冲突保护、页面会话刷新与退出入口；代码尚未提交，也没有接入真实 Supabase 项目。
- 代码仓库：`/Users/chenxin/Documents/Codex 2/videomind-ai`；Git remote 为 `git@github.com:17-chen/videomind-ai.git`。

## 2026-10-08 工作树快照

- 当前分支 `main`；本地最近提交 `1de8974`，日期 2026-08-26，标题 `Build Phase 7 production foundations`。
- 开始本轮开发前有 37 个已修改或未跟踪的文件，主要是 2026-09-04 的认证基础、分享文本解析和配套文档；本轮又增加了认证和文档改动。不要在没有核对 diff 前执行清理、重置或覆盖。
- `.env` 在本地且不提交；当前未配置 Supabase，`AUTH_MODE` 未设置，因此使用默认 `demo`。DeepSeek Key 在本地被检测为已设置；本文不记录其值。

## 重要入口

- 前端页面：`frontend/app/`；API 客户端：`frontend/lib/api.ts`；认证：`frontend/lib/supabase/` 和 `frontend/components/auth-form.tsx`。
- 后端入口：`backend/app/main.py`；接口：`backend/app/api/v1/routes/`；视频处理：`backend/app/services/video_processing/`。
- AI 分析：`backend/app/agents/video_analysis_agent.py`；RAG：`backend/app/services/rag.py`、`vector_store.py`、`embeddings.py`。
- 数据模型和迁移：`backend/app/models/`、`backend/alembic/`；认证：`backend/app/services/auth.py`、`backend/app/api/dependencies.py`。
- 配置模板：`.env.example`；本地编排：`docker-compose.yml`。
- 文档入口：[项目资料](docs/PROJECT_MATERIALS.md)、[当前架构](docs/architecture.md)、[阶段路线图](docs/roadmap.md)。

## 已确认的技术决策

- 本地优先；作品集上线计划为 Vercel + Render + Supabase，向量层拟由 Chroma 转向 pgvector。
- DeepSeek 用于分析与回答；当前本地 hash embedding 仅验证检索流程，不代表高质量中文语义检索。
- 在扩展 Library 前优先建立真实认证和用户隔离，同时保留本地 demo 模式。
- 长视频后台工作当前依赖 FastAPI BackgroundTasks，生产环境需要可靠队列。

详见 [DECISION_LOG](DECISION_LOG.md)。

## 验证状态与风险

- 2026-10-08：起初前端超时，原因是旧容器内 `/app` bind mount 为空；使用 Colima socket 重新创建前后端容器后，首页、认证页、Dashboard、Library、Chat 与后端 readiness 均返回 200。
- 前端在隔离副本中通过 typecheck、lint、生产构建；后端在实际 Python 3.12 容器中通过 16 项测试，当时 Alembic 版本为 `20260904_0002`；此后已迁移至 `20261008_0004`。
- 使用临时测试配置验证未登录访问 Dashboard、Library、Chat 均重定向至 `/auth`。工作台和知识库在后端不可用时显示错误面板。预览首页示意数据已标明，视频详情会刷新处理状态。真实 Supabase 注册、令牌刷新和双用户登录尚未运行验收。
- 真实 Supabase 注册、登录、退出、JWT 与用户数据隔离尚未完成运行验收。
- 完整视频 URL → 转写 → 分析 → 向量写入 → 问答尚未以真实样例完成验收；无字幕视频因默认 ASR 关闭而不能自动转写。
- 普通 shell 默认 Docker context 指向 Docker Desktop；本机项目容器使用 Colima socket。不要把默认 context 的连接失败误判为 Docker 容器停机。

## 下一步开发顺序

1. 保护并审查现有未提交改动；修复前端无法响应和 Docker 环境后，重跑前后端测试。
2. 配置测试用 Supabase 项目，验收注册、登录、退出、过期令牌、用户 A/B 数据隔离和迁移；再提交 Sprint 02 代码。
3. 选一个有字幕的真实视频完成 URL 到问答闭环，记录每一阶段结果与失败原因。
4. 再补无字幕 ASR、中文 embedding、文件上传，以及生产任务队列和持久化存储。
5. 上线前复核 API 文档、部署审计和当前版本，避免沿用早期计划的旧结论。

## 安全的恢复命令

```bash
cd '/Users/chenxin/Documents/Codex 2/videomind-ai'
git status --short --branch
git diff --check
git log -5 --oneline
curl --max-time 5 http://localhost:8000/health
DOCKER_HOST=unix:///Users/chenxin/.colima/default/docker.sock docker compose ps
```

如果 Docker 未运行，先恢复运行环境；不要直接把“容器不存在”当作业务代码回归。不要把 `.env` 输出到聊天、日志或提交中。

## 2026-10-08 新增能力

- `/settings` 提供中文模型设置及中英文切换；Next.js 自带的英文 Preferences 已从开发预览隐藏。
- 用户 DeepSeek/OpenAI 密钥加密存于 `ai_settings`，支持可选独立 OpenAI 转写密钥；已认证用户的分析、问答、转写只使用自己的密钥。`USER_API_KEY_ENCRYPTION_KEY` 在本地 `.env`，不能提交或丢失。
- Alembic 已至 `20261008_0004`。本地 PostgreSQL 设置保存、读取、删除通过；测试值已清理，demo 模式随后禁止保存个人密钥。当前仍是 demo 模式，需配置 Supabase 并完成双用户真实验收后才能对外开放。

## 2026-10-08 本地向量库恢复

`CHROMA_MODE=embedded` 为本地默认，Chroma 数据写入 `storage/chroma/`（已忽略 Git）；`remote-chroma` profile 保留服务端模式。PostgreSQL 与向量库就绪检查均通过，本地向量写入、重开、按用户过滤检索通过。真实视频与付费模型全链路仍未验收。

## 2026-10-08 一键处理更新

`POST /api/v1/videos/{id}/run` 与详情页按钮已串联字幕、分析、入库。测试用模拟下载、模型和向量库验证首次写入失败后重试只重做入库；24 项后端测试通过。真实视频、真实模型服务商和 Supabase 双用户仍待验收。后台为单进程 BackgroundTasks，重启后不会自动恢复挂起任务。
