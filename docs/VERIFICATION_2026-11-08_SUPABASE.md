# 2026-11-08 Supabase 测试项目基础接入

## 范围与隔离

从 `b28c364` 继续。用户在控制台创建独立测试项目并将数据库密码填入本机私有文件后，本轮完成真实连接、迁移前备份、空库初始化和存储传输核查。凭证、项目地址、数据库连接信息、证书与备份只在本机非文稿同步目录 `~/Library/Application Support/VideoMind AI/`，配置/凭证权限 0600，目录 0700；没有写入 Git。原有 `.env`、本地数据库、运行容器和主密钥未替换，`outputs/` 与 `backend/:memory:.ses` 保留。

当前本地 Docker 仍是 local/Chroma 演示环境。本轮针对云库的检查通过专用临时进程显式加载私有配置，不代表旧本地预览已变成云端站点。最初 Colima 约 2GB；随后用户授权扩容并启动独立云预览，结果见下方运行补充。

## 真实服务证据

| 项目 | 实际结果 | 尚未证明 |
| --- | --- | --- |
| 项目配置 | 控制台已关闭 Data API；Email、注册、Confirm email 开启；Site URL 随独立预览改为本地 3001；私有桶 Public 关闭 | 两个账号实际注册、邮件送达、JWT/会话与逐用户隔离 |
| HTTPS/容器网络 | 宿主 Python 默认 CA 文件缺失；改用系统受信任 CA 后 Storage 通过。容器沿用项目 DNS 223.5.5.5/1.1.1.1 后当前 HTTPX 客户端通过 | 生产网络稳定性与公网平台访问 |
| 数据库连接 | 真实 PostgreSQL **17**，Session pooler，官方数据库 CA + **verify-full**，只读认证成功 | 目标部署平台连接池和长期负载 |
| 初始化前状态 | public 业务表 0，业务迁移未安装 | 既有云端业务结构升级/旧文件迁移 |
| 迁移前备份 | 官方 PostgreSQL 17 客户端自定义格式 pg_dump 成功，383761 字节，pg_restore --list 成功；归档只在私有目录 | 完整隔离恢复、恢复后的权限和对象一致性 |
| 显式迁移 | 业务 `20261024_0008`、向量 `20261103_v001`、对象 `20261107_o003` 均成功；业务用户/视频均 0 | 真实数据迁移、本人模型闭环 |
| 云端访问配置 | 先核对 public 表集合与后端所有者，再为 13 张业务/版本表启用 RLS、撤销 PUBLIC/anon/authenticated/service_role 表权限；客户端表授权剩余 0，后端所有者读取通过；同步收紧该所有者 public 新表/序列默认授权，未修改 auth/storage 系统表 | RLS 不是浏览器逐用户 policy；后端仍负责本人过滤。未来改变数据库运行角色时须重新验收 |
| 真实 Storage | 唯一键合成小文件上传、下载大小/SHA-256、只读 verify、精确删除和再次确认缺失均通过；最初测试键也重试确认清理 | 真实账号的 HTTP 上传/处理、服务商、提供方全部历史副本或备份清除 |
| 当前应用就绪函数 | 对真实库/pgvector/私有桶返回 ready；真实账本只读汇总 preview、记录 0、无写入；真实 Auth 公共 settings 连接通过、Email 与邮箱确认开启 | 此行仅函数检查；随后 HTTP 就绪证据见运行补充，仍非 Worker 任务或真实登录验收；账本 0 不等于全桶清单 |

数据库 CA 从项目控制台 Download certificate 的官方地址取得，并检查有效期；没有关闭 TLS 验证，也未修改全局系统信任库。使用已有加密主密钥准备独立云配置，不生成替代主密钥；云库尚无真实用户密文，不能标记解密恢复已验收。

存储检查只使用本轮新生成的随机不可变键和几十字节合成文本，没有私人视频、全桶扫描或前缀删除，也没有调用付费 ASR/LLM。当前桶页面显示单文件有效上限 50 MB，私有预览配置将上传上限设为 50 MB；这不是提供方总量、费用或物理副本容量验收。

## 实际发现与修复

