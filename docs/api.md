# API 文档

FastAPI 会在 `/api/v1` 下暴露版本化 API。

交互式 OpenAPI 文档地址：

```text
http://localhost:8000/docs
```

## 已实现接口

### `POST /api/v1/videos`

提交一个视频 URL，创建归属于当前用户的待处理记录，返回 `created`；处理由 `/process` 或 `/run` 显式启动。

请求体：

```json
{
  "url": "https://www.bilibili.com/video/...",
  "title": "可选标题",
  "description": "可选描述",
  "tags": ["AI Agent", "创业"]
}
```

响应：

```json
{
  "id": "video_id",
  "user_id": "user_id",
  "status": "created",
  "source": "bilibili",
  "url": "https://www.bilibili.com/video/...",
  "title": "可选标题",
  "description": "可选描述",
  "duration": null,
  "thumbnail": null,
  "transcript": null,
  "summary": null,
  "created_at": "2026-07-29T00:00:00Z",
  "updated_at": "2026-07-29T00:00:00Z"
}
```

### `GET /api/v1/videos`

分页获取当前用户的视频列表。

查询参数：

- `limit`：每页数量，默认 `20`
- `offset`：偏移量，默认 `0`
- `search`：可选搜索关键词，最长 120 字符，匹配原始标题、描述、链接以及 AI 标题和摘要；`%`、`_` 按普通文字匹配。
- `category`：可选分类过滤，最长 120 字符。

响应的 `total` 为筛选后的视频总数；排序为创建时间倒序、ID 倒序。前端 `/library` 使用从 1 开始的 `page` 参数转换为 offset，每页 20 条。

### `GET /api/v1/videos/upload-policy` 与 `POST /api/v1/videos/upload`

前者返回当前服务端的 `max_bytes` 和支持的扩展名；后者使用 `multipart/form-data` 的 `file` 与可选 `title` 上传本人视频。支持 MP4、WebM、MKV、MOV、M4V，并要求 MIME 合理、大小不超过限制、ffprobe 能识别实际视频流。服务端生成保存文件名，不使用客户端路径。成功返回视频详情，`source=upload`、`status=created`；重复上传同一内容返回 409，超限返回 413，不支持或无效媒体返回 415。上传资料的问答来源指向应用内详情页。

上传后可调用已有的 `/process` 或 `/run`，跳过 yt-dlp 并对本地文件提取音频。若未启用本地 ASR，也未配置本人可用的 OpenAI 转写密钥，处理会失败并显示提示。当前真实模型与服务商完整链路尚未验收。

### `GET /api/v1/videos/categories`

返回当前用户整个视频库中的非空分类字符串数组，去重并排序，不受列表分页或搜索条件影响。Supabase 模式下需要有效用户令牌。

### `GET /api/v1/videos/{id}`

获取视频详情，包含视频元数据、转写文本、摘要和处理状态。

### `PATCH /api/v1/videos/{id}`、`PUT /api/v1/videos/{id}/note`、`POST /api/v1/videos/{id}/sync-index`

本人可以编辑视频标题（≤500 字）、备注（≤10000 字）、标签（≤20 个，每个 1–60 字）和分类（≤120 字）。空分类撤销手工覆盖并恢复 AI 分类。笔记须先有 AI 摘要，可保存 ≤100000 字 Markdown；保存后标记为手工笔记，后续 AI 重新分析更新结构化摘要但保留手工笔记。其他用户返回 404，处理中返回 409。

已入库资料编辑后立即重建本人向量。若向量更新失败，接口仍返回已保存的数据库内容，同时 `index_sync_error` 给出待同步状态；旧向量可继续被检索。详情页可调用 `sync-index` 重试。数据库与 Chroma 不具备跨存储原子事务；客户端不得把有同步错误的响应当作完整成功。

### `POST /api/v1/videos/{id}/process`

返回 202 并创建 PostgreSQL 持久任务，由独立 Worker 执行视频处理 Pipeline。`POST /run`、`POST /analyze`、`POST /embed` 也返回 202；它们不再在 API 请求里执行耗时步骤。

当前 Pipeline：

```text
Video URL → yt-dlp 下载视频与字幕 → 优先解析字幕
或本地上传 → 读取服务端保存的视频文件
-> 无字幕时使用 ffmpeg 提取音频
-> 配置的本地或用户本人云端 ASR 转写
-> Transcript 入库
-> 更新 Video 状态
```

响应：

```json
{
  "id": "video_id",
  "status": "queued",
  "message": "视频处理任务已启动",
  "task_id": "task_uuid"
}
```

### `POST /api/v1/videos/{id}/analyze`

将 Phase 4 的 Video Analysis Agent 入队；须已有 transcript 和本人模型配置。

输入来源：

```text
Transcript
-> Video Analysis Agent
-> 结构化 JSON
-> Markdown 笔记
-> Summary 入库
```

要求：

- 视频必须已经有 transcript。
- 已认证用户必须先在个人设置中保存自己的模型配置；缺 Key 时不会回退到项目所有者密钥。
- 默认 Provider 是 DeepSeek，新配置默认模型为 `deepseek-flash`。

### `POST /api/v1/videos/{id}/embed`

将视频入库任务排队，由 Worker 写入 ChromaDB 向量知识库。

输入来源：

```text
Video metadata
+ Transcript
+ Summary
+ Markdown Note
-> 本地 embedding
-> ChromaDB
-> Embedding 映射入库
```

要求：

- 视频至少需要有 transcript 或 AI summary。
- 当前默认 `EMBEDDING_PROVIDER=local_hash`，不依赖 OpenAI。
- 可选 `bge_zh` 使用独立集合与分段索引；真实模型效果尚未验收。

响应为 202，包含 `id`、`status=queued`、`message` 和 `task_id`。完成后从视频详情或任务接口查询结果。

### `GET /api/v1/videos/{id}/task`、`POST /api/v1/videos/{id}/task/cancel`

前者返回本人视频的最近任务，包含 `kind`、`status`、`stage`、`attempts`、`error` 和时间；无任务返回 `null`。后者取消本人排队任务，或对运行中任务设置取消请求；Worker 在当前阶段结束后停止后续阶段。其他用户返回 404。失联任务经租约恢复；可能产生费用的阶段如未确认落库，会停止自动重试并要求人工发起新任务。

### `POST /api/v1/chat`

Chat With My Videos：基于当前用户的视频知识库检索相关资料，再调用 DeepSeek 生成中文回答。

请求体：

```json
{
  "question": "我之前收藏过哪些关于 AI Agent 创业的视频？",
  "limit": 5
}
```

响应：

```json
{
  "answer": "基于你的视频知识库，相关内容主要集中在...",
  "sources": [
    {
      "video_id": "video_id",
      "title": "视频标题",
      "url": "https://www.bilibili.com/video/...",
      "category": "Technology",
      "distance": 0.23,
      "snippet": "命中的内容片段..."
    }
  ]
}
```

### `GET /api/v1/health`

API 健康检查。

### `GET /health`

应用级健康检查。

## 后续接口规划

- `GET /api/v1/videos/{id}/transcript`
- `GET /api/v1/videos/{id}/notes`
- `PATCH /api/v1/videos/{id}/notes`
- `GET /api/v1/categories`
- `PATCH /api/v1/videos/{id}/category`
