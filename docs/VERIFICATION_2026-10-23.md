# 2026-10-23 核查记录：真实媒体 Worker 与检索对照

## 范围与环境

- 开工时工作树干净，本地 `main` 为 `2ba2294`，与当时 `origin/main` 一致。
- 实际本机使用 Colima Docker socket。正式 API、Worker、PostgreSQL 与前端容器保持原配置；本轮验证使用一次性 PostgreSQL 和一次性本地 AI Worker，未读取或修改正式项目数据卷，也未使用个人模型密钥。
- 一次性数据库从空库迁移到 Alembic `20261021_0007`；本地 AI Worker 使用已安装可选依赖的 `videomind-ai-local-ai-probe` 镜像、faster-whisper base CPU int8 和隔离的临时存储。

## 真实媒体持久任务

- 使用 [NASA One Small Step 公开视频](https://commons.wikimedia.org/wiki/File:One_Small_Step_-_NASA.webm) 建立真实 URL 视频和 `process` 持久任务。任务 ID `1b43f4a1-fe58-4759-b755-5351144acc70`，视频 ID `1bbd958d-3df4-405a-84d3-d129dd7e2b53`；这些 ID 只存在于已清理的一次性数据库。
- 实际数据库任务状态从 `running / transcription / attempt 1` 变为 `succeeded / completed / attempt 1`。Worker 日志显示真实 URL 下载与转写阶段完成；数据库中保存 386 字符转写。本次任务只运行转写处理，没有分析、向量入库或生成问答。
- 验证后停止并自动移除 `videomind-eval-worker-20261023`、`videomind-eval-db-20261023`；正式 `videomind-worker` 与 `videomind-postgres` 未停止。

这补充了 R5 的“真实媒体由独立 Worker 领取并完成”证据；没有覆盖真实媒体运行中强制终止、多实例长期运行或付费外部调用。既有 2026-10-21 受控长任务租约、SIGKILL 与双领取演练不能替代这些情形。

## 真实文本检索评测

- [数据集](../backend/evals/retrieval_public_nasa_en.json)包含前次实际 ASR 的阿波罗英文转写、两条 NASA Minute 公开视频的真实英文字幕、跨用户相同文本及 12 道人工问题。源视频、字幕哈希、运行命令和五组原始逐题结果见 [评测文档](RETRIEVAL_EVALUATION.md)。
- top-k=2 时，hash Recall@2 为 68.18%；BGE 在 200/40、350/60、500/80 三种分段设置下均为 72.73%，跨用户违规均为 0。350/60 的候选倍数 1 与 5 得分和排序一致。
- 所有 BGE 设置都漏掉三道阿波罗问题。参数调整没有解决这个失败；保留原题和原报告。模型是中文 BGE，而这组真实样本是英文，不能用这组结果代表中文资料质量或完整问答质量。
- 评测只运行 embedding、Chroma 检索和用户过滤；没有生成回答、引用核对、真实 Supabase 会话或付费服务调用。

## 自动检查

- 后端完整 `python -m pytest -q`：82 passed，1 条 LangGraph 依赖弃用警告；`ruff check app tests scripts`：通过。
- 前端在容器内临时副本运行 `npm run build`、`npm run typecheck`、`npm run lint`：全部通过，未覆盖正在预览的 `.next`。
- 固定虚构中文 hash 回归仍保持原语料 SHA-256 `4294248dddda86abb87d0661b238408366cf53a0bbaea7700e024c93c2066632` 与 Recall@3 96.43%，跨用户违规 0；这不是实际服务验收。

## 剩余边界

真实中文自然语音转写、更多真实资料和引用准确性、个人服务商分析与生成问答、真实 Supabase 双用户、多实例长期运行及目标云端存储仍待验收。R1、R2、R5 等整体里程碑未因此完成。

## 同日后续：用户任务上限与向量故障续跑

- 新增 `MAX_ACTIVE_VIDEO_TASKS_PER_USER`，默认 2、允许 1–100；入队时同时计算该用户 `queued` 与 `running` 任务。超限返回 HTTP 429 和明确提示，同一视频重复提交仍返回 409。取消排队任务后名额释放；不同用户分别计数。此限制是任务接收上限，不是 Worker 同时执行数上限。
- PostgreSQL 入队事务先锁定用户行再计数、更新视频状态并插入任务，防止不同 API 会话同时通过计数。用一次性 `postgres:16-alpine` 从空库迁移到 `20261021_0007`，将上限设为 1，两个线程各用独立会话同时入队：一个成功、一个收到 429，活动任务数为 1；取消成功任务后第三个请求可入队。一次性容器已停止并自动移除，正式数据库和数据卷未参与。
- 模拟向量写入首次失败后重新触发持久 `run` 任务：第一次任务 `failed`，转写与摘要保留；第二次任务 `succeeded`，转写和分析各调用一次、入库调用两次。该测试覆盖复用逻辑，不代表真实付费模型或外部向量服务验收。
- 后端 `python -m pytest -q` 为 84 passed，`ruff check app tests scripts` 通过；本次未修改前端，上一提交的前端 CI 成功。
- 尚缺用户存储总量、请求频率控制、真实多实例持续负载与真实服务商故障演练。R2、R8 整项均保持未完成。
