# 2026-10-20 R4 核查记录

## 范围与结果

- 开工时 `main` 工作树干净，与 `origin/main` 一致，基线 `f33baf7`。
- R4 新增本人元信息、分类和 Markdown 笔记编辑。手工笔记在再次 AI 分析时保留；用户分类覆盖 AI 分类。编辑已入库内容后自动更新向量，失败保留旧索引并提示重试。
- 最终后端 `python -m pytest -q`：69 passed；`ruff check app tests scripts`：通过。前端临时副本 `npm run build`、`npm run typecheck`、`npm run lint`：通过。
- 本机 PostgreSQL 迁移前备份到 Git 忽略的 `storage/backups/videomind-before-20261020-0006.sql`（仅当前用户读写），随后从 `20261019_0005` 升至 `20261020_0006`。未重置数据卷。
- 后端重启后 `/api/v1/health/ready` 返回 `200`、数据库和向量库均 `ok`。运行中 API 创建、编辑、分类筛选、删除临时资料成功。
- 另用临时合成资料调用实际 API 写入 Chroma，再编辑资料；实际 Chroma 文档和分类更新，且临时资料与向量已删除。

## 验收边界

- 权限隔离、处理中冲突、手工笔记保留、向量故障时保留旧索引及重试由测试覆盖；其中双用户身份和向量故障是模拟环境。真实 Supabase 双用户仍未验收。
- Chroma 集成烟测使用合成文本、当前本地 hash embedding；不证明真实视频 ASR、BGE 中文语义质量、模型生成答案或服务商计费正确。
- PostgreSQL 与 Chroma 之间没有原子事务。重索引失败时数据库显示新内容，旧向量仍可能被问答命中；`index_sync_error` 和重试入口用于暴露、修复该状态。多实例并发编辑仍须后续可靠任务设计处理。
