# 2026-10-12 本地 AI 开发核查

本记录只描述本轮实际执行的检查。默认配置仍是 `ASR_PROVIDER=disabled` 与 `EMBEDDING_PROVIDER=local_hash`，本轮没有填写或使用真实服务商 Key。

| 范围 | 结果 | 边界 |
| --- | --- | --- |
| 后端测试 | 38 项通过 | 本地 Whisper 与 BGE 用假模型验证调用、提前失败、分段、用户隔离及删除；未下载真实模型 |
| 后端静态检查 | 通过 | `ruff check app tests scripts` 与 Python 语法编译通过 |
| 前端 | 通过 | 容器中 typecheck、lint、生产 build 通过 |
| Docker Compose 配置 | 通过 | `docker compose config --quiet` 成功 |
| 在线本地服务 | 通过 | VideoMind API 8001 的 readiness 返回数据库和向量库 `ok`；设置页 3000 返回 200 |
| 默认后端镜像重建 | 未完成 | Debian 基础系统软件包下载持续停滞，主动终止构建；未观察到 Dockerfile 语法错误 |
| 可选本地 AI 依赖与真实模型 | 未验收 | 未安装可选依赖、未下载模型、未用真实音频评测 |

下一步需要在网络正常且磁盘空间充足的机器上用 `INSTALL_LOCAL_AI=true` 构建后端，分别用一段有授权的无字幕短视频和一组中文问答样例测试。切换到 `bge_zh` 后运行 `python -m scripts.reindex_vectors`，再比较检索来源与答案。真实 Supabase、视频平台及付费模型验收仍按 [前次记录](VERIFICATION_2026-10-11.md) 进行。
