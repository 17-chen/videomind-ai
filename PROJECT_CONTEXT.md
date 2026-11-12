# 项目上下文

2026-11-12：功能 `e67de3f` 已同步 GitHub，[CI 43165117133](https://github.com/17-chen/videomind-ai/actions/runs/43165117133) 前后端及固定检索检查全部通过。快进保留远端17d53b8问答元信息修复；R5/R8 音频提取增加约0.5秒的在途磁盘余量检查，失败/超时先终止并回收 ffmpeg 再清理本次暂存，保留旧文件和无关目录。17项针对性及全量397项后端测试/Ruff通过，含真实 ffmpeg 故障/重试，ASR为模拟。云队列空闲后重载API/Worker，未重跑视频或调用模型；空间预留、下载合并、真实双账号/恢复仍待验收。见 [本轮核查](docs/VERIFICATION_2026-11-12.md)。

2026-11-11：问答候选通过业务库归属核验后，来源标题、链接和分类也取业务库当前值，避免沿用过期索引元信息；片段仍取索引。11 项来源测试与 Ruff 在隔离只读容器通过；未调用付费模型或更新云预览，真实引用质量待验收。

2026-11-10 恢复推进：最终功能 `0a2b93c` 已同步 GitHub，[CI 42838499156](https://github.com/17-chen/videomind-ai/actions/runs/42838499156) 前后端及固定检索检查全部通过。新增只读数据库恢复比对命令，覆盖8张业务表及5张可选迁移/向量/对象表的选定结构与内容；拒绝自身比较和 RLS 过滤视图，预算不足不判匹配。394 项后端测试/Ruff 通过；一次性 PostgreSQL 16 实际 pg_dump/pg_restore 的合成13表匹配、合成密文可解、同数量正文改变可检出。真实 Supabase 17、用户主密钥与对象文件恢复仍未验收；未操作真实备份或付费模型。见 [恢复核查](docs/VERIFICATION_2026-11-10_RESTORE.md) 与 [比对说明](docs/RESTORE_VERIFICATION.md)。

2026-11-10：功能 `d1dd39c` 已同步 GitHub，[CI 42744791214](https://github.com/17-chen/videomind-ai/actions/runs/42744791214) 前后端及固定检索检查通过。R8 新增只读运营阈值命令 check_operations，覆盖排队过久、过期租约、近期失败及本地低磁盘余量，提供 0/1/2 退出码和脱敏 JSON；读取失败不伪装健康。380 项后端测试/Ruff 通过，API/Worker 各自只读实测为 ok；未重启服务、重跑视频或调用模型。生产调度/通知、空间预留、真实双账号和完整恢复仍待做。见 [本轮核查](docs/VERIFICATION_2026-11-10.md) 与 [监控说明](docs/OPERATIONS_MONITORING.md)。

2026-11-09：功能提交 `6d7986e` 已同步 GitHub，[CI 42555093216](https://github.com/17-chen/videomind-ai/actions/runs/42555093216) 前后端及固定检索检查通过。推进 R2/R7 问答来源保护。生成前按业务库复核候选 Video 的本人归属和存在性，过滤重复/空正文；无有效资料不调用模型，SQL 失败不信任索引回退。上下文与来源卡片统一 [1] 编号。369 项后端测试/Ruff、12 项前端回归及隔离 build/typecheck/lint 通过；3001 来源卡片与云 API 已更新，未调用真实模型或重跑视频。真实引用质量、双账号、全程自动更新与恢复仍待验收。见 [本轮核查](docs/VERIFICATION_2026-11-09.md)。

2026-11-08 验收推进：修复入队响应及任务/视频快照错位时按钮提前解锁，补逐阶段轮询/错误重试/卸载与问答引用渲染回归。12 项前端测试、隔离 build/typecheck/lint；一次性 PostgreSQL 下 359 项后端测试/Ruff 通过，已同步 3001 单个组件。真实页面可见已有笔记，云队列活动/失败/过期均 0；现有 1 条用户密文以当前主密钥校验 verified，不等于备份恢复。未重复处理视频或调用模型；第二账号尚未准备，真实全过程自动更新、问答引用质量、双账号和隔离恢复仍待验收。见 [本轮核查](docs/VERIFICATION_2026-11-08_ACCEPTANCE.md)。

2026-11-08 最终交接：`37efbf9` 的 CI 42459704977 前后端通过。用户确认注册登录、登录跳转/完成状态正常，并报告已生成内容；全程无需手动刷新的内容更新仍待浏览器复核。当前使用 3001/8002 云预览、本地 Whisper base + 本人 DeepSeek、云 pgvector/local_hash；原 3000/8001 为旧演示。优先看 [交接当前摘要](PROJECT_HANDOFF.md)，不要把单次生成或组件模拟测试当成双用户/完整模型验收。

2026-11-08 界面修复：登录成功改为持久化会话后的完整文档跳转，避免复用登录前导航；日期显式 Asia/Shanghai，消除服务端 UTC 与浏览器时区的 hydration 差异；视频操作直接按本人接口刷新视频/任务，终态停止轮询并恢复按钮，completed 阶段补中英文。7 项前端测试与隔离 build/typecheck/lint 通过；已更新 3001，用户明确反馈登录和完成状态两项均正常。后台成功任务实际耗时约 111 秒，不是持续转写；未证明 ASR 计算加速或完整模型链验收。见 [核查](docs/VERIFICATION_2026-11-08_UI.md)。

2026-11-08 转写运行修复：排查发现用户停留在 3000 旧演示页面；独立云预览仍为 3001/8002。云预览 API/Worker 已启用本地 Whisper base（CPU/int8），DeepSeek 仍由各用户本人配置用于笔记/问答，无需 OpenAI 转写 Key。已复用本地 AI 镜像，在非文稿同步私有目录建立新模型缓存；原缓存读取超时，保留未覆盖。真实 Worker 离线模型加载、合成静音解码、HTTP ready=200 及 10 项相关隔离测试通过。未自动重跑真实视频或调用付费模型，真实内容质量与端到端仍未验收，见 [记录](docs/VERIFICATION_2026-11-08_LOCAL_ASR.md)。

2026-11-08 运行补充：用户授权 Colima 4GB 扩容后，独立云预览前端 3001/API 8002/Worker 已运行；真实 HTTP ready=200、匿名 videos=401、云队列 queued/running/failed/expired=0，原本地 3000/8001 已恢复。Site URL=3001。功能 `57c0794` 的 CI 42452665353 前后端通过；双账号/本人模型仍未验收，见 [接入记录](docs/VERIFICATION_2026-11-08_SUPABASE.md)。

> 最后核对：2026-11-12。优先以仓库代码、Git 状态和本次实测为准；不记录真实密钥。完整文档索引见 [项目资料入口](docs/PROJECT_MATERIALS.md)。

**文档入口更新（2026-10-27）：**默认 `README.md` 为英文首页，`README.zh-CN.md` 为对应中文首页；原 README 保存在 `docs/archive/README.before-bilingual.zh-CN.md`，仅作历史参考。此次只修改文档，功能和真实服务验收状态未因此改变。

## 项目基本信息

- **名称：**VideoMind AI。
- **目标：**把收藏但没时间看的视频转成结构化笔记、可检索知识库和可追溯来源的问答。
- **实际代码仓库：**`/Users/chenxin/Documents/Codex 2/videomind-ai`，Git remote `git@github.com:17-chen/videomind-ai.git`。
- **目标用户：**学习者、内容创作者和管理视频资料的知识工作者。

## 当前阶段

Phase 1–6 已有基础实现；当前处于真实云预览验收和上线保护收尾。Supabase Auth/PostgreSQL/私有 Storage/pgvector 基础已接通，3001/8002 使用本地 Whisper 与本人 DeepSeek。单账号登录与生成内容已有用户确认；完整问答质量、双用户、恢复和正式部署未验收，不能视为正式多用户 SaaS。

**Git 快照：**2026-10-27 交接文档整理前已快进到 GitHub 的 `41d743d` 中英文 README 提交；恢复预检功能为 `1242761`，后续记录 CI 的提交为 `5b19d36`。原有未跟踪 `outputs/` 保留不动。交接文档提交后以实际 Git 状态为准，不复用这个快照判断未来工作树。

**按原完成计划的进度：**R3 上传、R4 编辑的本地代码和检查已完成；R1 真实本地模型/R5 持久任务/R8 配额日志与密钥预检均有部分真实证据，但整项未完成；R2 的本人服务商分析→入库→问答、R7 真实 Supabase 双用户、R6 云端数据库/向量/对象存储和 R9 目标平台发布均未验收。细分任务及可自主推进顺序见 [剩余计划](docs/COMPLETION_PLAN.md)。模拟服务与虚构语料只证明对应测试范围。

**交接补充：**检索评测已随 `064b1b7` 推送；随后将 `PROJECT_HANDOFF.md` 重整为完整当前快照，`docs/COMPLETION_PLAN.md` 补充 R1–R9 的验收与依赖。新聊天先从仓库 `AGENTS.md` 和 [恢复说明](docs/NEW_CHAT_START.md) 进入，不依赖旧聊天自动继承。

## 技术架构

- 前端：Next.js 16.4.3、React 19、TypeScript、Tailwind CSS。
- 后端：Python 3.12、FastAPI、SQLAlchemy、Alembic、LangGraph。
- 数据：PostgreSQL 保存用户、视频、转写、摘要和向量映射；本地目录保存视频、音频和笔记。
- 视频：yt-dlp 下载、字幕优先，缺字幕时抽取音频；默认 `ASR_PROVIDER=disabled`，可选安装本地 faster-whisper 或使用用户的 OpenAI 转写 Key。
- AI：DeepSeek 默认用于分析和回答；默认 `local_hash` embedding + ChromaDB 提供基础 RAG 流程，新增可选共享 pgvector 后端，可选本地中文 BGE 模型与分段索引。
- 认证：默认 demo user；可选 Supabase 注册登录和后端令牌验证已实现，当前独立云预览使用 Supabase；真实双用户验收待完成。
- 本地编排：Docker Compose 默认启动 PostgreSQL、Adminer、backend、frontend；Chroma 使用后端嵌入式持久化，独立服务是可选 profile。

详见 [当前架构](docs/architecture.md)。

## 验证状态

**2026-11-08 云端补充：**独立 Supabase 测试项目已完成真实 PostgreSQL 17 verify-full 连接、迁移前归档/目录检查、空库三组迁移和后端专用表权限配置；真实私有桶合成文件上传/摘要/精确删除通过，修复 HTTP 400 包装 NoSuchKey 的兼容性问题。359 项后端测试/Ruff 通过。既有本地预览未切换；双账号、本人模型链、恢复与部署仍待验收。见 [核查](docs/VERIFICATION_2026-11-08_SUPABASE.md)。

**2026-11-08 补充：**功能提交 `c98aad2` 已同步，[CI 42444875044](https://github.com/17-chen/videomind-ai/actions/runs/42444875044) 前后端均通过；后续补 PostgreSQL 聚合 JSON 类型修复，343 项本地全量复测通过。R6/R8 新增对象账本只读汇总与显式远端摘要核查；分批/字节预算、并发变化检测和脱敏输出已验证，始终不修改状态、释放额度或删除对象。343 项后端测试/Ruff、前端隔离 build/typecheck/lint 及 4 项保护用例通过；真实 PostgreSQL 与本地 HTTP，云响应仍为模拟。本机默认只读检查返回 not_installed，环境未切换；安全解决 pending、旧文件迁移和真实云验收仍待做。见 [核查](docs/VERIFICATION_2026-11-08.md)。

**2026-11-07 补充：**功能提交 `dfdc41c` 已同步 GitHub，[CI 42345630901](https://github.com/17-chen/videomind-ai/actions/runs/42345630901) 后端与前端均通过。R6 上传 API、笔记编辑与持久 Worker 已统一接入可选文件后端；上传先持久预留来源/总量配额，确认后才原子发布 Video。新增可选迁移 `20261107_o003`，默认 `FILE_STORAGE_BACKEND=local`，未切换现有环境。316 项后端测试/Ruff、前端 4 项保护用例及隔离 build/typecheck/lint 通过；真实 PostgreSQL/ffmpeg，身份、Supabase、ASR、LLM 和向量写入使用测试替身。旧文件迁移、pending 结果对账、真实双用户与云端持久性仍未验收。见 [核查](docs/VERIFICATION_2026-11-07.md)。

**2026-11-06 补充：**功能提交 `df1f8b2` 已同步 GitHub，[CI 42197987551](https://github.com/17-chen/videomind-ai/actions/runs/42197987551) 后端与前端均通过。R6 处理/分析/笔记编辑服务可显式注入对象客户端，已支持成组发布、按用户私有落地、对象 ID 引用及正文/引用与账本同事务提交；禁止本地/对象混用以防配额漏算。293 项后端测试/Ruff、前端隔离检查通过，含真实 PostgreSQL 并发/回滚和真实 ffmpeg；Supabase、ASR 与 LLM 响应为模拟。上传 API、持久 Worker 后端选择、迁移与真实云端验收仍待做，默认运行未切换。见 [说明](docs/OBJECT_STORAGE.md) 和 [核查](docs/VERIFICATION_2026-11-06.md)。

**2026-11-05 补充：**功能提交 `b8134aa` 已同步 GitHub，[CI 42004927480](https://github.com/17-chen/videomind-ai/actions/runs/42004927480) 后端与前端均通过。R6/R8 接通视频删除与对象清理意图：删除意图和业务记录同事务提交，显式维护命令默认只读，已确认对象可按精确键重试；pending 上传结果不明时保留。267 项后端测试/Ruff 通过，含真实 PostgreSQL 删除/上传与维护并发、SQL 故障回滚；身份、向量和 Supabase 响应仍为模拟。上传/Worker/编辑读取尚未接入，不代表完整云端存储或真实验收。见 [说明](docs/OBJECT_STORAGE.md) 和 [核查](docs/VERIFICATION_2026-11-05.md)。

**2026-11-04 补充：**功能提交 `b04ac37` 已同步 GitHub，[CI 41835276579](https://github.com/17-chen/videomind-ai/actions/runs/41835276579) 后端与前端均通过。R6 新增私有对象传输与版本账本基础：不可变键、摘要校验、用户归属、失败保留旧版和独立显式迁移；业务上传/Worker/编辑读取/删除尚未接入，当前仍用本地文件。244 项后端测试及 Ruff 通过，含真实本地 HTTP 和一次性 PostgreSQL 并发；Supabase 响应/身份仍是模拟，云端验收未完成。见 [对象基础说明](docs/OBJECT_STORAGE.md) 与 [本轮核查](docs/VERIFICATION_2026-11-04.md)。

**2026-11-03 补充：**功能提交 `f3ba87e` 已同步 GitHub，[CI 41614700666](https://github.com/17-chen/videomind-ai/actions/runs/41614700666) 后端与前端均通过。R6 新增可选 PostgreSQL/pgvector 共享向量后端，默认仍为 Chroma。独立显式迁移、按用户/模型隔离、分段去重、事务替换和跨模型删除已有本地真实 SQL 证据；未切换现有环境。后端 204 项测试/Ruff、前端 4 项保护用例及隔离 build/typecheck/lint 通过。真实 PostgreSQL/pgvector 不等于真实 Supabase 验收，BGE 分段用模拟向量；媒体对象存储、云端角色/持久性与真实模型闭环仍待做。见 [pgvector 说明](docs/PGVECTOR.md) 和 [本轮核查](docs/VERIFICATION_2026-11-03.md)。

**2026-11-02 补充：**功能提交 `28fcc6f` 已同步 GitHub，[CI 41428541351](https://github.com/17-chen/videomind-ai/actions/runs/41428541351) 后端与前端均通过。R9 新增只读部署配置预检、前端 Vercel 构建保护和无凭证环境模板。后端 180 项测试/Ruff，前端 4 项部署保护用例及临时副本 build:deploy/typecheck/lint 通过；构建使用虚构配置，不代表真实服务验收。本机预检按预期返回 blocked，未修改当前环境。当前可准备受保护预发布，公开使用前须完成真实双用户、本人模型闭环和共享持久存储；Render 磁盘不能跨服务共享，现有 API/Worker 不能直接拆成两块独立盘。见 [部署时机](docs/DEPLOYMENT_READINESS.md) 与 [本轮核查](docs/VERIFICATION_2026-11-02.md)。

**2026-11-01 补充：**功能提交 `fe52987` 已同步 GitHub，[CI 41295419944](https://github.com/17-chen/videomind-ai/actions/runs/41295419944) 后端与前端均通过。R5/R8 新增 Linux 音频进程随 Worker 退出保护；真实 ffmpeg 在 SIGKILL/SIGTERM 后停止，超时清理与过期租约重试通过。队列使用隔离 SQLite，ASR 返回为模拟，未访问外部服务。后端 146 项测试/Ruff、前端临时副本 build/typecheck/lint 通过，见 [本轮核查](docs/VERIFICATION_2026-11-01.md)。遗留暂存文件不自动删除，下载合并子进程和长期多实例仍待验收。

**2026-10-31 补充：**功能提交 `72db8ce` 已同步 GitHub，[CI 41192394623](https://github.com/17-chen/videomind-ai/actions/runs/41192394623) 后端与前端均通过。R8 增加临时阶段容量 2048 MB、余量阈值 1024 MB、上传流/下载检查点/文本写入检查；音频使用独立子进程内核单文件限制，超限不发布截断结果。无特权用户 141 项测试/Ruff、前端隔离检查通过，含真实本地 HTTP/ffmpeg/资源上限检查；模拟低空间不计真实服务验收。配置和剩余的并发/合并预留边界见 [说明](docs/TEMPORARY_STORAGE.md) 与 [核查](docs/VERIFICATION_2026-10-31.md)。

**2026-10-30 补充：**功能提交 `99adac4` 已同步 GitHub，[CI 41034408189](https://github.com/17-chen/videomind-ai/actions/runs/41034408189) 后端与前端均通过。本机开发前端已实际切换 Next.js 16.4.3；增加锁文件/直接依赖启动校验，保留旧卷，预览四页 HTTP 200。R8 新增 `storage_status` 只读元数据对账，实际扫描完整、活动任务 0、9 个未归属文件全部保留；没有执行清理。后端无特权用户 124 项测试/Ruff，前端隔离 build/typecheck/lint 通过。见 [核查](docs/VERIFICATION_2026-10-30.md)、[磁盘说明](docs/STORAGE_MONITORING.md) 和 [前端开发说明](docs/FRONTEND_DEVELOPMENT.md)。

**2026-10-29 补充：**功能 `1751e77` 和测试隔离修复 `290cb47` 已同步 GitHub，[CI 40874438964](https://github.com/17-chen/videomind-ai/actions/runs/40874438964) 后端与前端均通过。首次 CI 暴露测试目录权限依赖，已补逐测试隔离并以无特权用户验证；空队列后重启本机 API/Worker，在线新策略可读。后续出现的未跟踪 `backend/:memory:.ses` 来源未确认，保留且不提交。后端全量 118 项测试（含两个真实 PostgreSQL 并发用例）及 Ruff 通过。R8 本地正式文件总量默认 10240 MB，上传、URL 下载/字幕、音频、转写和 Markdown 共用同一用户行锁核算；分阶段暂存，超限保留旧内容，等大替换/缩小允许。真实 PostgreSQL 双会话和自生成媒体的真实 ffmpeg/ffprobe 检查通过，ASR/分析模拟；前端当前锁文件匹配的 16.4.3 临时副本 build/typecheck/lint 通过。详见 [配额说明](docs/STORAGE_QUOTA.md) 与 [核查](docs/VERIFICATION_2026-10-29.md)。临时空间、孤立文件和云端持久性未覆盖。

**2026-10-28 补充：**功能提交 `b192c78` 已同步 GitHub，[CI 40631839773](https://github.com/17-chen/videomind-ai/actions/runs/40631839773) 后端与前端均通过。R8 增加认证前的来源/进程总请求限制，默认每分钟 300/3000 次；拒绝在读取正文、认证与数据库调用之前发生，返回 429、Retry-After 和请求编号。内存来源表有上限；Compose/Dockerfile 禁用代理头信任，代理后会共享来源额度。后端 102 项测试及 Ruff 通过；当前锁文件匹配的 Next.js 16.4.3 临时副本 build/typecheck/lint 通过。详见 [限流说明](docs/INGRESS_LIMITS.md) 和 [核查记录](docs/VERIFICATION_2026-10-28.md)。这是单进程保护，多实例统一计数、存储总量和真实外部服务仍待验收。

**2026-10-27 补充：**新增只读用户密钥恢复预检，合成密文测试覆盖模型和 ASR Key、错误密钥、空库与私有文件权限。后端 96 项测试及 Ruff 通过。本机 PostgreSQL 没有已保存的用户密文，返回 `inconclusive`，无法证明真实备份主密钥可恢复；当前主密钥及数据库均未修改。数据库、业务文件、Chroma 和主密钥的备份/隔离恢复步骤见 [恢复手册](docs/RECOVERY_RUNBOOK.md)，本轮证据见 [核查记录](docs/VERIFICATION_2026-10-27.md)。

**2026-10-26 补充：**API 视频任务入队日志现在关联请求编号与任务 ID；Worker 对领取、阶段、恢复和终态记录同一任务 ID。新增只读队列快照命令统计状态、最老排队时长、过期租约和最近一小时失败数。后端 94 项测试、Ruff 通过；命令在本机运行中的 PostgreSQL 上返回空队列及 0 个过期租约。未部署生产日志汇聚或告警，详见 [核查记录](docs/VERIFICATION_2026-10-26.md)。

**2026-10-25 补充：**新增 API 请求编号和脱敏路由日志，关闭新启动实例的 Uvicorn 原始访问日志与 Loguru 局部变量诊断。后端 92 项测试及 Ruff 通过；前端升级 Next.js 16.4.3 后生产镜像、HTTP 页面烟测、typecheck/lint 通过。npm 审计已无 high/critical，Tailwind 3 构建链仍有 4 项 moderate。当前后端默认镜像改用 Debian 官方 HTTPS 源，在 Colima 从源码构建成功，独立镜像应用导入、媒体工具与 `pip check` 通过；云平台仍待验收。详见 [核查记录](docs/VERIFICATION_2026-10-25.md)。

**2026-10-24 补充：**问答及视频任务请求新增 PostgreSQL 持久的每用户 60 秒窗口限流，默认分别 20 次、10 次，超限 429；重复任务请求也计数，使用用户行锁保证跨 API 会话串行判断。一次性 PostgreSQL 双会话同时请求验证两类操作均一成功一拒绝。本机现有数据库在已忽略目录备份后迁移至 `20261024_0008`，readiness 正常。后端 88 项测试及 Ruff 通过；用户存储总量、匿名流量、长期负载和真实 Supabase/付费服务尚未验收。详见 [核查记录](docs/VERIFICATION_2026-10-24.md)。

**2026-10-23 后续补充：**按用户限制 `queued` 与 `running` 视频任务合计，默认最多 2 个；上限检查前锁定用户行，超限 429，同视频重复仍为 409。一次性 PostgreSQL 双会话并发入队验证一成功一拒绝，取消后释放名额。模拟向量写入失败后的持久 `run` 重试仅再次入库，不重复转写或分析。后端 84 项测试及 Ruff 通过；真实服务商、用户存储总量和请求频率限制仍未验收。证据见 [同日核查记录](docs/VERIFICATION_2026-10-23.md)。

**2026-10-23 补充：**一次性 PostgreSQL 与独立本地 AI Worker 完成真实 NASA URL 下载和持久任务转写，任务最终成功；这不是分析、入库或问答的验收。新增 3 条 NASA 英文公开视频文本及 12 道人工题，在独立内存 Chroma 对照 hash 和 4 组真实 BGE 参数；最佳 BGE Recall@2 仍仅 72.73%，三道阿波罗题漏检。后端 82 项测试、Ruff 和前端隔离副本 build/typecheck/lint 通过。中文自然语音、生成回答、真实 Supabase 和付费服务仍待验收。详见 [核查记录](docs/VERIFICATION_2026-10-23.md) 与 [评测文档](docs/RETRIEVAL_EVALUATION.md)。

**2026-10-22 补充：**在独立验证镜像中安装可选本地 AI 依赖，修复 PyAV 19 与 faster-whisper、较新 tokenizers 与 ChromaDB 的真实兼容冲突，`pip check` 通过。真实 faster-whisper base 用 CPU int8 转写 8.24 秒合成中文语音及 NASA 56 秒真实公开视频；后者的 URL 下载、上传来源处理和无字幕缺 Key 失败路径在一次性 PostgreSQL 中通过，识别结果仍有错词。真实 BGE 在固定虚构语料上 Recall@3 100%、跨用户违规 0。模型缓存位于已忽略的 `storage/model-cache/`；默认 API/Worker 未切换到本地 AI。真实笔记/问答、Supabase 与付费模型仍未验收。见 [核查记录](docs/VERIFICATION_2026-10-22.md)。

**2026-10-21 补充：**R5 本地持久任务基础已实现：PostgreSQL 入队、独立 Worker、租约恢复、按阶段取消和本人任务接口。后续加固了旧 Worker 失去所有权后的阶段与终态写入。后端 75 项测试/Ruff、前端临时副本 build/typecheck/lint 通过；本机迁移至 `20261021_0007`，API 重启后任务保留、真实 Worker 完成合成资料入库、PostgreSQL 双 Worker 竞争、取消恢复与清理通过。另以受控阻塞阶段运行实际执行进程 96 秒，验证租约心跳后 SIGKILL，任务重新领取完成。真实媒体、付费服务、Supabase 用户和多实例长期运行仍未验收，R5 整项未完成。见 [核查记录](docs/VERIFICATION_2026-10-21.md)。

**2026-10-20 补充：**R4 本人资料与手工笔记编辑已实现；分类参与列表和索引，已入库视频编辑自动尝试同步，失败保留旧向量并标记可重试。后端 69 项测试、Ruff、前端隔离构建/typecheck/lint 通过；本地迁移至 `20261020_0006`，实际运行 API 的创建、编辑、分类筛选和清理通过。真实模型、Supabase 双用户和多实例一致性未验收。详见 [核查记录](docs/VERIFICATION_2026-10-20.md)。


**2026-10-19 补充：**R3 本地视频上传入口、文件验证、按用户重复保护和处理路径已实现。自生成短视频经运行中 API 上传、重复拒绝、详情和删除清理通过；模拟转写、笔记、入库工作流通过，66 项后端测试/Ruff 和前端 build/typecheck/lint 通过。本机 PostgreSQL 迁移至 `20261019_0005` 前已在不入 Git 的 `storage/backups/` 保存备份。真实 ASR、用户模型与 Supabase 双用户验收仍缺；详情见 [核查记录](docs/VERIFICATION_2026-10-19.md)。

**2026-10-18 补充：**先快进合入 GitHub 的 `700ccde` 字幕选择修复，随后添加推送与 PR 自动检查，覆盖后端测试/Ruff/固定 hash 检索和前端构建/typecheck/lint。本地后端 63 项通过，Ruff 通过，虚构语料 Recall@3 为 96.43%、隔离违规 0；前端临时副本的 build/typecheck/lint 通过。远端首次运行暴露 PostgreSQL 服务缺失；修复后的 [GitHub CI](https://github.com/17-chen/videomind-ai/actions/runs/39103657908) 两个任务均通过，详见 [本轮核查](docs/VERIFICATION_2026-10-18.md)。R1 真实本地模型依赖尚未安装，真实音频、BGE、外部服务仍未验收。

**当前验证（2026-10-16）：**后端 62 项测试和 Ruff 通过；12 条虚构文本、15 道问题的真实 hash + 内存 Chroma 评测完成，Recall@3 为 96.43%，隔离违规为 0。漏检与小样本边界见 [检索评测](docs/RETRIEVAL_EVALUATION.md)。本轮未改前端，最近一次前端构建与页面检查为 2026-10-15，详见 [上轮核查](docs/VERIFICATION_2026-10-15.md)。

**历史验证（2026-10-08）：**隔离副本前端 typecheck、lint、生产构建通过；实际 Python 3.12 后端容器中 16 项测试通过，Alembic 位于 `20260904_0002 (head)`。最初前端超时是旧容器的 bind mount 为空；重新创建前后端无状态容器后，主要页面和 readiness 返回 200。临时 Supabase 配置下未登录访问受保护页面会跳转到 `/auth`；真实登录未验证。

**此前记录（2026-09-04）：**前端 typecheck、lint、build 通过；后端 9 项测试通过；更早的全新 PostgreSQL Alembic 迁移和生产 Docker 镜像曾通过验证。这些是历史结果，需要在当前环境复验。

## 已知风险与缺口

- 当前 `.env` 未设置 Supabase 配置，`AUTH_MODE` 使用默认 demo。真实注册/登录及用户隔离未验收。
- 尚无有字幕真实 URL 的完整创建 → 转写 → 分析 → 向量写入 → 问答验收记录。
- 无字幕视频在默认 ASR 关闭时需要用户转写 Key；可选本地模型已在一个英文真实视频上完成转写，独立 Worker 也完成该视频的持久任务，但中文自然语音和笔记链路待验。BGE 的小型英文真实资料对照仍漏三道阿波罗题，不能代表中文语义质量。
- 视频处理已有本地 PostgreSQL 持久任务和独立 Worker，受控长任务进程中断/心跳及用户入队上限的 PostgreSQL 双会话竞争已验；真实媒体运行中故障、付费调用与多实例长期运行未验，本地文件和 Chroma 尚无生产存储方案。
- 视频下载受平台策略、Cookie、网络、yt-dlp 和 ffmpeg 环境影响。
- 前端容器挂载为空的问题已通过重新创建容器恢复；如果复发，先检查 Colima Docker socket、bind mount 和容器日志。
- `docs/api.md`、`docs/project-plan.md`、`docs/deployment-audit.md`、`docs/self-review.md` 包含历史阶段陈述，读取时需与当前架构和路线图核对。

## 下一步

1. 扩充中文自然语音和跨主题资料，保留本轮英文样本失败题，核对真实回答引用；不要以小样本直接确定质量阈值。
2. R8 上传及下载/生成正式文件总量已有上限；继续临时处理空间、孤立文件对账/清理和生产统一流量限制（本地认证前限制已实现），并完成 R5 真实媒体任务的进程故障边界和多实例长期运行演练；付费步骤只在本人服务商可用后验收。
3. 配置真实 Supabase 测试项目后，完成注册、登录、会话刷新和双用户隔离验收；此前继续完成不依赖账号的实现。
4. 确认作品集上线方案，逐步配置 Vercel、Render、Supabase 和存储。

具体里程碑见 [阶段路线图](docs/roadmap.md)，任务见 [TODO](TODO.md)。

原始总工作量与剩余范围见 [完成计划](docs/COMPLETION_PLAN.md)：2026-10-16 曾估算小规模多用户版本累计 50–80 小时、本地版 16–26 小时；其中部分工作现已完成，数字不能当作 2026-10-27 的剩余工时。真实联调和云端适配的剩余工时待重新估算。

## 2026-10-08 补充：双语与用户密钥

- 前端增加中文默认、英文切换、`/settings` 模型设置页；开发工具入口已隐藏。
- 后端增加 `ai_settings` 用户独立配置表，服务端 Fernet 加密密钥；DeepSeek/OpenAI 模型和可选 OpenAI 转写密钥按当前用户读取。Supabase 认证模式下不使用项目所有者的密钥作为回退。
- 本地 `.env` 已生成加密主密钥（本文不记录值），PostgreSQL 迁移到 `20261008_0004`。真实数据库中的设置保存、读取、删除已通过；本地演示账户的测试密钥已删除，且 demo 模式现已禁止保存个人密钥。真实 Supabase 登录与服务商扣费仍需外部配置及验收。

## 2026-10-08 补充：本地向量库

发现独立 Chroma 镜像未安装，原本地问答链路会在向量写入和检索时失败。现默认改为 Chroma PersistentClient，路径 `/app/storage/chroma` 映射到仓库 `storage/chroma/`；独立 HTTP 模式保留。容器内本地持久化写入/重开/检索烟测通过，`/api/v1/health/ready` 返回数据库与向量库均为 `ok`。这不等于真实视频和实际模型问答全链路已验收。

## 2026-10-08 补充：一键视频流程

视频详情现在可一键触发字幕、AI 分析、向量写入，且可在失败后复用已有的转写和笔记。请求按视频状态原子校验，拒绝并发重复启动。后端完整测试为 24 项通过，前端隔离副本的 typecheck、lint、build 通过。实际有字幕视频和真实模型调用仍未验收；后台任务在进程重启时不会自动恢复。

## 2026-10-09 补充：笔记操作与 API 级隔离验证

视频详情的 Markdown 笔记可复制或下载，处理入口可直接打开个人模型设置。新增模拟外部下载、模型和向量服务的 API 级测试，验证已认证用户从保存个人 Key 到一键入库、问答引用的闭环，以及另一用户无法读取视频或检索其内容；后端测试共 25 项通过。前端隔离副本 typecheck、lint、build 通过。真实 Supabase 项目、真实视频及服务商账单仍未验收。

## 2026-10-09 补充：视频删除

用户可从详情页删除自己的非处理中视频；后端先删除对应用户的 Chroma 文档，再删除 PostgreSQL 视频及关联内容，最后按生成的 ID 清理本地媒体、转写和笔记文件。向量删除失败会保留数据库记录以便重试；数据库提交失败可能留下暂时缺失的向量，后续可重新入库。后端 27 项测试与前端 typecheck、lint、build 通过。真实多实例和外部向量服务故障恢复仍待验收。

## 2026-10-11 补充：运行核查与修复

发现本机另一项目占用 `127.0.0.1:8000`，最初对该端口的健康和路由检查误指向别的应用。VideoMind 本地 `.env` 已调整为宿主机 8001（不提交），容器内部仍为 8000；重建后已核对 OpenAPI 视频路由和带 `service=VideoMind AI` 标识的就绪状态。真实本地视频创建/读取/删除、demo 设置限制、空知识库问答及七个前端页面通过冒烟；Alembic 为 `20261008_0004 (head)`。无字幕处理在提取音频前检查转写 Key；后端 29 项测试和全量 Ruff、前端 typecheck/lint/build 通过。真实 Supabase、视频下载和付费模型仍待验收，详见 [核查记录](docs/VERIFICATION_2026-10-11.md)。

## 2026-10-12 补充：不依赖外部验收的开发

加入可选本地 faster-whisper、中文 BGE 向量模型、长文档分段与按视频去重、跨旧新集合删除、显式重新入库脚本，以及本地单进程启动时解除中断任务状态。默认演示配置不自动安装大型模型。后端 38 项测试和 Ruff、前端 typecheck/lint/build 通过；Docker Compose 配置校验通过。真实模型下载、真实转写/语义质量、生产多实例队列和外部服务商仍未验收。启用方法见 [本地 AI 配置](docs/LOCAL_AI.md)。

## 2026-10-13 补充：索引安全更新与设置页检查

BGE 索引更新改为先写入新版本再清理旧分段；故障时保留旧版，搜索时扩展被同一视频占满的候选范围。设置接口新增非敏感 `asr_provider` 字段，前端按实际转写模式显示中英文说明。后端 41 项测试与 Ruff、前端 typecheck/lint/build 通过。开发容器需要重启才加载本轮最新代码；重启后在线设置响应、readiness 和设置页正常。仍未验收的外部依赖见 [本轮核查](docs/VERIFICATION_2026-10-13.md)。

## 2026-10-14 至 15 日更新

向量重建工具已支持只读预检查、用户筛选、扫描数量限制和单条失败后继续。知识库新增每页 20 条的分页，翻页保留筛选；搜索覆盖原始标题、描述、链接及 AI 标题与摘要，百分号和下划线按普通字符处理。分类接口按当前用户汇总整个视频库，视频排序增加 ID 以保证相同创建时间的分页顺序稳定。
