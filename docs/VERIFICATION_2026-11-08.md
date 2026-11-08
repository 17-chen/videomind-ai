# 2026-11-08 对象只读核查

## Git 与范围

起点 `main=9e7a8c4`，开始 fetch 后与 origin/main 一致，远端为 `git@github.com:17-chen/videomind-ai.git`。原有未跟踪 `outputs/` 与 `backend/:memory:.ses` 保留，不读取内容、不提交。本轮沿 R6/R8 补只读账本/远端观察，不修改已部署环境、主密钥、用户数据或迁移版本；不是旧文件迁移或未决上传解决器。

功能提交 `c98aad2` 已正常推送，[CI 42444875044](https://github.com/17-chen/videomind-ai/actions/runs/42444875044) 前后端均通过。随后最终复核补 PostgreSQL 聚合整数转换与 JSON 序列化断言，后端 343 项和 Ruff 再次通过。

## 实现

- `python -m scripts.audit_objects` 默认仅 SQL 聚合，未安装账本时不创建云客户端；远端需显式 `--verify-remote`。输出固定聚合字段，异常脱敏，无身份、精确键、bucket、摘要或凭证。
- 远端验证精确不可变键、项目指纹及私有桶，通过 GET 流式计算大小/SHA-256，无本地媒体缓存。403、429、5xx、跳转等不当作不存在；不跟随重定向。已 deleted 对象再出现单独提示。
- 默认 limit=20、max-mb=512；每次尝试先预留声明大小 + 一块溢出余量，失败也消耗本批预算。超限跳过、后续截断会提示关注，offset 只用于暂停写入后的人工分批，不声称全桶/跨批原子快照。
- PostgreSQL 初始汇总和选取使用只读可重复读，网络期间释放 SQL 事务/锁；新只读事务复查整条元数据、状态、意图及更新时间，并发变化不计作稳定匹配。
- 所有结果仅为观察。pending 匹配、404、视频缺失均不触发发布、释放额度或删除；账本未变也不能证明在途远端请求已停止。

## 检查证据

| 项目 | 本轮结果 |
| --- | --- |
| 后端全量 | 无特权用户 65534：**343 passed**，无跳过；启用 PostgreSQL 配额/pgvector/对象集成用例 |
| Ruff | `ruff check app tests scripts alembic_pgvector alembic_objects` 通过 |
| 真实 PostgreSQL | 一次性 tmpfs PostgreSQL：核查事务 `transaction_read_only=on`，远端模拟读取期间独立连接可修改对象意图（500 ms 锁超时下成功），结果标记变化、不释放 pending 预留；确认 SUM(bigint) 返回 Decimal 后显式转换整数，真实 PostgreSQL 报告 JSON 序列化断言及再次全量 343 项通过；既有迁移/并发/回滚回归通过 |
| 真实本地 HTTP | 多块正文读取、大小/摘要校验，无媒体缓存；服务端模拟 Supabase 协议，不是实际 Supabase |
| 新增边界 | 缺失/损坏/超长/编码不符/权限/跳转/公共桶/错误项目拒绝、无限正文一块溢出即止、失败占用预算、批次截断/offset、元数据损坏不访问远端、未提交改动拒绝、CLI 关闭客户端及输出脱敏通过 |
| 状态保护 | GET 匹配或 404 均保持 pending、来源标志和预留；SQL 监听未发现核查写语句；deleted 缺失为正常观察、再次读到内容需关注 |
| 前端 | 源码未改；无网络一次性容器中 4 项部署保护用例、build/typecheck/lint 通过，不覆盖开发 `.next` |
| 检索 | local_hash、虚构语料、top-k=3，Recall 0.9643、Hit/MRR 1.0、越权 0；不是 BGE/真实语料/最终回答验收 |
| 本机默认命令 | `python -m scripts.audit_objects` 退出 0，status=not_installed、remote.enabled=false、observations_only=true、writes_performed=false；当前对象表未安装，没有连接真实云 |

测试使用自建容器 `videomind-storage-test-20261108`，仅自身 tmpfs，不访问现有数据卷；结束后移除，前端临时容器自动移除。既有 LangChain 弃用提示与 ONNX/Chroma 遥测告警仍在，命令退出 0；本轮不宣称修复这些依赖提示。

## 剩余与边界

真实 Supabase Storage/认证、双用户隔离、本人 ASR/LLM 闭环、跨实例持久性及备份恢复均未验收。默认仍为 local/Chroma，本轮未重启服务、未执行对象迁移或任何删除，也未切换环境。

下一步继续有凭据地解决 pending、旧文件迁移/数量摘要核对/回退、用户整体删除和物理容量/并发缓存方案。观察工具不证明 bucket 中没有账本外对象，不提供删除授权；本批正常也不代表全库、所有批次或完整服务通过验收。协议、字段与退出码详见 [对象说明](OBJECT_STORAGE.md)。
