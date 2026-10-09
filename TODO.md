# TODO

## 进行中

- [ ] Sprint 02 用户系统（验收标准：Supabase 注册、登录、退出、Profile、后端 JWT 验证和用户数据隔离）

## 待办

- [x] 全新 PostgreSQL 验证 Alembic migration（完成日期：2026-08-26）
- [x] Docker 生产镜像构建验证（完成日期：2026-08-26）
- [ ] 本地视频完整闭环验证（优先级：高；向量库已可用，真实 URL 与模型调用仍待验收）
- [ ] `faster-whisper` 本地 ASR（优先级：高；阶段：Phase 8）
- [ ] 中文 Embedding Provider（优先级：高；阶段：Phase 8）
- [ ] Supabase 前端登录与会话管理（优先级：高；阶段：Sprint 02；代码已补，真实项目验收待做）
- [ ] FastAPI Supabase Auth 令牌验证与用户同步（优先级：高；阶段：Sprint 02；代码已补，真实项目验收待做）
- [ ] Supabase PostgreSQL / Storage / pgvector（优先级：高；阶段：Sprint 03）
- [ ] Vercel 前端与 Render 后端部署（优先级：高；阶段：Sprint 07）
- [ ] 视频处理任务队列方案（优先级：中；依赖：后端部署平台）
- [ ] 线上 Debug 文档与测试 Checklist（优先级：中；依赖：部署方案确认）

## 已完成

- [x] Phase 1-6 基础产品构建（完成日期：2026-08-01；验证：README、源码、前端 build、后端 compile）
- [x] GitHub 首次同步（完成日期：2026-07-31；验证：`origin/main`）
- [x] AI memory space 前端视觉重构同步 GitHub（完成日期：2026-08-01；验证：commit `18aa0ef`）
- [x] 部署审计和路线选择（完成日期：2026-08-26；选择：本地优先，Vercel + Render + Supabase 渐进上线）
- [x] Alembic、生产 Dockerfile、健康检查和处理状态基础实现（完成日期：2026-08-26；验证：migration、pytest、Docker build、HTTP health）
- [x] Next.js 16.3.3 安全升级（完成日期：2026-08-26；验证：typecheck、lint、build、npm audit 0 vulnerabilities）
- [x] Phase 7 本地生产化基础（完成日期：2026-09-04；验证：迁移、生产构建、健康检查）
- [x] 视频分享文本解析和 API 错误展示修复（完成日期：2026-09-04；验证：前端 build、后端测试）
- [x] 本地持久化 Chroma 与用户隔离检索（2026-10-08；测试与容器内烟测通过）
- [x] 视频一键处理、分析、入库与失败后续跑（2026-10-08；模拟服务测试通过，真实视频待验收）
- [x] 模拟 API 全链路验证个人 Key、入库、问答与用户隔离（2026-10-09；真实 Supabase 和服务商待验收）
- [x] 视频 Markdown 笔记复制与下载（2026-10-09；前端构建验证）

## 阻塞项

- Supabase 项目 URL 与 Anon Key 需要用户创建项目后填入本地 `.env`，不得提交 Git；后端通过 Supabase Auth 验证访问令牌。
- 云端长视频处理需要后续任务队列；首次上线先限制为演示负载。

- [ ] 用真实 Supabase 两个账户验收各自模型密钥、视频数据隔离与外部服务商计费；对外开放前完成。
- [ ] 检查生产密钥管理与轮换方案；目前 Fernet 主密钥丢失将无法解密已保存的用户 Key。
