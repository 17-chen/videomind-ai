# 2026-10-22 本地模型与依赖核查

## 环境与兼容性

- 本机为 Apple Silicon 上的 Colima Linux aarch64 容器。使用独立验证镜像安装可选依赖，现有 API/Worker 保持默认 hash 与关闭 ASR 的运行配置。
- 原宽松版本会解析出 `tokenizers 0.23.3`，与 ChromaDB 0.5.23 的 `<=0.20.3` 要求冲突；`faster-whisper 1.2.1` 搭配 PyAV 19.0.2 在真实音频解码时因 `metadata_errors` 参数报错。依赖范围已收紧，验证镜像的 `pip check` 无冲突。[faster-whisper 上游问题](https://github.com/SYSTRAN/faster-whisper/issues/1589)记录了 PyAV 19 的兼容原因。
- 实际版本：Python 3.12、PyTorch 2.5.1、faster-whisper 1.2.1、CTranslate2 4.8.3、PyAV 18.1.0、sentence-transformers 3.4.1、transformers 4.45.2、tokenizers 0.20.3、huggingface-hub 0.36.2。
- 模型缓存为 Git 忽略的 `storage/model-cache/`，两模型下载后约 243 MB。Whisper `Systran/faster-whisper-base` 快照 `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`；BGE `BAAI/bge-small-zh-v1.5` 快照 `7999e1d3359715c523056ef9478215996d62a620`。当前下载和测试不等于模型在正式部署机器上的验收。

## 真实模型运行结果

- 用 macOS `say -v Tingting` 自生成 8.24 秒中文 AIFF 音频，原句为“今天我们学习视频知识库。首先提取字幕，然后生成摘要，最后检索相关内容。”`faster-whisper base` 在 CPU int8 下实际输出“今天我们学习视频知识苦,首先提取字幕,然后生成摘药,最后减所相关内容。”模型缓存已就绪后的单次调用耗时 2.65 秒，进程峰值常驻内存约 356 MiB。存在“知识库/知识苦”等识别错误；合成语音不代表自然语音质量。样本保留在 Git 忽略的 `storage/audio/local-ai-sample.aiff`，未提交音频。
- 真实 BGE 模型通过隔离内存 Chroma 运行固定检索评测，原始逐题报告为 [`baseline_bge_zh.json`](../backend/evals/baseline_bge_zh.json)。语料 SHA-256 `4294248dddda86abb87d0661b238408366cf53a0bbaea7700e024c93c2066632`；top-k=3，分段 350 字、重叠 60 字。BGE Recall@3 为 100%、Precision@3 为 40.48%、MRR@3 为 1.00，跨用户违规 0；相同虚构语料的 hash Recall@3 为 96.43%。原 hash 的 `paraphrase-resume` 漏掉一个标准视频，BGE 本次命中。这个小型项目自编语料不证明真实视频问答质量。
- 评测仍出现 Chroma 遥测接口警告，任务正常结束。没有调用 Supabase、实际公开视频、自然语音或付费模型服务。

## 回归检查

- 默认运行容器：后端 75 项测试、Ruff、固定 hash 检索回归（最低 Recall@3 0.9）通过。
- 可选依赖验证镜像：`pip check` 无依赖冲突；接入现有 Compose PostgreSQL 网络后，后端 75 项测试通过。最初未接入该网络的一次运行在应用启动阶段无法解析 `postgres`，属于验证容器网络设置错误，修正后重跑通过。
- 前端仅作回归，临时副本生产构建、typecheck、lint 通过；本轮未改前端代码。`git diff --check` 通过。

## 公开真实视频与自然语音补验（2026-10-22）

- 素材为 [Wikimedia Commons 的 NASA《One Small Step》](https://commons.wikimedia.org/wiki/File:One_Small_Step_-_NASA.webm)，页面标注 NASA 制作、美国公有领域；56.121 秒，WebM VP9/Opus，2,990,645 字节。下载副本 SHA-256 为 `b5c5aed12227844dfa623a969333a71308c41e195d631e544cd240e58517bd05`，只保存在 Git 忽略的 `storage/videos/`。
- 独立本地 AI 镜像直接对该视频运行现有 ffmpeg 提音频和 faster-whisper base CPU int8：提音频 0.16 秒，转写 4.43 秒。真实多人通信音频可以产生非空文本；末句误识为 “One giant leap for man”，而 [NASA Apollo 11 语音记录](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/Apollo11VoiceTranscript-Geology.pdf) 为 “mankind”。这记录了实际识别错误，不算准确率达标。
- 进一步在一次性 PostgreSQL 容器中运行到 `20261021_0007` 迁移，使用临时媒体目录调用真实 `process_video`：Wikimedia URL 下载、无字幕提音频、转写、数据库保存成功，耗时 8.54 秒；同一真实文件经 `save_uploaded_video` 验证视频流并走上传来源的处理路径，转写保存成功，耗时 2.60 秒。默认运行的 API、Worker 和正式数据库均未切换模型或写入这组测试数据。
- 再以另一隔离用户和 `ASR_PROVIDER=disabled` 对无字幕文件处理，得到“视频没有字幕时需要 OpenAI 转写密钥”错误，视频状态为 `failed`，未生成转写。验证结束后停止并删除一次性数据库容器与临时脚本。
- 上述是服务函数与真实媒体的隔离验收；没有验证浏览器/HTTP 排队后的独立 Worker、真实笔记生成、向量入库、最终问答、Supabase 双用户或付费服务。一个 56 秒英文样例不能代表中文自然语音和长视频质量。
- 本次补验后默认容器 75 项后端测试与 Ruff 通过；固定 hash 检索回归 Recall@3 为 96.43%、隔离违规 0；前端临时副本生产构建、typecheck、lint 通过，`git diff --check` 通过。该检索分数仍来自虚构语料。
- 上一轮推送的 [CI 运行 39789748651](https://github.com/17-chen/videomind-ai/actions/runs/39789748651) 后端和前端通过，但提示旧版 Actions 的 Node.js 20 弃用和 `ubuntu-latest` 迁移。对照 [GitHub 官方 Action 元数据](https://github.com/actions/checkout/blob/v7/action.yml)、[GitHub 托管运行环境](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)后，升级 checkout/setup-node/upload-artifact 至 v7、setup-python 至 v6，并固定 Ubuntu 24.04；本机工作流 YAML 可解析，升级后远端结果另以对应运行记录为准。

## 未完成

- R1 已有一个允许使用的自然语音真实视频样例；仍需更多真实转写、人工答案标签、分段参数对照和最终回答引用核查；真实无字幕媒体的上传到笔记完整链路尚未验收。
- 正式后端镜像尚未切换到可选本地 AI 配置；独立验证镜像的成功不代表上线镜像已部署。本机 Docker 默认服务未修改。
