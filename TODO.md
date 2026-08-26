# TODO

## 进行中

- [ ] Phase 7 本地生产化基础（验收标准：迁移、生产构建、健康检查和完整本地闭环通过）

## 待办

- [x] 全新 PostgreSQL 验证 Alembic migration（完成日期：2026-08-26）
- [x] Docker 生产镜像构建验证（完成日期：2026-08-26）
- [ ] 本地视频完整闭环验证（优先级：高）
- [ ] `faster-whisper` 本地 ASR（优先级：高；阶段：Phase 8）
- [ ] 中文 Embedding Provider（优先级：高；阶段：Phase 8）
- [ ] Supabase PostgreSQL / Storage / pgvector（优先级：高；阶段：Phase 9）
- [ ] Vercel 前端与 Render 后端部署（优先级：高；阶段：Phase 9）
- [ ] 视频处理任务队列方案（优先级：中；依赖：后端部署平台）
- [ ] 线上 Debug 文档与测试 Checklist（优先级：中；依赖：部署方案确认）

## 已完成

- [x] Phase 1-6 基础产品构建（完成日期：2026-08-01；验证：README、源码、前端 build、后端 compile）
- [x] GitHub 首次同步（完成日期：2026-07-31；验证：`origin/main`）
- [x] AI memory space 前端视觉重构同步 GitHub（完成日期：2026-08-01；验证：commit `18aa0ef`）
- [x] 部署审计和路线选择（完成日期：2026-08-26；选择：本地优先，Vercel + Render + Supabase 渐进上线）
- [x] Alembic、生产 Dockerfile、健康检查和处理状态基础实现（完成日期：2026-08-26；验证：migration、pytest、Docker build、HTTP health）
- [x] Next.js 16.3.3 安全升级（完成日期：2026-08-26；验证：typecheck、lint、build、npm audit 0 vulnerabilities）

## 阻塞项

- 正式用户认证安排在 Phase 10，不阻塞作品集版本上线。
- 云端长视频处理需要 Phase 10 的任务队列，Phase 9 先限制为演示负载。
