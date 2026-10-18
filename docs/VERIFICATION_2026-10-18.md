# 2026-10-18 自动检查核查

## 范围与 Git

- 开工时本地 `main` 工作树干净，远端领先一个 `700ccde` 字幕选择修复提交；已用 `git merge --ff-only origin/main` 合入。
- 本轮新增 `.github/workflows/ci.yml`，在 push 与 pull_request 上运行后端和前端两个独立任务；没有向 CI 提供用户密钥或真实资料。

## 本地实际检查

- 运行中的后端容器：`python -m pytest -q`，**63 passed，1 条 LangGraph 待弃用警告**；`ruff check app tests scripts` 通过。
- 相同容器：`python -m scripts.evaluate_retrieval --provider local_hash --top-k 3 --min-recall 0.9` 通过；虚构语料 Recall@3 为 **0.9642857143**，用户隔离违规 **0**。Chroma 遥测兼容性与 ONNX CPU 提示不影响退出码，未为此升级依赖。
- 前端容器内复制源码到临时目录并链接现有依赖，`npm run build`、`npm run typecheck`、`npm run lint` 均通过。没有覆盖正在运行的 `/app/.next`。
- `git diff --check` 通过。

## 远端 CI

首次 GitHub Actions 运行 [39103574463](https://github.com/17-chen/videomind-ai/actions/runs/39103574463)：前端通过，后端 60 项通过、1 项失败、2 项初始化失败。失败原因是三个 API 测试会启动应用并连接 PostgreSQL，而最初的 CI 配置没有数据库服务，默认主机名 `postgres` 在 GitHub runner 上无法解析。随后为后端任务增加临时 PostgreSQL 16 服务和 CI 专用连接地址；修复后的运行结果待补充。

工作流的固定检索门槛仅用于防止当前虚构语料回归；不等同于真实 BGE、ASR、真实视频、生成答案或真实 Supabase 验收。

## R1 条件

现有后端容器未安装 `faster_whisper` 与 `sentence_transformers`，模型缓存目录无已下载模型；因此本轮没有真实本地模型结果，也没有把模拟测试标为真实验收。后续需在目标运行环境安装可选依赖并下载模型，再做真实音频与 BGE 对照。
