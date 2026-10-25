# 2026-10-25 核查记录：日志、依赖与当前镜像

## API 日志

- 每个 HTTP 请求由后端生成 32 位十六进制请求编号，响应头为 `X-Request-ID`，CORS 暴露该响应头供前端读取。日志只写请求编号、HTTP 方法、路由模板、状态码和耗时；未匹配路由统一记 `<unmatched>`。API 错误日志只记状态码，未处理异常只记类型。
- 禁用 Loguru 局部变量诊断，并在应用启动时禁用 `uvicorn.access` logger；后端 Dockerfile 与 Compose 的 Uvicorn 启动参数也加入 `--no-access-log`，避免默认访问日志写入原始路径和查询串。正在运行的开发容器尚未重建，新的启动参数需下次重建后生效；应用日志配置由开发热重载加载。
- 3 项定向测试覆盖正常请求、带敏感路径/查询的 404、带凭证的 401，以及异常文本含敏感内容的 500；确认响应编号存在且应用日志没有输入的敏感文本。完整后端 92 passed，Ruff 通过。测试不能证明其他进程或外部日志服务的配置已脱敏。

## 前端依赖与镜像

- 2026-10-25 使用 npm registry 审计原锁文件：10 项告警（1 critical、5 high、4 moderate），其中 Next.js 16.3.3 命中 [Next.js 安全公告](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j)。将 Next.js 和 `eslint-config-next` 固定为 [16.4.3](https://github.com/vercel/next.js/releases/tag/v16.4.3)，运行兼容范围内的 `npm audit fix --package-lock-only` 后，完整审计为 4 moderate、0 high、0 critical；`--omit=dev` 同样为 4 moderate。剩余告警来自 Tailwind 3 / `postcss-nested` / `postcss-selector-parser` 构建链，npm 当时报告没有兼容修复；未强行跨主版本升级 Tailwind。
- 以更新后的锁文件从源码构建前端 production 镜像成功，Next.js 16.4.3 优化构建及内置 TypeScript 检查通过；独立容器 `/auth` 返回 HTTP 200。另以相同依赖构建隔离 development 镜像，`npm run typecheck`、`npm run lint` 均通过。没有替换正在运行的开发容器。

## 后端默认镜像

- 原 Dockerfile 在 Colima 的 Debian HTTP 软件源下载索引处两次停滞；同一基础容器访问官方 HTTPS 源可以响应。Dockerfile 将官方源地址切换到 HTTPS 后，`docker build` 从当前源码完整成功，`ffmpeg`、`ffprobe` 安装完成。
- 在不挂载仓库的独立镜像中，`from app.main import app` 成功、媒体工具可执行，`python -m pip check` 返回 `No broken requirements found`。这是当前本机 Colima 的默认镜像验证，不等于 Render 等目标环境构建或发布验收。
- 本轮源码提交 `aa1731d` 的 [GitHub Actions 运行 40152940072](https://github.com/17-chen/videomind-ai/actions/runs/40152940072) 后端测试、Lint、隔离 hash 检索基线及前端构建、类型检查、Lint 均通过。

## 尚未验收

- 尚未连接真实 Supabase、付费模型与云端存储，亦未在目标部署平台核对日志、镜像和数据持久性。日志聚合、告警、Worker 阶段关联，以及 Tailwind 构建链的 4 项 moderate 告警仍需后续处理。
