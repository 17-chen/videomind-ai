# 2026-11-08 独立云预览本地转写修复

## 实际原因

用户报告按钮无反应时，浏览器实际停在 3000 旧演示版的失败视频，错误为缺少 OpenAI 转写 Key；云预览是 3001，原配置 ASR_PROVIDER=disabled。DeepSeek 的模型配置用于笔记/问答，本项目无字幕路径须另选本地 Whisper 或用户本人的 OpenAI 转写凭证。之前仅解释了本地方案，未启用，不能视为问题已解决。

已打开正确云预览登录页，保留旧页面和旧本地环境，不复制旧视频到云端，不代用户输入密码或 Key。

## 运行变更

- 旧本地 AI 镜像已有 faster-whisper，pip check 通过；原文稿目录模型缓存加载报不完整，宿主直接读取也超时。根因未进一步证明，未删除或覆盖缓存。
- 在本机 `~/Library/Application Support/VideoMind AI/asr-model-cache/` 独立下载官方 faster-whisper base 模型。模型加载/合成两秒静音解码通过，输出无语音段；这是运行检查，不是识别质量验收。
- 确认云队列 queued/running=0 后，停止并保留旧 API/Worker 容器，关闭旧容器自动重启以免竞争；私有旧配置同样保留。新容器仍使用当前后端源码，复用已有本地 AI 镜像，挂载新缓存只读，HF_HUB_OFFLINE=1。
- 仅云预览 API/Worker 配置 ASR_PROVIDER=faster_whisper、base、cpu、int8；API 8002、前端 3001、Supabase 认证/对象和 pgvector 保持。前端用户设置会读取当前 ASR 模式显示本地转写说明。原 3000/8001 演示配置未改，主密钥未重建。
- 模型缓存不与视频暂存 tmpfs 混放；既有阶段/暂存限制仍有效。模型推理会占用 CPU/内存，尚未完成长视频或多任务资源验收。

## 验证和限制

- 新 API/Worker 均报告 faster_whisper、supabase 认证与 supabase 文件后端，本地依赖存在。
- 当前 Worker 容器实际加载配置中的模型成功。真实 HTTP ready=200，数据库、向量、私有桶 ok。HTTP ready 自身不检查转写推理能力，因此另外执行模型加载检查。
- 无网络、无真实凭证的隔离容器执行 test_local_ai.py、test_no_subtitle_pipeline.py、test_ai_settings.py：10 passed。模型/服务响应在这些单测中为替身，另有上述真实离线模型烟测；既有 LangChain 弃用提示仍在。
- 本轮只改运行配置和文档，前后端业务源码未改；未重复前端构建或声称全量测试重新运行。
- 不自动重新入队、不读取视频正文或用户 Key、不触发付费 LLM。用户需在 3001 登录，查看本人知识库与模型设置，再显式处理视频。真实转写文字、DeepSeek 笔记/问答、双用户隔离与恢复仍未验收。

如需回退，先停新任务、确认队列无活动，再停止新云 API/Worker，恢复私有旧配置后启动保留的旧容器；不要同时启动两套 Worker，也不要删除数据卷。
