# 在新聊天恢复 VideoMind AI

更新：2026-11-08。新聊天连接本机真实仓库后，可以依赖已提交文件恢复；聊天历史和旧镜像不是当前运行事实。完整进度见 [PROJECT_HANDOFF 当前交接](../PROJECT_HANDOFF.md)。

复制以下文字到新聊天：

> 继续 VideoMind AI。真实仓库是 `/Users/chenxin/Documents/Codex 2/videomind-ai`。先读 `AGENTS.md`、`PROJECT_HANDOFF.md` 顶部当前交接、`PROJECT_CONTEXT.md`、`docs/COMPLETION_PLAN.md`、`TODO.md`，再核对 Git 工作树、最近提交和远端。最新功能基线 `37efbf9` 的 GitHub CI 前后端通过；后续交接文档提交以实际 HEAD 为准。当前云预览是 3001/8002，使用 Supabase Auth/SQL/私有 Storage/pgvector、本地 Whisper base 转写和用户本人的 DeepSeek；embedding 仍 local_hash。3000/8001 是旧本地演示，不要混淆。用户已确认登录和任务完成显示正常，并说内容已生成；优先复核“从入队到生成内容自动出现，全程不用手动刷新”的浏览器体验，再继续问答引用、双账号隔离、重启持久性/恢复和受保护部署。不要重新处理已完成视频或擅自重复付费模型调用。保留 `outputs/`、`backend/:memory:.ses`，不读取或提交其内容；保留所有用户数据和现有主密钥。3001 前端从私有源码副本运行，改仓库后须同步对应源码并验证。区分代码实现、模拟测试、真实运行和用户人工确认。完成后运行相关检查、更新文档并核对远端后同步 GitHub，不强制推送；中文报告。

## 恢复时应核对

- `git status --short --branch`、`git log -6 --oneline`、remote；不 reset/清理未知文件。
- [真实 Supabase 接入](VERIFICATION_2026-11-08_SUPABASE.md)、[Whisper 配置](VERIFICATION_2026-11-08_LOCAL_ASR.md)、[UI 修复](VERIFICATION_2026-11-08_UI.md)。359 项后端全量、10 项 ASR 相关测试、7 项前端测试均各有范围/日期，不代表新聊天已重跑。
- Colima 已获授权扩至 4GB，socket 为 `unix:///Users/chenxin/.colima/default/docker.sock`。重启前仍检查队列，保留原数据卷。
- 私有配置、启动器、前端运行副本、CA、新 ASR 缓存及备份在本机 `~/Library/Application Support/VideoMind AI/`，只能输出脱敏状态，不回显内容。当前 frontend-preview 与仓库独立，不能假设改源码会自动热更新 3001。
- 保留的旧云 API/Worker 带 `-before-local-asr-20261108` 后缀且停止；不得同时启动旧/新 Worker。完整回退说明见本地转写记录。
- 约 111 秒是一次成功任务整体耗时，不能当成 ASR 单独速度/中文质量或完整服务商验收。用户已说生成内容，不再要求重做注册；下一步补证据。

未完成：自动更新完整浏览器验证、真实问答引用、双用户/各自 Key、真实备份恢复与删除/重启持久性、旧文件迁移与 pending 解决、资源与生产限流监控、目标平台部署。公开部署没有完成，当前是本机连接云服务的预览；部署决策见 [部署时机](DEPLOYMENT_READINESS.md)。

没有本机仓库时，提供交接文档和 GitHub 源码即可恢复背景，但不能声称已检查本机运行或私有配置。不要上传密码、Key、Cookie、令牌、用户资料或备份归档。
