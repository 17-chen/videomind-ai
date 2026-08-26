# 技术决策日志

只记录影响长期维护的决策；保留被替代的历史记录。

## 2026-08-01 — 部署前先执行审计

- 状态：已接受
- 背景：项目已经完成基础前后端和 UI，但尚未正式部署。
- 技术决策：进入生产部署前先做项目健康检查和部署风险审计，不直接大规模修改代码。
- 选择方案：先同步 GitHub，再输出 Phase 1 审计报告，等待确认后进入生产配置。
- 原因：避免在部署平台、数据库、向量库和认证方式未确认前引入错误架构。
- 放弃方案：直接改 Dockerfile / 直接部署到某个平台。
- 影响与风险：部署速度稍慢，但能降低返工和线上配置混乱风险。
- 相关文件或提交：`PROJECT_CONTEXT.md`、`docs/deployment-audit.md`、commit `18aa0ef`。

## 2026-08-26 — 采用渐进式上线架构

- 状态：已接受
- 背景：项目已有本地产品闭环，但认证、任务队列、对象存储和向量持久化尚未生产化。
- 技术决策：先完成本地生产化基础，再使用 Vercel + Render + Supabase 发布作品集版本，最后引入 Worker 和多用户 SaaS 能力。
- 原因：保留当前 Next.js、FastAPI 和 SQLAlchemy 架构，降低首次上线的服务数量和改造风险。
- 向量方案：本地阶段继续使用 Chroma；线上阶段优先迁移 Supabase pgvector。
- 数据库方案：本地 Docker PostgreSQL；线上 Supabase PostgreSQL；统一使用 Alembic 管理 schema。
- 影响与风险：作品集版本会限制长任务负载；完整可靠的视频处理依赖后续 Redis + Celery Worker。
- 相关文件：`docs/roadmap.md`、`TODO.md`、`backend/alembic/`。
