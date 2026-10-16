# 中文检索评测

## 目的和边界

固定语料和正确视频列表，用相同的问题比较向量模型与检索代码。当前评测只覆盖检索，不调用生成模型，不验证最终回答的事实准确性。默认语料全部为本项目编写的虚构教学文本，不含真实用户资料或真实视频转写。

运行时使用 Chroma EphemeralClient 和独立集合，结束后移除该内存集合；不连接 PostgreSQL，不打开已有的持久向量库。生产 API 仍按原有配置连接向量库。请把评测作为独立命令运行，不要嵌入正在处理请求的服务进程。

## 运行

在仓库根目录执行：

```bash
docker compose exec backend python -m scripts.evaluate_retrieval
docker compose exec backend python -m scripts.evaluate_retrieval --top-k 3 --min-recall 0.9 --output /tmp/retrieval-report.json
```

默认 `--provider local_hash`，无需服务商 Key 或下载模型。启用本地 BGE 后，可在同一套数据上比较：

```bash
docker compose exec backend python -m scripts.evaluate_retrieval --provider bge_zh --top-k 3 --output /tmp/bge-report.json
```

BGE 需要安装 `requirements-local-ai.txt`，首次运行可能下载 `EMBEDDING_MODEL` 指定的模型。模型与分段长度会记录在报告中；此命令不会调用用户的付费模型 API。真实 BGE 尚未在本轮运行。

`--dataset <JSON路径>` 可加载其他语料。结构参考 `backend/evals/retrieval_zh.json`。视频 ID 和问题 ID 必须唯一，正确答案必须存在且属于提问用户；空答案只允许用于没有任何视频的用户，避免把尚未实现的语义拒答能力算作成功。

## 指标与检查

| 指标 | 定义 |
| --- | --- |
| Hit rate@k | 有标准答案的问题中，前 k 个不同视频至少命中一个答案的比例 |
| Recall@k | 每题命中标准视频数 / 该题标准视频总数，再对问题平均 |
| Precision@k | 每题命中标准视频数 / k，再对问题平均；返回不足 k 条也以 k 为分母 |
| MRR@k | 每题首个正确视频排名的倒数，未命中记 0，再对问题平均 |
| Privacy violation count | 返回了其他用户或未知视频 ID 的问题数；所有问题均参与检查 |

空知识库用例只参加隔离检查，不加入检索质量平均值；重复分段不会被重复计算为正确视频。报告同时保存语料 SHA-256、模型、top-k、逐题结果和检查项。

有隔离违规时返回退出码 1；显式设置 `--min-recall` 后，低于阈值也返回 1。默认不设置质量阈值，报告中的 `passed=true` 只说明隔离检查通过，不能当作产品质量验收。数据或参数错误返回非零退出码，已处理的数据/文件错误返回 2。

## 2026-10-16 基线

原始结果：[local_hash 基线 JSON](../backend/evals/baseline_local_hash.json)。语料版本为 `videomind-synthetic-zh-v1`，包含 12 条虚构视频文本、15 道问题，其中 14 道计入检索质量；top-k=3，hash 维度 384。

| 指标 | 结果 |
| --- | --- |
| Hit rate@3 | 100% |
| Recall@3 | 96.43% |
| Precision@3 | 38.10% |
| MRR@3 | 1.00 |
| 隔离违规 | 0 |

`paraphrase-resume` 仍漏掉标准答案中的 `queue` 视频，召回率为 0.5，报告保留原结果。多数问题只有一个标准视频，precision@3 上限因此通常为 1/3；这组数据规模小且标签不代表真实用户的完整相关性判断。高命中率不能推断真实中文语义检索已经达标。

后续应扩展真实且允许使用的转写与问答标签，再以相同语料对比 BGE、分段参数和回答引用。首次运行还出现了现有 Chroma 遥测接口兼容性警告和 ONNX CPU 提示，评测仍正常完成；本轮没有修改依赖版本或屏蔽这些提示。
