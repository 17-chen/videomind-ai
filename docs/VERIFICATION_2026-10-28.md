# 2026-10-28 核查：R8 认证前流量控制

## 基线与范围

- 读取 AGENTS、交接、上下文、剩余计划和 TODO；`git fetch origin` 后 `HEAD...origin/main` 为 `0 0`，起点为 `d04f9df`。
- 原有未跟踪 `outputs/` 保留，不读取、删除或加入提交。未修改真实 `.env`、主密钥或业务数据库。
- 新增认证前单进程限流，覆盖来源/全局窗口、内存来源表上限、429 与 Retry-After、CORS 和中英文提示。配置和未完成边界见 [限流说明](INGRESS_LIMITS.md)。

## 本轮实际运行

| 检查 | 结果与证据范围 |
| --- | --- |
| `python -m pytest -q` | 102 passed；包括 6 项新增窗口/并发/容量/拒绝路径测试。认证和服务相关原有测试仍以模拟为主 |
| `ruff check app tests scripts` | All checks passed |
| 隔离 Uvicorn HTTP | 容器内部 127.0.0.1:18083，关闭 lifespan，临时设置 Supabase 模式及来源上限 2；匿名请求 401、401，带伪造 Bearer/转发头的第三次请求 429。请求编号、Retry-After、允许来源 CORS、健康检查豁免及 readiness 受限均通过。进程随后终止，没有访问真实认证服务 |
| `python -m scripts.evaluate_retrieval` | 退出 0，`passed=true`、`privacy_passed=true`；固定虚构语料和隔离内存 Chroma，不证明真实中文资料或生成回答质量 |
| 前端 build/typecheck/lint | 当前源码在 `videomind-frontend-check:20261025` 的隔离临时副本离线通过；先用 `cmp` 确认镜像与仓库 `package-lock.json` 完全一致，Next.js 实际版本 16.4.3 |
| `git diff --check` | 通过 |

## 检查过程发现与限制

- 运行中的开发前端依赖实际是 Next.js 16.3.3。首次临时副本检查虽然通过，但不作为当前锁文件的验证结果，也没有改动开发服务依赖。
- 临时 `npm ci` 因容器 DNS 的 `EAI_AGAIN` 失败，继而报 npm `Exit handler never called`。随后改用锁文件完全一致的已有镜像，离线验证成功。
- 临时副本将 node_modules 链接到镜像 `/app`，Next.js 16.4.3 提示 27 个文件位于 tracing root 之外，因此该临时 standalone 产物不作为可部署镜像；源码编译、类型与 lint 均退出 0。目标平台部署/镜像验收仍归 R9。
- pytest 的 LangGraph 弃用提示、检索的 Chroma 遥测与 ONNX CPU 提示仍存在，检查正常完成。
- Compose/Dockerfile 新启动命令带 `--no-proxy-headers`；未重建现有服务以变更其启动参数。真实 HTTP 检查使用了新参数，不宣称当前常驻服务已按新启动配置验收。

## 尚未验收

- 本地进程限流不是多实例统一计数或公网抗攻击验收，代理共享额度、HTTPS/重定向和平台负载需要后续核查。
- R8 下载/生成文件总容量、生产监控、真实主密钥恢复与轮换仍待做。
- R1 中文自然语音和跨主题检索/回答引用，R5 真实媒体在途故障及长期运行仍未完成。
- R2/R3 本人模型完整链路、R7 真实 Supabase 双用户、R6 云存储/pgvector、R9 目标平台发布仍未验收。
