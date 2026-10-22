# 项目上下文

> 最后核对：2026-10-22。优先以仓库代码、Git 状态和本次实测为准；不记录真实密钥。完整文档索引见 [项目资料入口](docs/PROJECT_MATERIALS.md)。

## 项目基本信息

- **名称：**VideoMind AI。
- **目标：**把收藏但没时间看的视频转成结构化笔记、可检索知识库和可追溯来源的问答。
- **实际代码仓库：**`/Users/chenxin/Documents/Codex 2/videomind-ai`，Git remote `git@github.com:17-chen/videomind-ai.git`。
- **目标用户：**学习者、内容创作者和管理视频资料的知识工作者。

## 当前阶段

Phase 1–6 已有基础实现。Phase 7 的迁移、健康检查和生产构建基础此前通过验证，但真实视频端到端流程未验收。当前处于 Sprint 02 的 Supabase 用户系统接入：认证、用户映射、登录页、Auth 服务校验、邮箱冲突保护和会话刷新等代码已随 `8f8047d` 提交；真实 Supabase 项目仍未连接。项目现阶段是本地演示，不是正式多用户 SaaS。

**Git 快照：**2026-10-22 本轮开工时 `main` 与 GitHub 一致，最近提交为 `b485f92`；此后本地 AI 依赖与模型验收继续推进，完成时以实际 Git 状态为准。

**交接补充：**检索评测已随 `064b1b7` 推送；随后将 `PROJECT_HANDOFF.md` 重整为完整当前快照，`docs/COMPLETION_PLAN.md` 补充 R1–R9 的验收与依赖。新聊天先从仓库 `AGENTS.md` 和 [恢复说明](docs/NEW_CHAT_START.md) 进入，不依赖旧聊天自动继承。

## 技术架构

- 前端：Next.js 16.3.3、React 19、TypeScript、Tailwind CSS。
- 后端：Python 3.12、FastAPI、SQLAlchemy、Alembic、LangGraph。
- 数据：PostgreSQL 保存用户、视频、转写、摘要和向量映射；本地目录保存视频、音频和笔记。
- 视频：yt-dlp 下载、字幕优先，缺字幕时抽取音频；默认 `ASR_PROVIDER=disabled`，可选安装本地 faster-whisper 或使用用户的 OpenAI 转写 Key。
- AI：DeepSeek 默认用于分析和回答；默认 `local_hash` embedding + ChromaDB 提供基础 RAG 流程，可选本地中文 BGE 模型与分段索引。
- 认证：默认 demo user；Supabase 注册登录及后端 Auth 服务令牌验证代码正在接入。
- 本地编排：Docker Compose 默认启动 PostgreSQL、Adminer、backend、frontend；Chroma 使用后端嵌入式持久化，独立服务是可选 profile。

详见 [当前架构](docs/architecture.md)。

## 验证状态

**2026-10-22 补充：**在独立验证镜像中安装可选本地 AI 依赖，修复 PyAV 19 与 faster-whisper、较新 tokenizers 与 ChromaDB 的真实兼容冲突，`pip check` 通过。真实 faster-whisper base 用 CPU int8 转写 8.24 秒合成中文语音，有可见错字；真实 BGE 在固定虚构语料上 Recall@3 100%、跨用户违规 0。模型缓存位于已忽略的 `storage/model-cache/`；默认 API/Worker 未切换到本地 AI。自然语音、真实视频、Supabase 与付费模型仍未验收。见 [核查记录](docs/VERIFICATION_2026-10-22.md)。

**2026-10-21 补充：**R5 本地持久任务基础已实现：PostgreSQL 入队、独立 Worker、租约恢复、按阶段取消和本人任务接口。后续加固了旧 Worker 失去所有权后的阶段与终态写入。后端 75 项测试/Ruff、前端临时副本 build/typecheck/lint 通过；本机迁移至 `20261021_0007`，API 重启后任务保留、真实 Worker 完成合成资料入库、PostgreSQL 双 Worker 竞争、取消恢复与清理通过。另以受控阻塞阶段运行实际执行进程 96 秒，验证租约心跳后 SIGKILL，任务重新领取完成。真实媒体、付费服务、Supabase 用户和多实例长期运行仍未验收，R5 整项未完成。见 [核查记录](docs/VERIFICATION_2026-10-21.md)。

