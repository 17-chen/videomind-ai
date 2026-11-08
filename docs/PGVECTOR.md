# 可选共享 pgvector 向量后端

2026-11-08：独立 Supabase PostgreSQL 17 已安装本项目 pgvector 迁移，当前连接/结构就绪检查通过，并收紧后端专用表权限。未进行真实 BGE 云端向量写入/检索闭环；原有本地 Chroma 未切换。见 [真实基础接入记录](VERIFICATION_2026-11-08_SUPABASE.md)。

2026-11-03：R6 子项。`VECTOR_STORE_BACKEND=chroma` 仍为默认；`pgvector` 使用同一个 `DATABASE_URL` 保存向量，供 API 和 Worker 共享。没有自动切换现有环境，也没有复制或删除现有 Chroma 文件。未知后端值会拒绝启动，不静默回退。

## 适配语义

- 复用现有结果结构和分段边界；hash 保存整篇，`bge_zh` 按现有 350/60 分段。
- pgvector 模式忽略 Chroma 的模式/路径/集合设置，使用同一业务库中的后端专用表。每次检索在 SQL 中按 `user_id`、模型指纹与实际维度过滤；余弦距离排序，在 SQL 按视频选最佳分段后限量返回。同一长视频不会挤满有界候选池。查询上限 1–100。
- 目前是精确扫描，索引只优化用户/模型过滤；没有 HNSW/IVFFlat 近似索引，也没有规模化性能结论。检索范围和能力依据 [pgvector 官方文档](https://github.com/pgvector/pgvector)。
- 嵌入值在事务前生成并检查；无效、非有限、空或零向量不写入。全零查询返回空结果，不调用回答模型。模型之间按 provider、BGE 模型 SHA-256 和维度隔离，切换需要重建。
- 对同视频更新先核对归属并锁定视频行，再在同一个向量事务中删除旧分段、插入全量新分段。插入失败则回滚，旧版保留；两个更新不会混合分段。模型计算在拿锁之前完成，锁不覆盖模型加载时间。
- 删除以 `user_id + video_id` 删除该后端中全部模型的分段。删除服务已经在自己的 SQLAlchemy Session 锁定视频，向量删除不会在另一个连接重复锁视频，避免互锁。数据库删除视频/用户也通过 FK 清除所属向量。
- 向量事务与业务 `Embedding` 映射仍分开提交，保留原 Chroma 调用契约；业务映射更新失败仍需重试。没有声称整个 PostgreSQL 业务和向量是一个统一事务，也没有解决所有并发编辑先后顺序问题。

## 独立迁移与访问边界

可选迁移目录 `backend/alembic_pgvector/`，版本表 `alembic_version_pgvector`，初始版本 `20261103_v001`。业务 `alembic_version` 仍为 `20261024_0008`；普通 `scripts.migrate` 不会安装扩展或创建向量表。因此未启用 pgvector 的现有普通 PostgreSQL/Chroma 环境不受影响。

显式迁移创建/复用 `vector` 扩展和 `public.vm_vector_chunks`，记录版本；重复应用不修改向量数据。支持扩展位于 `public` 或 `extensions`，运行时从 PostgreSQL 元数据取得并正确引用 schema，不依赖某台服务的 search_path。未知同名表与未记录版本不会被自动覆盖。可选迁移回退仅删除自己的向量表，不删除可能供其他应用使用的扩展；回退前须备份并准备重建索引。

向量表启用 RLS，撤销 PUBLIC 以及存在时的 `anon`、`authenticated`、`service_role` 表权限，以消除托管平台默认授予 public schema 表访问的影响。**没有提供面向浏览器 JWT 的逐用户 RLS policy。** 正常路径是可信后端数据库角色访问，应用始终传入已认证用户的 `user_id`；不能把直连数据库凭证放到前端。运行角色必须是该表所有者或经过审查的专用后端角色并具有必要权限/RLS 策略，不能假定普通 GRANT 自动绕过 RLS。当前隔离测试使用数据库所有者与模拟平台角色；这不替代真实 Supabase 角色验收。

## 计划启用步骤

以下步骤会改变目标环境，仅在已备份且已授权的目标上操作。本轮没有执行现有业务库的切换或迁移。

1. 备份目标数据库、业务文件、Chroma 和当前主密钥；参考 [恢复手册](RECOVERY_RUNBOOK.md)。先在隔离环境恢复验证。
2. 确认目标 PostgreSQL 安装 pgvector，目标数据库中的可信迁移角色可创建扩展/表；业务表须位于 public。平台预装扩展位于 extensions 时无需移动扩展。
3. 在目标后端环境先运行现有 `python -m scripts.migrate`，将业务结构迁移至当前 head。
4. 显式运行 `python -m scripts.prepare_pgvector --apply`。成功输出 applied；失败只给固定错误，不回显连接串。**不带 `--apply` 不打开数据库、不写任何内容，退出 2 并输出 not_applied。** 该状态不是一次已执行的结构 dry-run。
5. API、Worker 配置相同 `DATABASE_URL`、`VECTOR_STORE_BACKEND=pgvector` 和 embedding 配置，空队列后安全重启；不用切换/重新生成主密钥。应用不会自行建向量表，缺表或扩展时 readiness 返回不可用。
6. 使用现有 `python -m scripts.reindex_vectors --dry-run` 核对视频范围，再在已授权目标运行去掉 dry-run 的重建。向量由数据库中的转写/摘要/手工笔记重建，不是直接复制 Chroma 内部文件；可按 `--user-id`、`--limit` 控制范围。首次查询新后端没有旧 Chroma 的资料，必须先重建再验收。
7. 核对两用户过滤、资料和分段数量、编辑、检索、删除、重启及引用质量后才对用户开放。

## 回退和未完成项

- 回到 `VECTOR_STORE_BACKEND=chroma` 不会自动恢复切换后的新更新：旧 Chroma 在 pgvector 运行期间没有双写。回退前按当前数据库内容重建目标 Chroma，再验证数据；旧文件仅保留作为恢复参考，不保证永远最新。
- 从当前后端删除视频不会自动连接另一个已停用后端清理旧副本；业务数据库删除的 pgvector FK 能清理同库向量，但旧 Chroma 文件仍按备份/保留策略处理。切换后旧副本的隐私清理不能遗漏。
- 本轮只解决共享向量，媒体/音频/转写/笔记仍是本地文件。API 和 Worker 仍不能直接部署成两个独立 Render 磁盘，必须继续对象存储适配。见 [部署时机](DEPLOYMENT_READINESS.md)。
- 真实 Supabase 凭证、迁移权限、连接池/TLS、云端备份/恢复、跨实例长期负载和自然语音/真实 BGE/回答引用质量尚未验收。

验证见 [2026-11-03 核查](VERIFICATION_2026-11-03.md)。测试的 PostgreSQL 和 pgvector 是真实服务；用户、平台角色和文本为虚构，分段测试的向量模型为替身；固定语料指标不能代替真实服务质量。
