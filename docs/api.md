# API 文档

FastAPI 会在 `/api/v1` 下暴露版本化 API。

交互式 OpenAPI 文档地址：

```text
http://localhost:8000/docs
```

## 已实现接口

### `POST /api/v1/videos`

提交一个视频 URL，创建视频处理任务。Phase 2 只入库并返回 `queued` 状态，真正的视频下载、字幕和 AI 分析会在 Phase 3/4 接入。

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
  "status": "queued",
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
- `search`：可选搜索关键词
- `category`：可选分类过滤

### `GET /api/v1/videos/{id}`

获取视频详情，包含视频元数据、转写文本、摘要和处理状态。

### `POST /api/v1/videos/{id}/process`

触发视频处理 Pipeline。

当前 Pipeline：

```text
Video URL
-> yt-dlp 下载视频与字幕
-> 优先解析字幕
-> 无字幕时使用 ffmpeg 提取音频
-> Whisper ASR 转写
-> Transcript 入库
-> 更新 Video 状态
```

响应：

```json
{
  "id": "video_id",
  "status": "processing",
  "message": "视频处理任务已启动"
}
```

### `POST /api/v1/videos/{id}/analyze`

启动 Phase 4 的 Video Analysis Agent。

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
- `.env` 必须配置 `DEEPSEEK_API_KEY`。
- 默认 LLM Provider 使用 DeepSeek。
- 默认模型使用 `LLM_MODEL=deepseek-v4-flash`。

### `POST /api/v1/videos/{id}/embed`

将视频写入 ChromaDB 向量知识库。

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
- 后续可以替换为 bge-m3、sentence-transformers 或托管 embedding 服务。

响应：

```json
{
  "id": "video_id",
  "vector_id": "video:video_id",
  "message": "视频已写入向量知识库"
}
```

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
