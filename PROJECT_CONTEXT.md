# 项目上下文

> 最后核对：2026-10-09。优先以仓库代码、Git 状态和本次实测为准；不记录真实密钥。完整文档索引见 [项目资料入口](docs/PROJECT_MATERIALS.md)。

## 项目基本信息

- **名称：**VideoMind AI。
- **目标：**把收藏但没时间看的视频转成结构化笔记、可检索知识库和可追溯来源的问答。
- **实际代码仓库：**`/Users/chenxin/Documents/Codex 2/videomind-ai`，Git remote `git@github.com:17-chen/videomind-ai.git`。
- **目标用户：**学习者、内容创作者和管理视频资料的知识工作者。

## 当前阶段

Phase 1–6 已有基础实现。Phase 7 的迁移、健康检查和生产构建基础此前通过验证，但真实视频端到端流程未验收。当前处于 Sprint 02 的 Supabase 用户系统接入：认证、用户映射、登录页和分享链接修复的代码已在本地工作树；2026-10-08 又补了 Auth 服务校验、邮箱冲突保护、页面会话刷新与退出入口。这些改动尚未提交，也未连接真实 Supabase 项目。项目现阶段是本地演示，不是正式多用户 SaaS。

**Git 快照：**本地 `main` 最近提交为 `1de8974`（2026-08-26，Phase 7 基础）；2026-10-08 自查时有 37 个已修改或未跟踪文件。开始新工作前先检查并保护这批改动。

## 技术架构

- 前端：Next.js 16.3.3、React 19、TypeScript、Tailwind CSS。
- 后端：Python 3.12、FastAPI、SQLAlchemy、Alembic、LangGraph。
- 数据：PostgreSQL 保存用户、视频、转写、摘要和向量映射；本地目录保存视频、音频和笔记。
- 视频：yt-dlp 下载、字幕优先，缺字幕时抽取音频；默认 `ASR_PROVIDER=disabled`，因此无字幕转写尚未可用。
- AI：DeepSeek 默认用于分析和回答；当前 `local_hash` embedding + ChromaDB 只提供基础 RAG 流程。
- 认证：默认 demo user；Supabase 注册登录及后端 Auth 服务令牌验证代码正在接入。
- 本地编排：Docker Compose 默认启动 PostgreSQL、Adminer、backend、frontend；Chroma 使用后端嵌入式持久化，独立服务是可选 profile。

详见 [当前架构](docs/architecture.md)。

## 验证状态

**本轮验证（2026-10-08）：**隔离副本前端 typecheck、lint、生产构建通过；实际 Python 3.12 后端容器中 16 项测试通过，Alembic 位于 `20260904_0002 (head)`。最初前端超时是旧容器的 bind mount 为空；重新创建前后端无状态容器后，`/`、`/auth`、`/dashboard`、`/library`、`/chat` 与后端 readiness 均返回 200。另用临时 Supabase 配置构建，未登录访问 Dashboard、Library、Chat 均返回 307 到 `/auth`。真实 Supabase 登录仍未验证。本轮还修复了工作台/知识库的错误伪装、视频处理状态反馈与首页示意数据标记；前端 typecheck、lint、build 通过，模拟后端不可用时错误面板显示正常。`git diff --check` 无空白错误。

**此前记录（2026-09-04）：**前端 typecheck、lint、build 通过；后端 9 项测试通过；更早的全新 PostgreSQL Alembic 迁移和生产 Docker 镜像曾通过验证。这些是历史结果，需要在当前环境复验。

## 已知风险与缺口

- 开始本轮开发时有 37 个未提交文件；本轮继续增加认证和文档改动。当前 `.env` 未设置 Supabase 配置，`AUTH_MODE` 使用默认 demo。真实注册/登录及用户隔离未验收。
- 尚无有字幕真实 URL 的完整创建 → 转写 → 分析 → 向量写入 → 问答验收记录。
- 无字幕视频因默认 ASR 关闭而不能完成转写；本地 hash embedding 的中文语义质量有限。
- FastAPI BackgroundTasks 缺少持久化重试；本地文件和 Chroma 尚无生产存储方案。
- 视频下载受平台策略、Cookie、网络、yt-dlp 和 ffmpeg 环境影响。
- 前端容器挂载为空的问题已通过重新创建容器恢复；如果复发，先检查 Colima Docker socket、bind mount 和容器日志。
- `docs/api.md`、`docs/project-plan.md`、`docs/deployment-audit.md`、`docs/self-review.md` 包含历史阶段陈述，读取时需与当前架构和路线图核对。

## 下一步

1. 恢复前端和 Docker 环境；审查并测试 2026-09-04 的未提交改动。
2. 完成 Supabase 认证配置、迁移、双用户隔离验收并提交 Sprint 02。
3. 用真实有字幕视频完成全链路验收；再进入本地 ASR 和中文 embedding。
4. 确认作品集上线方案，逐步配置 Vercel、Render、Supabase、存储和队列。

具体里程碑见 [阶段路线图](docs/roadmap.md)，任务见 [TODO](TODO.md)。

## 2026-10-08 补充：双语与用户密钥

- 前端增加中文默认、英文切换、`/settings` 模型设置页；开发工具入口已隐藏。
- 后端增加 `ai_settings` 用户独立配置表，服务端 Fernet 加密密钥；DeepSeek/OpenAI 模型和可选 OpenAI 转写密钥按当前用户读取。Supabase 认证模式下不使用项目所有者的密钥作为回退。
- 本地 `.env` 已生成加密主密钥（本文不记录值），PostgreSQL 迁移到 `20261008_0004`。真实数据库中的设置保存、读取、删除已通过；本地演示账户的测试密钥已删除，且 demo 模式现已禁止保存个人密钥。真实 Supabase 登录与服务商扣费仍需外部配置及验收。

## 2026-10-08 补充：本地向量库

发现独立 Chroma 镜像未安装，原本地问答链路会在向量写入和检索时失败。现默认改为 Chroma PersistentClient，路径 `/app/storage/chroma` 映射到仓库 `storage/chroma/`；独立 HTTP 模式保留。容器内本地持久化写入/重开/检索烟测通过，`/api/v1/health/ready` 返回数据库与向量库均为 `ok`。这不等于真实视频和实际模型问答全链路已验收。

## 2026-10-08 补充：一键视频流程

视频详情现在可一键触发字幕、AI 分析、向量写入，且可在失败后复用已有的转写和笔记。请求按视频状态原子校验，拒绝并发重复启动。后端完整测试为 24 项通过，前端隔离副本的 typecheck、lint、build 通过。实际有字幕视频和真实模型调用仍未验收；后台任务在进程重启时不会自动恢复。

## 2026-10-09 补充：笔记操作与 API 级隔离验证

视频详情的 Markdown 笔记可复制或下载，处理入口可直接打开个人模型设置。新增模拟外部下载、模型和向量服务的 API 级测试，验证已认证用户从保存个人 Key 到一键入库、问答引用的闭环，以及另一用户无法读取视频或检索其内容；后端测试共 25 项通过。前端隔离副本 typecheck、lint、build 通过。真实 Supabase 项目、真实视频及服务商账单仍未验收。
