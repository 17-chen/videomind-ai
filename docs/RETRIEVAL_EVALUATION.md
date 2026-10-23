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

BGE 需要安装 `requirements-local-ai.txt`，首次运行可能下载 `EMBEDDING_MODEL` 指定的模型。模型与分段长度会记录在报告中；此命令不会调用用户的付费模型 API。2026-10-22 已在独立本地 AI 镜像中运行真实 BGE，结果如下。

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

## 2026-10-22 真实 BGE 模型对照

[BGE 逐题 JSON](../backend/evals/baseline_bge_zh.json)使用与 hash 基线相同的语料指纹 `4294248dddda86abb87d0661b238408366cf53a0bbaea7700e024c93c2066632` 和 top-k=3。模型为 `BAAI/bge-small-zh-v1.5`，本次缓存快照为 `7999e1d3359715c523056ef9478215996d62a620`；分段 350 字、重叠 60 字。

| 指标 | hash | BGE |
| --- | ---: | ---: |
| Recall@3 | 96.43% | 100% |
| Precision@3 | 38.10% | 40.48% |
| MRR@3 | 1.00 | 1.00 |
| 跨用户违规 | 0 | 0 |

BGE 在 `paraphrase-resume` 命中了 hash 漏掉的第二个标准视频。样本仅有 12 条项目自编文本，且评测不包含生成回答；应继续扩充真实授权资料与人工标签，再讨论质量阈值或分段参数。

## 2026-10-23 公开视频文本与参数对照

新增 [NASA 公开视频语料](../backend/evals/retrieval_public_nasa_en.json)：3 条英文视频文本、另一用户的一条相同文本副本，12 道人工编写并标注相关视频的问题（11 道计入质量，1 道空资料只检查隔离）。阿波罗视频文本来自 2026-10-22 实际 faster-whisper base 转写；[来源视频](https://commons.wikimedia.org/wiki/File:One_Small_Step_-_NASA.webm)，保存的转写 SHA-256 为 `e713d52dd6318ad52fcee02d28ed1674c1d9b436efdaa3464e04f5b8467486cf`。其中 “One giant leap for man” 是模型错词，保留原样。

另外两条来自 [5 月 8 日 NASA Minute](https://commons.wikimedia.org/wiki/File:NASA_Minute_May_8,_2026.webm) 和 [5 月 22 日 NASA Minute](https://commons.wikimedia.org/wiki/File:NASA_Minute_May_22,_2026.webm) 的公开英文字幕；原始 SRT SHA-256 分别为 `18096023e278948c4d0ff14e6115875adf9c332ddd7e88d131d709300b02b3b1`、`5022d5194cad4a352eeba3ef02448f8abce9454236525b721d1441320a9f1fae`。语料保留来源链接。它包含同义改写、文末信息、多视频答案与跨用户相同资料，但规模很小，标签并非全面相关性标注，也没有真实中文自然语音。

所有报告使用相同语料指纹 `20b17d73f85810dc857c3dc2281e9db22dcb9d74bfd74050fca4f2ca782db37d`、top-k=2 和独立内存 Chroma。BGE 模型为 `BAAI/bge-small-zh-v1.5`；数字是本次本地实际模型结果，不是模拟 embedding。下表各报告均保留逐题结果。

| 设置 | Hit@2 | Recall@2 | Precision@2 | MRR@2 | 跨用户违规 |
| --- | ---: | ---: | ---: | ---: | ---: |
| [hash 基线](../backend/evals/public_nasa_hash_top2.json) | 72.73% | 68.18% | 40.91% | 0.6364 | 0 |
| [BGE 200/40、候选倍数 5](../backend/evals/public_nasa_bge_200_40_m5.json) | 72.73% | 72.73% | 45.45% | 0.6818 | 0 |
| [BGE 350/60、候选倍数 5](../backend/evals/public_nasa_bge_350_60_m5.json) | 72.73% | 72.73% | 45.45% | 0.7273 | 0 |
| [BGE 500/80、候选倍数 5](../backend/evals/public_nasa_bge_500_80_m5.json) | 72.73% | 72.73% | 45.45% | 0.6818 | 0 |
| [BGE 350/60、候选倍数 1](../backend/evals/public_nasa_bge_350_60_m1.json) | 72.73% | 72.73% | 45.45% | 0.7273 | 0 |

三道阿波罗问题在所有 BGE 设置中均未进入前两条；hash 也漏掉这三题，并在 `space-weather` 只命中两个标准答案中的一个。候选倍数 1 与 5 的结果一致，因为检索不足两条不同视频时会继续扩大搜索。此次只比较了参数，没有据此改生产默认值。中文 BGE 处理英文资料的结果不能直接推断中文资料质量；下一步需要更多中文自然语音及跨主题样本，再定质量阈值和检查回答引用。

复现命令（BGE 需使用已安装可选依赖、已缓存模型的独立环境）：

```bash
python -m scripts.evaluate_retrieval --dataset evals/retrieval_public_nasa_en.json --provider local_hash --top-k 2 --output evals/public_nasa_hash_top2.json
python -m scripts.evaluate_retrieval --dataset evals/retrieval_public_nasa_en.json --provider bge_zh --top-k 2 --chunk-size 350 --chunk-overlap 60 --candidate-multiplier 5 --output evals/public_nasa_bge_350_60_m5.json
```

从 `backend/` 运行；把后三个参数改为表中组合即可复现其他报告。`--chunk-size`、`--chunk-overlap`、`--candidate-multiplier` 仅用于 BGE 评测，本轮未修改生产默认分段与候选数。报告的 `passed=true` 仅说明没有跨用户违规，72.73% 召回不应称为质量达标。
