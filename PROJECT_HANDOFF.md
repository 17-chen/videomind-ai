# VideoMind AI 项目交接

> 更新：2026-10-15。供一段时间未开发后恢复工作；以本地代码和当时的实测结果为准。

## 项目介绍

把 Bilibili、抖音等收藏视频转成转写文本、AI 笔记、个人知识库和可引用来源的视频问答。当前产品主要是本地 Demo，计划逐步上线作品集版本。

## 当前目标与阶段

- Phase 1–6 的基础实现已有代码：项目骨架、视频 API、字幕优先处理、AI 分析、RAG 基础和中文前端。
- Phase 7 的 Alembic、生产构建和健康检查基础此前已验证；真实视频全流程仍待验收。
- 当前 Sprint 02：Supabase 认证与用户隔离。2026-10-08 已补 Auth 服务校验、邮箱冲突保护、页面会话刷新与退出入口；认证代码已随 `8f8047d` 提交，仍没有接入真实 Supabase 项目。
- 代码仓库：`/Users/chenxin/Documents/Codex 2/videomind-ai`；Git remote 为 `git@github.com:17-chen/videomind-ai.git`。

## 2026-10-15 开工快照

- 当前分支 `main`；开工时最近提交为 `d3637fd`，工作树干净且与 GitHub 一致。此前本地 AI、分段索引和向量重建工具已提交，不再是未提交工作。
- 本轮补齐知识库分页、筛选保留、AI 摘要搜索和全库分类入口；后端 52 项测试、Ruff、前端 typecheck/lint/build 与 43 条虚构数据的生产页面检查通过。
- `.env` 在本地且不提交；真实 Supabase 和服务商验收仍未完成。先检查实际 Git 状态再继续修改，不要按历史工作树描述执行清理。

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

1. 核对 Git 状态、Colima 开发容器和最近的验证记录；当前已无上轮待保护的未提交改动。
2. 配置测试用 Supabase 项目，验收注册、登录、退出、过期令牌、用户 A/B 数据隔离和迁移；再提交 Sprint 02 代码。
3. 选一个有字幕的真实视频完成 URL 到问答闭环，记录每一阶段结果与失败原因。
4. 可选无字幕 ASR 和中文 embedding 已实现，继续真实效果验收，再推进文件上传、生产任务队列与持久化存储。
5. 上线前复核 API 文档、部署审计和当前版本，避免沿用早期计划的旧结论。

## 安全的恢复命令

```bash
cd '/Users/chenxin/Documents/Codex 2/videomind-ai'
git status --short --branch
git diff --check
git log -5 --oneline
curl --max-time 5 http://localhost:8001/api/v1/health/ready
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

## 2026-10-11 恢复提示

本机另一 Python 项目占用了 `127.0.0.1:8000`。VideoMind 本地 `.env` 已将宿主机 API 改为 8001，前端浏览器 API 地址同步改为 8001；容器内部 API 仍为 8000。不要用 `localhost:8000` 的健康响应判断 VideoMind 状态，先检查 `/openapi.json` 是否有 `/api/v1/videos`。本轮 29 项后端测试、全量 Ruff、前端 typecheck/lint/build 及本地 CRUD 冒烟通过；真实 Supabase 和付费模型仍未验收。详见 [运行与功能核查](docs/VERIFICATION_2026-10-11.md)。

## 2026-10-12 本地能力更新

新增可选 faster-whisper 和 BGE 中文模型，默认不安装；BGE 分段后需要运行 `python -m scripts.reindex_vectors` 为已有视频重新入库。单进程本地服务重启会把中断任务标记为失败以便重试。后端 38 项测试和 Ruff、前端 typecheck/lint/build 通过；真实模型文件没有下载，效果未验收。详细启用方式见 [本地 AI 配置](docs/LOCAL_AI.md)。

## 2026-10-13 恢复提示

未提交工作树继续增加索引安全更新与设置页转写模式提示。后端 41 项测试与 Ruff、前端 typecheck/lint/build 通过。开发容器的自动重载未加载宿主机改动，确认没有活跃任务后重启前后端，在线 API 才返回新字段；详见 [本轮核查](docs/VERIFICATION_2026-10-13.md)。

## 2026-10-15 知识库更新

`/library` 用 `page` 参数分页，每页 20 条，超过末页时跳回末页；搜索和分类会保留在翻页链接中，重新提交筛选从第一页开始。`GET /api/v1/videos/categories` 返回当前用户全部非空分类，不受当前页限制。后端搜索已包含 AI 标题和摘要。详见 [本轮核查](docs/VERIFICATION_2026-10-15.md)。
