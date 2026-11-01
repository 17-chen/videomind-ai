# 2026-11-01 核查：音频进程中断与恢复

## 起点与改动

- 已读取 AGENTS、交接、上下文、剩余计划与 TODO；起点 `6c54a11`，拉取远端后本地与 `origin/main` 一致。
- 原有未跟踪 `outputs/`、`backend/:memory:.ses` 保留，未读取正文、修改或提交。
- R5/R8：Linux 音频 launcher 使用父进程退出信号停止 ffmpeg，并在设置后核对预期父 PID，覆盖启动竞态。Linux 设置失败不执行命令；继续保留既有单文件限制与超时。
- Compose Worker 增加 `init: true`，回收被收养子进程。不增加依赖，不改数据库结构、用户密钥或权限，不清理未知文件。

## 实际验证

- **后端全量：146 passed，Ruff 通过。**以 UID 65534、`RUN_POSTGRES_QUOTA_TESTS=1` 运行，无跳过；含既有两个真实 PostgreSQL 双会话用例。保留原 LangGraph 弃用提示。
- **真实 ffmpeg 中断：**自生成 10 秒静音 WAV；测试专用 wrapper 用 `-re` 控制速度、`-flush_packets 1` 刷新输出。生产参数不受影响。独立执行进程调用实际 `claim_next_task` / `execute_claimed_task`，确认 ffmpeg 正在写本次私有暂存 MP3，再分别 SIGKILL、SIGTERM 终止执行进程。两种情况下 ffmpeg 均停止，旧正式音频保持不变，数据库没有发布部分音频。
- **恢复重试：**在隔离 SQLite 中将租约时间改为已过期，再由实际恢复函数重新入队；第二个独立执行进程重新提取真实音频成功，尝试次数 2，任务成功。ASR Key 解析和转写响应为测试替身，不请求云服务；租约时间推进为模拟，没有等待实际 90 秒，更不等于 PostgreSQL 多实例故障验收。
- **遗留文件：**强制退出的旧暂存目录保持存在、大小不再增长；重试只发布自己的新输出，不删除旧目录。测试通过 subreaper 回收自己制造的孤立进程，恢复测试进程原来的 subreaper 状态。
- **正常超时：**真实 ffmpeg 被音频超时终止并回收，任务失败，旧正式音频保留，本次暂存目录被正常清理，没有执行模拟 ASR。
- **启动竞态/失败：**实际 launcher 在预期父 PID 不符时不执行目标命令；模拟 `prctl` 设置失败会拒绝继续。原有真实内核文件限制和常规 ffmpeg 测试继续通过。
- 首次目标测试中一项因 ffmpeg 缓冲而未稳定观察到在途文件，改用仅测试 wrapper 的逐包刷新；随后目标 5 项及全量 146 项通过，没有放宽生产上限或省略失败检查。
- **前端：**当前 Next.js 16.4.3，在临时源码副本 build/typecheck/lint 通过，没有覆盖预览 `.next`。临时副本软链接 `/app/node_modules`，standalone tracing 提示部分依赖在临时根外；这个副本不用于部署镜像。GitHub CI 会在正常安装布局再次检查。
- **运行配置：**Compose 配置校验通过；先只读确认 queued/running 均 0，再仅重建 Worker。新 Worker 的 `/proc/1/comm` 为 `docker-init`，音频监督模块可加载；后端 readiness HTTP 200。
- **实际磁盘只读对账：**扫描完整、活动任务 0、扫描错误 0，暂存/待提交 part/UUID 孤立文件均 0；此前 9 个未归属文件共 6,798,912 字节仍保留。故障媒体和测试 SQLite 均在测试私有临时目录。

功能提交 `fe52987` 已同步 GitHub，[CI 41295419944](https://github.com/17-chen/videomind-ai/actions/runs/41295419944) 后端与前端均通过。远端覆盖后端测试/Ruff、隔离 hash 检索基线，以及正常安装布局的前端 build/typecheck/lint；不代表真实模型或部署验收。

## 未验收边界

- 监督只保证 Linux 下直接启动、普通无提权 ffmpeg 的父进程退出行为；非 Linux 原生环境保留 POSIX 文件限制，但没有该父进程退出保证。Linux 不允许 `prctl` 的环境会拒绝执行媒体命令。
- yt-dlp 下载/合并子进程、其他后代进程和付费外部调用不在本轮监督范围。没有通过在途付费步骤、长期多实例或目标云平台验收。
- SIGKILL 遗留暂存目录未自动清理；本轮不授予未知文件删除权限。并发空间预留、合并硬限制、生产统一限流仍待完成。
- 本轮真实部分是媒体进程、信号与文件行为；队列故障使用 SQLite，ASR/租约时间为模拟。未运行中文自然语音质量、真实服务商分析/问答、Supabase 双用户、云存储或正式部署验收。
