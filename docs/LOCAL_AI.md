# 本地转写与中文向量模型

这些功能不需要用户提供付费模型密钥，但首次运行需要下载模型文件，并消耗运行服务器的计算、内存与磁盘。若对外提供多用户服务，这部分服务器资源由站点运营方承担。AI 摘要与视频问答仍需当前用户自己的模型 API Key；本地配置不改变这条权限边界。

## 启用

在 Git 忽略的 `.env` 中按需设置：

```env
INSTALL_LOCAL_AI=true
ASR_PROVIDER=faster_whisper
LOCAL_WHISPER_MODEL=base
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
EMBEDDING_PROVIDER=bge_zh
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

重新构建后端：

```bash
docker compose --profile app up -d --build backend
```

直接在宿主机运行后端时，先安装 `requirements.txt` 和 `requirements-local-ai.txt`。Docker 把模型缓存映射到 `storage/model-cache/`，避免重建容器后重复下载。`storage/` 已被 Git 忽略。只使用字幕、云端转写或 `local_hash` 时保持 `INSTALL_LOCAL_AI=false`，不安装大型模型依赖。

`faster_whisper` 只在视频没有字幕时使用；有字幕仍优先读取字幕。默认 `base` 模型以 CPU int8 运行。首次调用需要下载模型，耗时取决于网络和机器。未安装组件时，处理会在提取音频前报出明确错误。

## 切换向量模型

`bge_zh` 使用 `BAAI/bge-small-zh-v1.5`，查询会加入中文检索指令。长文档按约 350 字分段并保留重叠，搜索结果按视频去重。它与旧 `local_hash` 使用不同的 Chroma 集合，避免维度和向量意义混用。切换后，用下面的命令把数据库中已有的转写与笔记重新写入当前集合：

```bash
docker compose exec backend python -m scripts.reindex_vectors --dry-run
docker compose exec backend python -m scripts.reindex_vectors
```

第一条只统计可重新入库的视频，不写入向量；确认数量后运行第二条。多用户部署时可加 `--user-id <用户ID>` 限定范围，用 `--limit <数量>` 先对前几条视频试运行；重复使用同一限制仍会从第一条开始。脚本按 ID 顺序逐批读取视频，跳过无转写且无摘要的视频；单条失败会回滚数据库事务、继续处理其余视频，最后列出失败视频 ID 并返回非零退出码。修复原因后重复运行即可，重新入库会更新同一视频的向量。

已有视频的旧向量集合不会自动清空；删除视频时会清理本项目的旧 hash 集合及所有 `bge_zh` 集合。重新入库运行期间，知识库搜索可能暂时缺少部分旧视频。改变 `EMBEDDING_MODEL` 后也需要重新入库。

同一视频重新入库时会先写入新分段，成功后再删除旧分段；写入失败不会先清空原有搜索内容。清理旧分段失败时可能暂时保留两版，搜索结果会按视频去重。

## 当前验收边界

代码和模拟模型测试可以在没有真实视频和付费 Key 的情况下执行；真实模型下载、真实视频转写速度与质量、中文问答准确性仍需在目标机器上验证。`local_hash` 保持旧版单向量行为；`bge_zh` 已分段，但分段长度和回答质量仍需真实内容评测。
