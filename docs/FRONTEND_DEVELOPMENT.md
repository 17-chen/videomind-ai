# 前端开发依赖与本机预览

2026-10-30：修复持久依赖卷继续使用旧 Next.js 的问题。仓库锁文件为 16.4.3，先前本机卷仍为 16.3.3，重建镜像并不会自动替换已有卷内容。

## 启动规则

Docker 开发镜像和 Compose 在启动开发服务前执行 `node scripts/ensure-dependencies.mjs`：

1. 计算当前 `package-lock.json` 的 SHA-256，与依赖卷中的标记比较。
2. 核对 package.json 的依赖声明与锁文件一致，以及直接依赖/开发依赖的已安装版本与锁文件一致。
3. 不一致或缺少标记时先运行 `npm ci --no-audit --no-fund`；安装/校验失败则退出，不继续启动旧依赖。

Dockerfile 在正常 `npm ci` 完成后写入标记。此校验针对开发环境的版本漂移，不是整个 node_modules 的内容完整性审计；多容器共用同一开发卷并发安装未验收。

Compose 改用 `frontend_node_modules_v2`。旧 `videomind-ai_frontend_node_modules` 卷保留，本轮没有清空或删除它；数据库、媒体和其他业务卷未变化。重新启动旧镜像时，绑定的源码仍有启动脚本，因此在依赖未同步时会明确失败。新环境仍按 README 构建镜像和启动即可。

## 本机已执行的修复

本机网络此前 npm 下载出现 DNS 故障，因此采用离线方式：先比较已有 `videomind-frontend-check:20261025` 镜像与仓库锁文件完全一致，再将其依赖初始化到新卷、写入锁文件指纹，仅重建前端容器。该手工预填卷会产生 Compose 的“已有卷不是由 Compose 创建”提示，但容器已成功启动；不是数据库错误，不应通过删除数据卷来消除提示。

随后使用 `--network host` 从当前 Dockerfile 重建开发镜像成功，并保留旧镜像标签 `videomind-frontend-dev-legacy:20261030` 后切换本机前端。没有修改全局 DNS/代理；禁网重建的 npm 安装曾失败，不作为成功证据。实际开发容器读取的 Next.js 为 16.4.3；首页、认证、设置、知识库均 HTTP 200。旧卷可以作为回退资料保留；回退时需要协调依赖挂载和启动校验，不能只把旧版本卷接回新启动命令。

## 检查

```bash
docker compose exec -T frontend node -p 'require("next/package.json").version'
docker compose exec -T frontend node scripts/ensure-dependencies.mjs
```

第二条命令在不匹配时会安装依赖，只应在开发服务启动前运行；日常只读核对使用第一条。更换锁文件后先按正常流程重建/启动，不能在运行中的依赖卷里手工覆盖文件。

生产构建继续使用隔离副本。本轮将依赖卷只读挂载到一次性容器的 `/check/node_modules`，源码复制到 `/check` 后执行 build/typecheck/lint，避免覆盖预览的 `.next`，也避免符号链接导致的 tracing-root 警告。Next dev 自动改写的 `next-env.d.ts` 路径不混入提交。
