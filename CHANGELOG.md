# Changelog

记录有意义的用户可见变更和工程变更。最新日期置顶。

## 2026-08-26

### 新增

- 新增分阶段任务路线图，明确本地生产化、完整能力、作品集上线和多用户 SaaS 四个后续阶段。
- 新增 Alembic 首次迁移、API 存活检查和 PostgreSQL 就绪检查。
- 新增下载、转写、分析、向量写入等细粒度视频状态。

### 修改

- 前后端 Dockerfile 改为生产启动方式，Docker Compose 保留本地热更新命令。
- 前端升级到 Next.js 16.3.3，并迁移 ESLint flat config。
- 前端字体改为无构建期网络依赖的系统字体栈。
- 增加 Docker ignore 规则，显著缩小构建上下文。

### 修复

- 清除前端生产依赖安全告警，`npm audit --omit=dev` 为 0 vulnerabilities。
- 修复断网环境下 Google Fonts 导致的生产构建失败。

### 验证

- 前端 typecheck、lint、生产 build 和生产 Docker 镜像通过。
- 后端 Docker pytest 4 项通过，生产 Docker 镜像通过。
- 全新 PostgreSQL 的 `alembic upgrade head` 通过。
- 本地 API liveness/readiness 通过，前端生产容器首页和知识库返回 200。

## 2026-08-01

### 新增

- 新增项目上下文文件，用于后续部署和跨会话交接。
- 新增部署审计报告，记录生产化风险和分阶段上线建议。

### 修改

- 前端视觉重构为个人 AI 记忆空间风格：大卡片、胶囊按钮、黑白灰主视觉、粉紫 AI 强调。
- GitHub 已同步最新 UI 重构提交：`18aa0ef Redesign frontend as AI memory space`。

### 修复

- 无业务修复。

### 下一步

- 确认生产部署路线并进入生产配置阶段。
