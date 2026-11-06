# 2026-11-06 核查：对象成组发布与处理服务

## 本轮范围

- 按 AGENTS 恢复交接、上下文、完成计划和 TODO，核对源码与 Git；起点 `d355b2d`，fetch 后 main 与 origin/main 一致。
- 保留未跟踪 `outputs/`、`backend/:memory:.ses`，不读取内容、不修改、不提交；未改 `.env`、主密钥、真实用户配置或既有数据卷。
- 新增同一视频/种类的原子成组发布、完整快照替换及私有组读取；兼容原单文件替换。整组 pending 先提交，全部上传确认后才切换 ready；新组不含的旧 sidecar 名称一并退休。
- 处理服务显式注入对象客户端时，视频/音频使用 `object://UUID`，通过本人账本落地私有临时目录供字幕/ffmpeg/ASR；音频、转写及分析/手工笔记使用统一发布。视频引用、转写正文和笔记正文随组切换同 SQL 事务提交，向量同步仍在提交之后。
- 新增本地/对象混用保护，避免按本地 Path 漏算云端容量；对象预检和准入用户锁下都检查本地正式文件，本地准入拒绝该用户的非 deleted 对象/未决意图。没有新迁移，业务 head 为 `20261024_0008`，可选账本 head 仍 `20261105_o002`。
- **运行入口仍未切换**：没有新环境模式开关；HTTP 上传和持久 Worker 后端选择尚未接入。本轮是服务层接入，不是线上对象存储已启用。

## 已运行检查

- **后端最终：293 passed、0 skipped，Ruff 通过**（app/tests/scripts/alembic_pgvector/alembic_objects）。UID 65534，开启 PostgreSQL 配额、pgvector、对象 SQL 用例；原 LangGraph 弃用提示保留。
- **新增 22 项处理/组用例**：使用生产 Supabase 适配器 + HTTP MockTransport、真实文件与 SQLite；Supabase bucket/对象响应、身份、ASR 和 LLM 均为模拟。检查半组上传响应丢失仍保留整组旧版、配额净替换/整体拒绝、旧 sidecar 退休、非法/过大组、越权和错误引用、逐块落地、中途下载失败清理已落地明文、缓存目录权限和引用缺客户端时拒绝降级。
- **服务路径**：URL 下载替身实际生成媒体和 VTT，在对象发布后从本人私有组解析字幕；只有对象 ID 的上传来源在新 SQL Session/新 HTTP 客户端处理，不共享源文件。后者不经过上传 API，不计上传功能完成。转写实际消费私有缓存，使用模拟本人 Key；分析/笔记正文与手工保护检查通过。
- **真实本地媒体**：ffmpeg 从 lavfi 生成 0.5 秒视频，实际媒体经对象适配器上传和落地，再由真实受限音频执行器提取；ASR 返回模拟文本。未运行真实模型或外部视频下载。
- **新增 4 项真实 SQL 用例**：独立 tmpfs PostgreSQL 容器 `videomind-storage-test-20261106`、随机一次性数据库，无业务卷。两个连接发布两文件组：同视频最终只有一套一致摘要的 ready 组，跨视频共用额度时整组 200/413。真实 CHECK 拒绝 Video 引用/标题或笔记正文更新时，旧业务正文/引用与旧对象组一起保留，新组全部 pending。
- **前端**：源码未改；一次性禁网容器、依赖卷只读挂载，Next.js 16.4.3 build/typecheck/lint 与 4 项部署保护用例通过，未覆盖开发 `.next` 或修改依赖卷。
- **隔离检索**：实际 Chroma/local_hash，15 道固定虚构语料题，Recall@3 96.43%、Hit@3 100%、MRR@3 1.0、隔离违规 0；不是模型语义质量或生成回答验收。既有 Chroma telemetry/ONNX 主机提示保留，命令成功退出。

运行核对：当前业务库 head 仍 `20261024_0008`、对象账本不存在、向量仍为 chroma；readiness HTTP 200 且 database/vector_store 均 ok。未切换配置、迁移业务库或改变既有卷。本轮 tmpfs PostgreSQL 容器已停止删除，前端检查容器自动退出删除；既有容器/卷/镜像均保留。功能提交 `df1f8b2` 已同步 GitHub，[CI 42197987551](https://github.com/17-chen/videomind-ai/actions/runs/42197987551) 后端与前端均通过（全量回归/真实 SQL、Ruff、隔离检索、前端构建/类型/Lint/部署保护）。后续仅补验证记录。

## 未验收与下一步

- 继续上传 API、上传来源配额、持久 Worker/HTTP 统一后端工厂和 readiness；现有入口仍默认本地。对象服务参数不能当作公开切换开关，当前两块独立 Render 磁盘仍不能共享业务文件。
- 本地旧文件迁移/回退、物理副本容量与并发预留、pending 结果对账、用户整体删除、在途读取和云端恢复仍待做；不能靠删账本或改状态解除混用保护。
- 未接入真实 Supabase 身份、bucket/角色权限、云端持久性/计费，也没有本人模型真实生成闭环；真实本机 SQL/ffmpeg 与模拟云响应均不计真实服务验收。

详见 [对象存储说明](OBJECT_STORAGE.md)、[剩余计划](COMPLETION_PLAN.md) 与 [部署时机](DEPLOYMENT_READINESS.md)。
