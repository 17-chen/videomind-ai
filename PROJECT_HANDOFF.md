# VideoMind AI 完整交接文档

> 更新：2026-10-23。供新聊天或新开发者直接接手；这份文件描述当前状态，早期逐日过程请查 CHANGELOG 与有日期的验证记录。文档不含真实密钥。

## 1. 先读摘要

项目把收藏的视频转为转写文本、结构化 AI 笔记、可搜索的个人知识库和可追溯来源的问答。基础产品已能在本地演示；正式多用户所需的真实认证验收、可靠队列、云端存储和上线收尾仍未完成。

- **真实仓库：**`/Users/chenxin/Documents/Codex 2/videomind-ai`。
- **GitHub：**`https://github.com/17-chen/videomind-ai`；remote 为 `git@github.com:17-chen/videomind-ai.git`，主分支 `main`。
- **最近功能基线：**2026-10-21 增加 PostgreSQL 视频任务、独立 Worker 和 `20261021_0007` 迁移；2026-10-22 补了本地 AI 兼容性与真实公开视频处理验收。恢复时以实际 Git 为准。
- **2026-10-23 开工前：**工作树干净，本地 `main` 与 `origin/main` 一致，提交 `2ba2294`；完成时再次核对实际 Git 状态。
- **最新后端证据：**2026-10-23，默认容器 82 项测试及 Ruff 通过；真实 NASA URL 的持久任务在一次性 PostgreSQL 与独立本地 AI Worker 中完成下载和转写。真实英文资料的 hash/BGE 检索参数对照保留失败题，详见 [核查记录](docs/VERIFICATION_2026-10-23.md)。
- **最新前端证据：**2026-10-23，临时副本的生产构建、typecheck、lint 通过；任务阶段和取消入口已接入。
- **自动检查：**开工前最近的 [GitHub Actions](https://github.com/17-chen/videomind-ai/actions/runs/39790202539) 后端、前端任务均通过；新提交以其实际运行结果为准。R9 仅自动检查子项完成。
- **2026-10-22 本地模型证据：**独立镜像的可选依赖与 `pip check` 通过；faster-whisper base 已转写合成中文音频及一个 NASA 真实公开视频。后者的 URL 下载、本地上传、无字幕缺 Key 失败路径在隔离数据库通过；真实 BGE 在固定虚构语料上完成隔离检索，详见 [核查记录](docs/VERIFICATION_2026-10-22.md)。
- **下一步：**R1 补中文自然语音与跨主题样本、核对回答引用；R2 完成真实分析/问答，R5 继续真实媒体故障、付费阶段与多实例长期运行验收。
- **本轮未完成的验收：**中文自然语音质量、真实笔记/向量/问答、Supabase/服务商调用和多实例运行仍待验证；英文公开视频的 72.73% Recall@2 也不是完整服务质量验收。

先读本文件，再读 [剩余工作](docs/COMPLETION_PLAN.md)、[项目上下文](PROJECT_CONTEXT.md)、[TODO](TODO.md)。详细索引见 [项目资料](docs/PROJECT_MATERIALS.md)；新聊天开场文字见 [恢复说明](docs/NEW_CHAT_START.md)。

## 2. 用户目标和协作偏好

1. 网站中英文切换，中文为默认界面；已实现，不要重做。
2. 登录用户使用自己的模型、API Key 和服务商账户计费；禁止回退到站长的密钥。
3. 开发应先核对现有功能、修复问题，再推进明确的后续项；完成后报告实际检查结果。
4. 用户多次要求开发成果同步 GitHub，并希望能本地预览。发布行为以当前聊天明确授权为准；历史偏好不能替代新会话授权。
5. 用中文、尽量不用不必要的技术术语；常规可逆开发自主完成，遇到真实缺失信息再说明。
6. 用户要求长期保留项目记忆；每轮重要工作更新文档，不依赖聊天自动继承。
7. 2026-10-16 的工程估算：本地功能收束 16–26 小时，完整小规模多用户版本累计 50–80 小时；不计等待用户注册/授权账号，包含配置后的联调修复。详见剩余计划，不是保证日期。

## 3. 架构和代码入口

保留现有 monorepo，不要为恢复上下文而更换框架。

| 模块 | 当前实现 | 入口 |
| --- | --- | --- |
| 前端 | Next.js 16.3.3、React 19、TypeScript、Tailwind | `frontend/app/`、`frontend/components/` |
| 中英文 | Cookie 记录语言，前后端提示逐步双语化 | `frontend/lib/{i18n,language,server-language}.*` |
| 前端接口 | 浏览器与服务端分别选择 API 地址，传递用户令牌 | `frontend/lib/api.ts` |
| 认证 | 默认 demo；可选 Supabase Auth 校验与用户映射 | `frontend/lib/supabase/`、`backend/app/{api/dependencies,services/auth}.py` |
| API | FastAPI /api/v1，SQLAlchemy 数据访问 | `backend/app/api/v1/routes/`、`backend/app/main.py` |
| 视频处理 | yt-dlp、字幕优先、ffmpeg 提取音频、可选 ASR | `backend/app/services/video_processing/` |
| 持久任务 | PostgreSQL 入队 → 独立 Worker 分阶段执行与取消 | `backend/app/services/video_tasks.py`、`backend/scripts/video_worker.py` |
| 分析 | LangGraph 生成结构化摘要和 Markdown | `backend/app/agents/video_analysis_agent.py`、`backend/app/services/analysis.py` |
| 个人 Key | 按用户保存，加密存储，不回传明文 | `backend/app/services/ai_settings.py`、`backend/app/models/ai_settings.py` |
| RAG | hash 默认、BGE 可选，Chroma 检索后生成回答 | `backend/app/services/{rag,embeddings,vector_store}.py` |
| 数据 | PostgreSQL 保存用户、视频、转写、摘要、向量映射和设置 | `backend/app/models/`、`backend/alembic/` |
| 本地文件 | 媒体、音频、转写、笔记和模型缓存 | `storage/`，不随 Git 提交 |
| 运维脚本 | 迁移、向量重建、固定检索评测 | `backend/scripts/` |

已接受的方向：本地优先，后续 Vercel + Render + Supabase；向量生产适配拟采用 pgvector。当前本地任务使用 PostgreSQL 队列，Redis/Celery 是后续部署负载明确后的候选。长期决定见 [DECISION_LOG](DECISION_LOG.md)。

## 4. 已有功能与验收边界

| 能力 | 代码状态 | 已有证据 / 仍缺什么 |
| --- | --- | --- |
| URL 和分享文本添加视频 | 已实现 | 本地 API 创建/读取/删除烟测通过；真实平台下载仍受网络和平台影响 |
| 详情、阶段状态和一键流程 | 已实现 | 模拟 API 全链路、失败续跑和并发请求保护通过；真实视频完整链路未验收 |
| 字幕与转写 | 已实现字幕优先，可选 faster-whisper/OpenAI | 真实 faster-whisper 已在合成中文音频及 NASA 自然语音视频上运行，均有识别错误；中文自然语音和完整笔记链路未验收 |
| AI 笔记 | 已实现摘要、观点、行动项和 Markdown | 模拟调用通过，前端支持复制/下载/手工编辑；手工笔记在重新分析时保留 |
| 中英文和个人模型设置 | 已实现 | 设置读写状态与加密、demo 禁止写 Key、本人配置调用路径已有测试；真实服务商计费待验收 |
| Supabase 注册/登录/退出/刷新 | 代码已实现 | 模拟身份、令牌验证、邮箱冲突与路由保护通过；真实双用户浏览器验收未做 |
| 知识库分页、搜索、分类 | 已实现 | 每页 20 条，筛选保留、AI 标题/摘要搜索、全库分类；52 项后端测试阶段和生产页面样例通过 |
| 持久化 Chroma 与删除 | 已实现本地单实例 | 持久化重开、用户过滤、跨集合清理和故障保留有测试 |
| BGE 长文本索引 | 已接入可选实现 | 真实模型已在虚构中文及 NASA 英文公开视频文本上对照 hash；英文样本三道阿波罗题漏检，中文真实资料质量待验收 |
| 固定检索评测 | 已完成工具、虚构语料基线及小型真实英文资料对照 | 内存 Chroma，15 个虚构问题加 12 个 NASA 视频人工问题；后者分段/候选对照与失败题见评测文档，生成回答未验收 |
| 本地上传 | 代码已实现 | 自生成视频的真实本地 HTTP 上传、重复冲突、删除清理及模拟处理链路通过；NASA 真实文件的上传来源与本地 ASR 在隔离数据库通过，本人模型与双用户验收未做 |
| 资料编辑 | 代码已实现 | 本地 API 编辑/筛选、权限与模拟向量故障通过；真实多用户与模型未验收 |
| 持久任务、取消 | 本地代码已实现 | API 重启保留任务、独立 Worker、双 Worker 竞争、受控长任务心跳与执行进程 SIGKILL 恢复通过；真实 NASA URL 的 Worker 下载/转写通过，真实媒体故障、付费阶段和多实例未验收 |
| 云存储/pgvector、配额监控、正式部署 | 未完成 | 详见 R6、R8、R9 |

## 5. 关键实现约束

- **密钥归属：**Supabase 模式按当前用户读取模型配置。demo 访问共用演示用户，因此禁止保存个人 Key，不能直接开放成多用户站点。
- **认证映射：**只按 Supabase subject 映射本地用户；已有邮箱冲突拒绝自动合并，避免接管 demo 或其他账号资料。
- **加密主密钥：**`USER_API_KEY_ENCRYPTION_KEY` 保存在未提交环境中。不能为排错随意覆盖或重新生成，否则已有加密 Key 无法读取。
- **用户隔离：**视频查询、分类、处理和删除按 user_id；向量检索也有 user_id 过滤。未来上传、任务和存储接口必须继承同一边界。
- **任务：**处理、分析、入库目前使用 PostgreSQL VideoTask 与独立 Worker；同视频活动任务由状态与部分唯一索引保护。失联租约可恢复，旧 Worker 在接管后不能推进下一阶段或覆盖任务终态。分析和可能已计费的云端转写中断要求手动重试。取消在阶段边界生效，不能中断当前外部调用；在途调用的外部副作用仍需单独评估。
- **安全索引：**BGE 新分段使用内容版本 ID，先写入新版本，再清理旧版本；新写入失败时旧内容可继续检索。清理失败可能短时留两版，由检索按视频去重。
- **删除顺序：**先删本人向量，再提交数据库删除，再清理本地文件。跨存储不具有原子事务；失败边界见技术决策日志。
- **模型切换：**hash 与 BGE 使用不同集合；切换模型后要显式重建。重建先 dry-run，实际重建会写向量。
- **资料修改：**当前元信息与手工笔记编辑会同步索引，失败有标记和重试；未来转写编辑仍须处理旧摘要与索引一致性。

## 6. 检索评测和已有质量证据

固定语料：`backend/evals/retrieval_zh.json`；原始报告：`backend/evals/baseline_local_hash.json`。

- 12 条虚构视频文本、15 道问题，14 道计入检索质量，1 道空知识库只查隔离。
- hash 维度 384，top-k=3；Hit rate=100%，Recall=96.43%，Precision=38.10%，MRR=1.00，跨用户违规为 0。
- `paraphrase-resume` 漏掉一个标准视频，原始失败保留。
- 语料很小、由项目编写且不是真实视频标签；这些分数不能证明真实中文问答达标。
- 评测使用独立内存 Chroma，不读取 PostgreSQL 或项目持久向量。默认 `passed=true` 仅表示隔离检查通过；设置 `--min-recall` 后才增加召回门槛。
- 当前工具测检索，不测生成回答。真实 BGE 已在虚构语料运行、ASR 已在单条公开自然语音视频运行；真实资料检索质量与最终回答准确性仍须完成 R1/R2。
- 2026-10-23 增加 NASA 英文公开视频真实文本与人工问题：top-k=2 的 BGE Recall 为 72.73%，三道阿波罗题漏检；分段/候选对照没有改善召回。原始报告与限制见 [评测文档](docs/RETRIEVAL_EVALUATION.md)，不能推断中文资料或最终回答达标。

完整定义和命令见 [评测文档](docs/RETRIEVAL_EVALUATION.md)。

## 7. 本机环境与恢复步骤

以下是最后运行记录，开始新聊天仍应实际核对；Git 不包含这些服务或数据。

- 前端本地预览：`http://localhost:3000`，知识库 `/library`，模型设置 `/settings`。
- 本机 VideoMind API 使用 `http://localhost:8001`，容器内部后端仍为 8000；此前宿主 8000 被另一项目占用。
- Docker 实际使用 Colima socket：`unix:///Users/chenxin/.colima/default/docker.sock`。默认 Docker Desktop socket 不存在不代表项目停机。
- 后端/前端/PostgreSQL/Worker 容器分别为 `videomind-backend`、`videomind-frontend`、`videomind-postgres`、`videomind-worker`。
- 2026-10-21 本机实测 Alembic 版本为 `20261021_0007 (head)`；新环境要核对实际版本并迁移，不盲目 stamp。
- 之前为 demo 认证、embedded Chroma、local_hash、ASR disabled。实际值只在授权环境检查，不把 `.env` 整份输出。
- `storage/model-cache/` 映射模型缓存并已加入 Git 忽略；2026-10-22 两个模型已在独立验证镜像中下载，可选依赖仍未安装到默认运行容器。

### 只读恢复命令

```bash
cd '/Users/chenxin/Documents/Codex 2/videomind-ai'
git status --short --branch
git log -6 --oneline
git diff --check
export DOCKER_HOST=unix:///Users/chenxin/.colima/default/docker.sock
docker compose ps
curl --max-time 5 http://localhost:8001/api/v1/health/ready
```

readiness 应包含 `service=VideoMind AI`；必要时检查 `/openapi.json` 有视频路由，避免测试到另一应用。服务停机时先查日志和挂载，不删除数据库或数据卷。

视频处理现在需要独立 Worker。现有后端镜像可通过 `docker compose --profile app up -d --no-deps worker` 启动 Worker；从零启动时使用 `docker compose --profile app up -d --build`。检查 `docker compose logs --tail=50 worker` 和视频详情里的任务状态。API 接受任务只代表已入队，Worker 未运行时任务会保留 queued。

### 后端验证

```bash
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend ruff check app tests scripts
docker compose exec -T backend alembic current
docker compose exec -T backend python -m scripts.evaluate_retrieval
```

向量重建预检查：

```bash
docker compose exec -T backend python -m scripts.reindex_vectors --dry-run
```

它支持 `--user-id` 和 `--limit`。重复运行同一 limit 仍从首条开始；并非带检查点的任务恢复。去掉 dry-run 才会写入向量。

### 前端验证

宿主机之前没有可用的 tsc/eslint，依赖在前端容器里。不要直接在正在预览的 `/app` 下运行生产构建，避免覆盖其 `.next`。可在容器内建立临时副本：

```bash
docker compose exec frontend sh
vm_check_dir=$(mktemp -d /tmp/videomind-check.XXXXXX)
cp -R app components lib public package.json package-lock.json tsconfig.json next-env.d.ts next.config.ts postcss.config.js tailwind.config.ts eslint.config.mjs proxy.ts "$vm_check_dir"/
ln -s /app/node_modules "$vm_check_dir/node_modules"
cd "$vm_check_dir"
npm run build
npm run typecheck
npm run lint
exit
```

构建会生成类型文件，因此先 build 再独立 typecheck。该副本不自动包含 `storage/` 和密钥。复制失败时先核对现有布局，不静默跳过文件。

## 8. 已遇到的问题

1. **端口串项目：**宿主 8000 曾指向其他服务，VideoMind 目前用 8001；前端浏览器地址和 API_PORT 必须对应，容器内部地址仍为 backend:8000。
2. **挂载或热更新失效：**旧容器曾出现空 `/app`，也曾未加载新代码。先对比容器源码与在线响应；确需重启前确认没有活跃视频任务。
3. **生产镜像重建：**之前受 apt 软件包下载影响，没有重新证明当前默认镜像可从零构建；2026-10-22 独立可选模型镜像已构建并验证，但不代表当前默认部署镜像可从零构建或启用了本地 AI。属于 R9 未验收项。
4. **生成文件变动：**开发服务器可能改写 `frontend/next-env.d.ts` 的 dev 类型路径，提交前核对来源，不混入无关改动。
5. **依赖提示：**检索评测出现 Chroma 遥测签名兼容性提示和 ONNX CPU 提示；评测完成。pytest 有 LangGraph 待弃用提示。不要为消除提示擅自大范围升级依赖。
6. **未验收不是需要重写：**认证/BYOK/ASR/BGE 已有实现，缺真实账号或模型测试时应补验收，不从零做第二套。
7. **下载凭证：**Bilibili 等平台可能要求 Cookie。只能在用户授权环境使用，不提交到 Git，不把公共样例的失败推断成核心业务已坏。

## 9. 最近功能提交与证据

| 提交 | 内容 | 证据 |
| --- | --- | --- |
| `064b1b7` | 中文检索评测、基线与工时范围 | `docs/VERIFICATION_2026-10-16.md`，后端 62 项 |
| `6fce45f` | 分页、AI 摘要搜索和全库分类 | `docs/VERIFICATION_2026-10-15.md`，后端 52 项与前端检查 |
| `d3637fd` | 向量重建预检查、用户筛选与失败续跑 | `docs/VERIFICATION_2026-10-14.md` |
| `467c61e` | WebVTT 分钟时间戳修复 | 对应字幕测试与 Git diff |
| `8e03e73` | 可选本地 AI、索引安全更新和任务中断标记 | `docs/VERIFICATION_2026-10-12.md`、`docs/VERIFICATION_2026-10-13.md` |

早期 16/29/41 项测试和“未提交”描述是历史记录，不能覆盖最新事实。2026-10-21 的实现与验证见 [核查记录](docs/VERIFICATION_2026-10-21.md)。

## 10. 新聊天的第一轮工作

1. 确认是否能访问真实仓库；若只有 ChatGPT 项目镜像，`sources/` 只读，不在那里修改业务代码。
2. 读仓库 `AGENTS.md`、本文件、剩余计划和当前 Git；先保护任何后来出现的用户改动。
3. 用简短中文报告当前状态、下一项 R 编号和验收方法，再继续实现。
4. 优先补 R1/R3 的更多真实语音、人工标签、分段与引用质量，再检查 R5 真实媒体任务/多实例故障边界；缺少账号时继续不依赖账号的工作。已有 NASA 公开样例证据，不要把它误算成付费服务或完整问答验收。
5. 完成后运行适当检查，更新有日期证据和任务状态；若当前用户授权同步，再核对远端、提交和推送，不能 force push。
6. 不能访问仓库时，使用本文件和剩余计划恢复背景，但明确说明未检查代码，不虚构测试或部署成功。

需要用户参与的是账号开通、资源/费用选择、本人验证、真实计费确认及必要的私人素材授权；代码实现、模拟测试、公开样例、本地模型、文档和排障应继续自主推进。
