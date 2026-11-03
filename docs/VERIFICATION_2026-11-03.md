# 2026-11-03 核查：可选共享 pgvector

## 起点与改动

- 按 AGENTS 读取交接、上下文、剩余计划与 TODO；起点 `feffb00`，拉取远端后本地与 `origin/main` 一致。
- 原有未跟踪 `outputs/`、`backend/:memory:.ses` 保留，未读取正文、修改或提交。
- R6 新增可选 `VECTOR_STORE_BACKEND=pgvector`，默认仍为 Chroma；复用结果结构与分段逻辑，使用已有 SQLAlchemy/psycopg，无新 Python 依赖。
- 新增独立显式 Alembic 环境与版本表，只有 `prepare_pgvector --apply` 才执行；普通业务迁移不要求安装 vector 扩展。本机没有执行新迁移或切换后端，没有修改 `.env`、主密钥、业务数据或既有数据卷。

## 实际检查

- **后端最终全量：204 passed，Ruff 通过。**UID 65534，显式启用两个 PostgreSQL 配额并发用例和 16 个 pgvector 数据库用例；无跳过。新增文件/迁移目录也执行 Ruff。原 LangGraph 弃用提示仍保留。
- **真实 pgvector：**官方 `pgvector/pgvector:0.8.7-pg16`，本机 Colima 独立命名容器 `videomind-pgvector-test-20261103`，数据目录为新建 tmpfs，不挂载现有卷；每个用例再创建随机命名的一次性数据库，检查后删除该库及其模拟角色。
- **迁移与 schema：**从空库运行所有既有业务迁移，再运行可选向量迁移；扩展位于 public 与 extensions 两种场景都通过。业务 head 保持 `20261024_0008`，独立版本为 `20261103_v001`；第二次应用不丢向量。
- **跨进程与过滤：**两个 PgVectorStore 实例及独立 Python 进程通过实际 factory 读取同一批数据库向量；Alice/Bob 只返回各自资料，越权 upsert 404，错误 user_id 删除无效果。
- **权限：**在一次性数据库模拟给 anon/authenticated/service_role 自动授予新表权限，再确认迁移已撤销三者的表 SELECT 权限、向量表 RLS 已启用。这不是实际 Supabase 角色/JWT policy 验收，测试使用可信数据库所有者。
- **原子更新/并发：**真实 SQL 约束让新分段在删除旧分段后插入失败，事务回滚且旧索引可检索；两个连接同步竞争同视频，最终没有混合版本；长文缩短后仅保留当前分段。
- **契约：**BGE 分段模式使用模拟非零向量，模型指纹切换隔离、SQL 视频级去重和跨模型删除通过；实际 `rag.index_video`、资料编辑同步、`delete_video_for_user` 及数据库 FK 清理通过。删除检查使用业务 Session 的真实视频锁，未出现双连接互锁。
- 初次专项测试中 8 维模拟 hash 恰好抵消为零，触发生产拒绝零向量的约束；测试改为明确的非零模拟输出，未放宽生产校验。固定语料另用实际 LocalHash 384 维，不使用该替身。
- **固定虚构语料：**12 条资料、15 道问题，在 pgvector 两种 schema 中均为 Recall@3 **96.43%**、Hit@3 100%、MRR@3 1.0、隐私违规 0；原 `python -m scripts.evaluate_retrieval` 的内存 Chroma/hash 也为同一结果。既有失败题仍保留，不修改标签；报告是检索阶段，无生成回答。
- **安全失败：**无效/NaN/Inf/零写入向量不访问数据库；零查询返回空检索。缺向量表 readiness 报 503，SQL 错误仅记录异常类型；准备命令默认不打开数据库，迁移异常不回显原始错误。前端新增两条中英文失败提示。
- **前端：**临时源码副本的 build/typecheck/lint 及 4 项部署保护用例通过；Next.js 16.4.3，未覆盖开发 `.next`。依赖软链接导致 standalone tracing 的 27 个文件在临时根外提示仍存在，临时产物不作为部署镜像。
- **运行核对：**当前后端配置仍为 chroma、readiness HTTP 200、业务 Alembic 仍为 `20261024_0008`。未将现有 API/Worker 切到 pgvector。

功能提交 `f3ba87e` 已同步 GitHub，[CI 41614700666](https://github.com/17-chen/videomind-ai/actions/runs/41614700666) 后端与前端均通过。远端包含新 pgvector 实测、后端/Ruff、隔离 hash 检索及前端部署保护/build/typecheck/lint；不代表真实云服务验收。本轮 tmpfs 测试容器已停止并删除，现有业务容器与数据卷保留。

## 未验收边界与下一步

- 真实服务仅指本机隔离 PostgreSQL/pgvector；所有用户、文本、URL、平台角色为虚构，BGE 分段模型为替身。真实 Supabase 认证/角色权限、云端迁移/TLS/备份恢复、真实模型质量和生成回答仍未验收。
- pgvector 是可选共享向量子项，不代表 R6 完成：媒体、音频、转写与笔记仍需对象存储适配，当前 API/Worker 仍不能拆到两个独立 Render 磁盘。
- 业务映射和向量替换分开提交，未提供跨后端双写、自动复制旧 Chroma 或自动清理旧副本；切换/回退须按数据库重建并核对。没有近似索引、大库性能或多实例长期负载验收。
- R5/R8 下载合并监督、并发空间预留、可恢复孤立文件清理和生产统一流量边界仍保留。

启用/回退步骤见 [pgvector 说明](PGVECTOR.md)，部署时机见 [部署说明](DEPLOYMENT_READINESS.md)。
