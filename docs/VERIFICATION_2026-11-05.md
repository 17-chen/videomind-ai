# 2026-11-05 核查：视频删除与对象清理意图

## 本轮范围

- 读取 AGENTS、交接、上下文、TODO、完成计划及相关源码；起点 `b63aaf7`，fetch 后 main 与 origin/main 一致。
- 未读取、修改或提交原有未跟踪 `outputs/`、`backend/:memory:.ses`；未改 `.env`、主密钥、用户配置和既有数据卷。
- R6/R8 接通视频删除：在同一数据库事务记录对象的 delete_requested 意图并删除业务记录；向量或 SQL 失败回滚。未安装可选账本时保留本地行为；旧账本未升级时，在向量操作前安全拒绝。
- 新增独立 `20261105_o002` 可选迁移（业务 head 仍为 `20261024_0008`），默认 false 列保留旧记录。存在未完成删除意图时拒绝降级丢列；现有业务库未应用此迁移。
- 新增默认只读 `python -m scripts.cleanup_objects`；只有 `--apply` 处理已标记、retired 且视频不存在的精确键，每批最多 1–100 次，确认 404 后才记 deleted。pending 不确定上传、无标记旧对象及现有视频都不自动删除。
- 上传登记 pending 前再次锁视频并核对归属；上传网络期间释放视频锁。完成后拒绝恢复已标记对象，防止删除后补登记或复活。

## 验证证据

- **后端：267 passed，0 skipped，Ruff 全通过**（app/tests/scripts/alembic_pgvector/alembic_objects）；UID 65534，显式启用 PostgreSQL 配额、pgvector 和对象库用例。原 LangGraph 弃用提示保留。
- **真实 SQL：**本轮新建 tmpfs 容器 `videomind-storage-test-20261105`，不挂载业务卷，各用例创建随机一次性库。新迁移从空库及带旧对象的 001 升级通过；业务 head 不变，原 RLS/客户端权限检查通过。拒绝丢失未完成意图的降级已验证；最终补表锁保护后，12 项 PostgreSQL 专项及全量 Ruff 复验通过，避免检查和删列之间的新意图竞争。
- **真实并发：**两个连接上传/删除竞争，在网络等待中视频可以删除，pending 意图保留，完成后的发布返回 404。测量后、登记前删除视频时，不创建对象/账本。两个维护连接通过 SKIP LOCKED，同一对象只执行一次删除。
- **真实 SQL 故障：**PostgreSQL trigger 在业务 DELETE 时失败，视频、ready 和意图全部回滚（向量仍可能已删，原跨存储边界保留）；在远端删除后的账本 UPDATE 时失败，意图保持 retired，下一次显式操作重试成功。新 Session 可读取删除后持久意图。
- **API/隔离：**FastAPI TestClient + 模拟 Supabase 身份验证越权 404、向量失败回滚、204 后意图持久；既有本地删除回归通过。身份、向量、远端对象都为虚构/替身，TestClient 不等于云端登录验收。
- **传输/恢复：**HTTP MockTransport 组合真实适配器，DELETE 200 但读取仍为 200 时保持 retired；直到确认 404 才记 deleted。模拟响应丢失和 SQL 提交失败可重试，当前对象、无意图对象、pending 与现有视频不会被推断为可清理。
- **维护命令：**默认预览用 SQL 事件断言无写入、不创建远端客户端；仅有 pending 时即使 --apply 也不创建客户端。批量上限、失败脱敏、关闭客户端和只输出聚合通过。本机业务库默认预检实际为 not_installed、attempted=0、writes_performed=false，未执行 --apply。
- **前端：**Next.js 16.4.3，一次性禁网容器源码副本、依赖卷只读挂载，4 项保护用例、build/typecheck/lint 通过；未覆盖开发 `.next` 或改变依赖卷。
- **检索：**实际隔离 Chroma/local_hash、15 道固定虚构语料题，Recall@3 96.43%、Hit@3 100%、MRR@3 1.0、隔离违规 0。不代表真实模型或生成回答质量；既有 Chroma telemetry/ONNX 主机提示保留，命令成功退出。
- **运行核对：**当前业务 revision 仍为 `20261024_0008`、对象账本不存在、向量为 chroma；readiness HTTP 200、database/vector_store 均 ok。未迁移现有库或切换运行存储。
- **阶段上限回归：**降低本地临时文件上限后，下载大对象仍拒绝 413，删除旧大对象不再被本地阶段上限阻挡（删除无媒体缓存分配）。

本轮 tmpfs PostgreSQL 容器已停止并删除，前端一次性检查容器自动退出删除；既有业务容器、数据卷和镜像均保留。GitHub CI 结果待推送后补记。

## 未验收与下一步

- 此轮接入的是视频删除意图及已确认对象的维护清理，上传、Worker、编辑读取仍用本地目录，完整 R6 适配未完成；当前 API/Worker 仍不能部署到两块独立 Render 磁盘。
- 没有运行真实 Supabase Storage、登录/JWT、角色权限、费用、云端恢复或本人模型全链路；本机真实 SQL 与模拟服务证据不能替代目标环境验收。
- pending 结果不明对象保留待核对，不能因年龄/404/视频缺失自动清理。用户整体删除、旧对象迁移、在途读取、物理容量/预留和告警仍待补；API 204 不等于所有云端副本物理删除。

操作与边界见 [对象存储说明](OBJECT_STORAGE.md)、[剩余计划](COMPLETION_PLAN.md) 和 [部署时机](DEPLOYMENT_READINESS.md)。
