# 2026-11-04 核查：对象传输与版本账本基础

## Git 与环境

- 按 AGENTS 读取交接、上下文、完成计划和 TODO；当前源码优先于历史记录。起点 `6040e6d`，本地与 origin/main 一致，保留并行合入的 WebVTT 元数据修复。
- 保留未跟踪 `outputs/`、`backend/:memory:.ses`，不读取内容、不修改、不提交；没有改 `.env`、主密钥、真实用户配置或现有数据卷。
- 新模型不在业务 metadata 中；本机运行库未应用账本迁移，业务仍用本地文件和 Chroma。没有创建云服务或切换现有 API/Worker。

## 已实现及验证

- 新增私有 Supabase Storage REST 传输层、不可变对象地址、SHA-256/大小校验、限量分块、失败保留旧目标和显式删除确认；后端独立存储凭证不进入浏览器，现代 secret Key 不当作 JWT Bearer。增加两条失败提示的中英文文案及无凭证模板。
- 文件账本先提交 pending 上传意图，后用真实用户/视频锁切换当前版本；上传结果不明或 SQL 提交失败时保留旧版和待对账键。检查用户归属、逻辑配额净增长和禁止直接清理当前版本。
- 独立可选迁移 `20261104_o001`，开启 RLS、撤销客户端表权限；默认准备命令不连接数据库，错误不回显原文。CI 显式启用新 PostgreSQL 检查。
- **后端：244 passed，0 skipped，Ruff 通过**；UID 65534，开启现有 PostgreSQL 配额、pgvector 和新账本数据库检查。包括 35 个对象/账本隔离用例及 4 个真实 SQL 用例。原有 LangGraph 弃用提示保留。
- **真实本地 HTTP/文件：**ThreadingHTTPServer 模拟 Supabase 私有桶和对象协议，使用虚构服务端 Key；实际 HTTP 完成上传/拒绝覆盖、校验下载、删除并确认 404。不是云端 Supabase 验收。
- **故障与隔离：**MockTransport 验证公开桶/错误桶、公开 Key、项目不匹配、跨域重定向、网络失败、错误长度/编码/摘要、符号链接；失败不覆盖旧文件且清理临时输出。SQLite 验证双用户、私有缓存清理、失败后的 pending、净替换额度、退休/删除与视频删除后禁止读取。
- **真实 PostgreSQL：**新建 `videomind-object-test-20261104` tmpfs 容器，无现有卷挂载；各用例用随机一次性数据库，业务迁移从空库执行，再运行对象迁移及重复执行，业务 head 仍为 `20261024_0008`。模拟 hosted default grants 后，anon/authenticated/service_role 的表增删改查权限均已撤销。两个真实连接并发：不同文件共用额度时结果为 200/413，保留 ready/pending；同文件竞争为 200/200，最终一个 ready、一个 retired。真实 SQL 约束失败回滚两次状态更新，旧版保持 ready。
- **隔离检索回归：**15 道固定虚构语料题，实际 Chroma/local_hash，Recall@3 96.43%、Hit@3 100%、MRR@3 1.0、隔离违规 0。既有 Chroma telemetry/ONNX 主机提示不影响退出结果；不代表真实中文语义质量或生成回答。

- **前端：**一次性禁网容器中的源码副本，依赖卷只读挂载，4 项部署保护用例、Next.js 16.4.3 build/typecheck/lint 全通过；没有覆盖开发 `.next`，没有修改现有依赖卷。

- **运行核对/清理：**本机 readiness 为 HTTP 200，database/vector_store 均 ok；只读核对业务 revision 为 `20261024_0008`、对象账本不存在、向量仍为 chroma。仅本轮 tmpfs 测试数据库容器在完成测试后停止删除，前端检查容器自动退出删除，所有既有卷与业务容器保留。最终扩大 SQL 异常脱敏范围后，39 项对象专项及 Ruff 复验通过。

同步前最近三次 GitHub CI 均为 success，包含基线 `6040e6d` 的 [41828806883](https://github.com/17-chen/videomind-ai/actions/runs/41828806883)。本轮功能提交 `b04ac37` 已同步 GitHub，[CI 41835276579](https://github.com/17-chen/videomind-ai/actions/runs/41835276579) 后端与前端均通过，覆盖真实 SQL 并发/账本、Ruff、隔离 hash 检索与前端全部检查。后续仅补验证记录。

## 未验收与下一步

- 本轮完成 R6 传输和账本基础子项；**尚未接入上传、Worker、编辑/读取和视频删除入口，完整对象存储适配未完成。** 配置不自动切换业务。
- ready 逻辑配额不等于云端账单；pending/retired、现有本地文件、并发预留尚未整合。没有自动回收或旧文件迁移，视频删除保留账本不等于已实现远端删除流程。
- 真实 Supabase bucket、角色/JWT、云端持久性/恢复、本人模型完整闭环、真实双账号及生产多实例验收仍需资源。现有两个独立 Render 磁盘不能共用文件；可准备受保护预发布，公开使用条件仍未满足。

详见 [对象基础说明](OBJECT_STORAGE.md)、[剩余计划](COMPLETION_PLAN.md) 与 [部署时机](DEPLOYMENT_READINESS.md)。