真实对象删除响应成功后，GET authenticated object 返回 **HTTP 400**，正文包含 `statusCode=404`、`code=NoSuchKey`、`error=not_found`、`message=Object not found`。旧代码只接受 HTTP 404，导致删除确认失败；只读 audit 也会将同一响应记为 failed。

新增严格且有界的缺失判定：保留普通 HTTP 404；仅对 HTTP 400 且上述四字段完全匹配的身份编码 JSON 视为同等缺失，正文迭代达到 64 KiB 即拒绝，不再读取下一块。其他 400、缺桶、401/403、5xx、模糊/损坏/压缩正文不放行。删除确认 GET 显式请求 identity 编码；DELETE 本身仍必须先获得原有受支持的确认状态。

这不扩大清理权限：pending 的匹配/缺失仍只观察、不晋升/不释放额度；只有受支持删除入口留下的明确退休意图才进入业务清理命令。修复后重试原合成键并完成新一轮真实传输/删除检查。协议参考：[Storage 错误码](https://supabase.com/docs/guides/storage/debugging/error-codes)、[官方 NoSuchKey 定义](https://github.com/supabase/storage/blob/master/src/internal/errors/codes.ts)。

## 自动检查

- 后端最终 **359 passed**、无跳过；启用一次性 PostgreSQL 配额、pgvector、对象用例。`ruff check app tests scripts alembic_pgvector alembic_objects` 通过。
- 新增覆盖严格 typed 400、拒绝权限/缺桶/模糊错误、单块错误体预算、清理 SQL 状态与 pending 额度保护。模拟用例仅在隔离 SQLite/一次性 PostgreSQL 执行，没有在云库运行 pytest。
- 前端源码未改；初次隔离构建在 2GB Colima 与后端并行时以 137 中止（已编译/类型阶段通过），保留这次失败记录；随后串行并限制 Node 堆为 768MB，4 项部署保护用例及 `npm run build`、`npm run typecheck`、`npm run lint` 全部通过；初次中止仍保留为资源边界证据。
- hash 检索固定虚构语料回归通过：Recall@3=0.9643，Hit/MRR=1.0，越权计数 0。不是 BGE 或真实问答质量验收。
- 既有 LangChain 弃用与 ONNX/Chroma 遥测提示仍在，不把退出 0 当作已修复这些依赖提示。

## 独立云预览运行补充

用户随后明确授权扩容：2026-11-08 在本地 queued/running=0 后，Colima 已由 2GB 调到 4GB（Docker 可用约 3.81 GiB），保留数据卷并恢复原四个容器。独立预览前端 `http://localhost:3001/auth`、API `http://localhost:8002/api/v1` 与云 Worker 已启动，端口仅绑定 127.0.0.1；API/Worker 读取私有配置/CA，前端仅加载公开配置与隔离源码副本。真实 HTTP ready=200（数据库/pgvector/私有桶 ok），无令牌 videos=401，登录页=200；Worker 启动无循环错误，真实云队列 queued/running/failed/expired=0；首次独立队列检查未取得结果，重试后读取成功。原本地 3000 登录页和 8001 存活检查均 200。Supabase Site URL 已改为 `http://localhost:3001` 并重载确认，无通配重定向。阶段临时上限 128MB、最小余量 128MB、每个后端容器暂存 tmpfs 512MB，仅为此预览约束，不是总量/多实例验收；暂存不持久，正式文件走私有桶。用户仍需自行注册并确认邮箱，两个账号及本人模型闭环未验收。

功能提交 `57c0794` 已同步，GitHub [CI 42452665353](https://github.com/17-chen/videomind-ai/actions/runs/42452665353) 前后端均通过。

## 下一步

独立云端 API、Worker 与前端已启动；不将现有演示用户和本地文件直接切换过去。准备 SMTP/两个能收信的真实测试账号，各自保存本人 LLM/ASR Key，再验证真实上传→转写→笔记→入库→问答引用、跨账号拒绝、删除、重启和持久性。旧数据迁移、未决上传解决协议、完整恢复、真实 BGE/中文资料质量和目标平台部署仍未完成，R6/R7/R9 均不标记整项完成。