**2026-10-20 补充：**R4 本人资料与手工笔记编辑已实现；分类参与列表和索引，已入库视频编辑自动尝试同步，失败保留旧向量并标记可重试。后端 69 项测试、Ruff、前端隔离构建/typecheck/lint 通过；本地迁移至 `20261020_0006`，实际运行 API 的创建、编辑、分类筛选和清理通过。真实模型、Supabase 双用户和多实例一致性未验收。详见 [核查记录](docs/VERIFICATION_2026-10-20.md)。


**2026-10-19 补充：**R3 本地视频上传入口、文件验证、按用户重复保护和处理路径已实现。自生成短视频经运行中 API 上传、重复拒绝、详情和删除清理通过；模拟转写、笔记、入库工作流通过，66 项后端测试/Ruff 和前端 build/typecheck/lint 通过。本机 PostgreSQL 迁移至 `20261019_0005` 前已在不入 Git 的 `storage/backups/` 保存备份。真实 ASR、用户模型与 Supabase 双用户验收仍缺；详情见 [核查记录](docs/VERIFICATION_2026-10-19.md)。

**2026-10-18 补充：**先快进合入 GitHub 的 `700ccde` 字幕选择修复，随后添加推送与 PR 自动检查，覆盖后端测试/Ruff/固定 hash 检索和前端构建/typecheck/lint。本地后端 63 项通过，Ruff 通过，虚构语料 Recall@3 为 96.43%、隔离违规 0；前端临时副本的 build/typecheck/lint 通过。远端首次运行暴露 PostgreSQL 服务缺失；修复后的 [GitHub CI](https://github.com/17-chen/videomind-ai/actions/runs/39103657908) 两个任务均通过，详见 [本轮核查](docs/VERIFICATION_2026-10-18.md)。R1 真实本地模型依赖尚未安装，真实音频、BGE、外部服务仍未验收。

**当前验证（2026-10-16）：**后端 62 项测试和 Ruff 通过；12 条虚构文本、15 道问题的真实 hash + 内存 Chroma 评测完成，Recall@3 为 96.43%，隔离违规为 0。漏检与小样本边界见 [检索评测](docs/RETRIEVAL_EVALUATION.md)。本轮未改前端，最近一次前端构建与页面检查为 2026-10-15，详见 [上轮核查](docs/VERIFICATION_2026-10-15.md)。

**历史验证（2026-10-08）：**隔离副本前端 typecheck、lint、生产构建通过；实际 Python 3.12 后端容器中 16 项测试通过，Alembic 位于 `20260904_0002 (head)`。最初前端超时是旧容器的 bind mount 为空；重新创建前后端无状态容器后，主要页面和 readiness 返回 200。临时 Supabase 配置下未登录访问受保护页面会跳转到 `/auth`；真实登录未验证。

**此前记录（2026-09-04）：**前端 typecheck、lint、build 通过；后端 9 项测试通过；更早的全新 PostgreSQL Alembic 迁移和生产 Docker 镜像曾通过验证。这些是历史结果，需要在当前环境复验。

## 已知风险与缺口

- 当前 `.env` 未设置 Supabase 配置，`AUTH_MODE` 使用默认 demo。真实注册/登录及用户隔离未验收。
- 尚无有字幕真实 URL 的完整创建 → 转写 → 分析 → 向量写入 → 问答验收记录。
- 无字幕视频在默认 ASR 关闭时需要用户转写 Key；可选本地模型仅在合成音频上完成真实推理，自然语音与视频链路待验。默认 hash embedding 的中文语义质量有限；BGE 已跑虚构语料，真实内容质量待评测。
- 视频处理已有本地 PostgreSQL 持久任务和独立 Worker，受控长任务进程中断/心跳已验；真实媒体、付费调用与多实例长期运行未验，本地文件和 Chroma 尚无生产存储方案。
- 视频下载受平台策略、Cookie、网络、yt-dlp 和 ffmpeg 环境影响。
- 前端容器挂载为空的问题已通过重新创建容器恢复；如果复发，先检查 Colima Docker socket、bind mount 和容器日志。
- `docs/api.md`、`docs/project-plan.md`、`docs/deployment-audit.md`、`docs/self-review.md` 包含历史阶段陈述，读取时需与当前架构和路线图核对。

## 下一步

1. 完成 R5 真实媒体处理故障边界和多实例长期运行演练；付费步骤只在本人服务商可用后验收。
2. 扩充真实且允许使用的视频转写、人工标签和回答引用样例，对比已完成的 hash/BGE 虚构语料基线。
3. 配置真实 Supabase 测试项目后，完成注册、登录、会话刷新和双用户隔离验收；此前继续完成不依赖账号的实现。
4. 确认作品集上线方案，逐步配置 Vercel、Render、Supabase 和存储。

具体里程碑见 [阶段路线图](docs/roadmap.md)，任务见 [TODO](TODO.md)。

剩余范围与初步工时见 [完成计划](docs/COMPLETION_PLAN.md)：按现有范围的小规模多用户版本约 50–80 小时有效开发，不计等待账号注册和授权时间；本地功能收束约 16–26 小时。该估算随真实联调结果更新。

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

## 2026-10-09 补充：视频删除

用户可从详情页删除自己的非处理中视频；后端先删除对应用户的 Chroma 文档，再删除 PostgreSQL 视频及关联内容，最后按生成的 ID 清理本地媒体、转写和笔记文件。向量删除失败会保留数据库记录以便重试；数据库提交失败可能留下暂时缺失的向量，后续可重新入库。后端 27 项测试与前端 typecheck、lint、build 通过。真实多实例和外部向量服务故障恢复仍待验收。

## 2026-10-11 补充：运行核查与修复

发现本机另一项目占用 `127.0.0.1:8000`，最初对该端口的健康和路由检查误指向别的应用。VideoMind 本地 `.env` 已调整为宿主机 8001（不提交），容器内部仍为 8000；重建后已核对 OpenAPI 视频路由和带 `service=VideoMind AI` 标识的就绪状态。真实本地视频创建/读取/删除、demo 设置限制、空知识库问答及七个前端页面通过冒烟；Alembic 为 `20261008_0004 (head)`。无字幕处理在提取音频前检查转写 Key；后端 29 项测试和全量 Ruff、前端 typecheck/lint/build 通过。真实 Supabase、视频下载和付费模型仍待验收，详见 [核查记录](docs/VERIFICATION_2026-10-11.md)。

## 2026-10-12 补充：不依赖外部验收的开发

加入可选本地 faster-whisper、中文 BGE 向量模型、长文档分段与按视频去重、跨旧新集合删除、显式重新入库脚本，以及本地单进程启动时解除中断任务状态。默认演示配置不自动安装大型模型。后端 38 项测试和 Ruff、前端 typecheck/lint/build 通过；Docker Compose 配置校验通过。真实模型下载、真实转写/语义质量、生产多实例队列和外部服务商仍未验收。启用方法见 [本地 AI 配置](docs/LOCAL_AI.md)。

## 2026-10-13 补充：索引安全更新与设置页检查

BGE 索引更新改为先写入新版本再清理旧分段；故障时保留旧版，搜索时扩展被同一视频占满的候选范围。设置接口新增非敏感 `asr_provider` 字段，前端按实际转写模式显示中英文说明。后端 41 项测试与 Ruff、前端 typecheck/lint/build 通过。开发容器需要重启才加载本轮最新代码；重启后在线设置响应、readiness 和设置页正常。仍未验收的外部依赖见 [本轮核查](docs/VERIFICATION_2026-10-13.md)。

## 2026-10-14 至 15 日更新

向量重建工具已支持只读预检查、用户筛选、扫描数量限制和单条失败后继续。知识库新增每页 20 条的分页，翻页保留筛选；搜索覆盖原始标题、描述、链接及 AI 标题与摘要，百分号和下划线按普通字符处理。分类接口按当前用户汇总整个视频库，视频排序增加 ID 以保证相同创建时间的分页顺序稳定。
