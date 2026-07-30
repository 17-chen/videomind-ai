# 当前自查记录

## 结论

项目方向是正确的。Phase 2/3 早期发现的关键结构问题已修复，Phase 4 的 AI 分析 Agent 基础能力已接入，Phase 5 的 RAG 基础闭环已开始落地，Phase 6 的前端基础 UI 已可运行。

## 已发现并修复的问题

- **Video 入参中的 tags 未落库**
  - 已在 `videos.tags` 中保存。

- **缺少 Pipeline 文件路径和错误字段**
  - 已增加 `media_path`、`audio_path`、`processing_error`、`processed_at`。

- **一对一关系表达不够明确**
  - 已给 `Video.transcript`、`Video.summary`、`Video.embedding` 增加 `uselist=False`。

- **Backend 不应在 Phase 2/3 强依赖 ChromaDB**
  - 已移除 backend 对 ChromaDB healthcheck 的启动依赖，避免 Phase 5 之前阻塞后端。

- **Phase 3 不能直接默认 Whisper**
  - 已增加字幕优先逻辑：yt-dlp 下载字幕后先解析 `.vtt/.srt`，没有字幕才提取音频并调用 Whisper。

- **缺少视频处理触发入口**
  - 已增加 `POST /api/v1/videos/{id}/process`。

- **Colima DNS 指向损坏的本地 resolver**
  - 已给 Colima VM 补充 resolver 文件，并给 Docker daemon 写入代理配置。

- **Docker Hub 拉取镜像超时**
  - 已通过 Docker daemon 代理配置修复，`postgres` 和 `backend` 已成功启动。

- **OpenAPI 和业务文案以英文为主**
  - 已改为中文主语言，并新增 `DEFAULT_LANGUAGE=zh-CN`。

- **缺少 AI 分析 Agent**
  - 已新增 `analysis_prompt.txt`、LangGraph Video Analysis Agent 和 `POST /api/v1/videos/{id}/analyze`。

- **RAG 不能假设 DeepSeek 提供 embedding**
  - 已新增本地 deterministic embedding 层，DeepSeek 只负责最终生成回答。

- **缺少 Chat With My Videos API**
  - 已新增 `POST /api/v1/videos/{id}/embed` 和 `POST /api/v1/chat`。

- **前端 Docker 和本机运行的 API 地址不同**
  - 已增加 `INTERNAL_API_BASE_URL`，服务端渲染在 Docker 内可走 `http://backend:8000/api/v1`，浏览器仍走 `NEXT_PUBLIC_API_BASE_URL`。

- **前端缺少稳定依赖锁定**
  - 已生成 `package-lock.json`，并固定 Next/React 核心版本，避免不同机器安装出不一致版本。

## 当前仍未完成

- 上传本地视频文件接口还未实现，当前 Phase 3 先跑 URL Pipeline。
- Alembic migration 还未正式接入，目前仍使用 `create_all` 适配 MVP 开发。
- 后台任务目前使用 FastAPI BackgroundTasks，生产级队列会在后续迭代中加入。
- 抖音/Bilibili 的下载成功率需要真实 URL、网络环境和平台策略验证。
- Phase 4/5 的真实 LLM 调用需要配置 `DEEPSEEK_API_KEY`，并且视频需要先完成 transcript。
- DeepSeek 不提供 Whisper 风格音频转写；当前 `ASR_PROVIDER=disabled`，无字幕视频需要后续接本地 ASR。
- 当前本地 hash embedding 可跑通 Demo 闭环，但中文语义效果不如 bge-m3 等专用 embedding 模型。
- ChromaDB 镜像此前拉取较慢，Phase 5 的运行验证依赖 Chroma 服务完成启动。
- Next.js 构建目前会提示 SWC optional dependency lockfile patch warning，但 typecheck 和 build 均已通过。
- LangGraph 当前有一个未来版本弃用 warning，不影响运行，后续升级依赖时处理。

## 下一步建议

1. 配置 `DEEPSEEK_API_KEY`。
2. 用 Bilibili 测试 URL 创建视频。
3. 触发 `/videos/{id}/process`。
4. 检查数据库中的 transcript 和 video status。
5. 触发 `/videos/{id}/analyze`。
6. 触发 `/videos/{id}/embed` 写入向量库。
7. 使用 `/chat` 询问个人视频知识库。
8. 使用 `http://localhost:3000` 检查前端页面。
9. 后续把 embedding 升级为更强的中文模型，并加入本地 faster-whisper。
10. 进入 UI 视觉精修，确定品牌色、信息密度、空状态和视频详情排版。
