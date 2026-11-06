# 部署时机与预发布步骤

核对日期：2026-11-06。当前是本地功能演示与生产准备阶段。2026-11-03 新增可选 [pgvector 共享向量适配](PGVECTOR.md)，本地真实 SQL 已验证，目标云服务未接入；2026-11-04 新增[对象传输/账本基础](OBJECT_STORAGE.md)，2026-11-05 视频删除意图已接入，2026-11-06 处理/分析/笔记服务已有显式对象路径，但上传 API、持久 Worker 后端选择与迁移未完成，不能据此切换部署拓扑。上传、编辑、队列、本人配置调用路径及配额有代码和测试证据；真实双用户、本人模型闭环及云端持久存储未验收。后端测试数量不是产品完成百分比。

## 什么时候部署

| 阶段 | 当前判断 | 进入条件 |
| --- | --- | --- |
| 本机开发预览 | 已可使用 | 保留现有本地数据、密钥和 Docker 环境 |
| 受保护的线上预发布 | 现在开始准备；资源配置后进入联调 | 固定 HTTPS 前后端地址、Supabase 测试项目、可用的个人模型额度、明确 API/Worker 共享持久存储方案；前后端配置预检通过 |
| 邀请少量真实用户 | 尚不满足 | 双账号隔离、各自 Key、真实上传/下载→转写→笔记→入库→问答/引用、删除、重启和持久性在目标环境通过 |
| 公开发布 | 尚不满足 | 上述验收通过，并完成备份恢复、生产流量入口与告警；按真实负载明确剩余限制 |

下一阶段应开始部署联调，不必等所有检索优化和长期负载优化结束。也不能仅部署一个能打开的首页就宣称完整网站上线。没有账号配置和目标环境验收日期时，不给出承诺式上线日期；历史 50–80 小时是原始总量，不能作为现在的剩余时间。

项目所有者现在需要准备：Supabase 测试项目和两个测试账号、本人模型可用额度，以及目标平台账号/资源与费用选择。密钥只进入本地私有环境或平台密钥设置，不发在聊天里、不提交到 Git。实际创建、付费资源和公开发布仍以当次授权为准。

## 先解决 API 与 Worker 的存储拓扑

当前 API 接收上传、编辑/删除文件并访问 Chroma；Worker 读取媒体并生成音频/转写/笔记、写入向量。两者依赖相同的本地路径和数据，单独运行 API 不会消费持久任务。

**不能直接把当前 API 和 Worker 分别部署成两个 Render 服务，再给它们各挂一块盘。** 两块同名路径的盘不是同一份文件。Render 持久盘只能由单个服务实例访问，其他服务无法共享；无持久盘的文件会在重部署时丢失。[Render 官方磁盘说明](https://render.com/docs/disks)。

原定 Vercel + Render + Supabase 路线保留，但 Render 的最终服务配置必须等存储适配后确定：媒体、音频、转写和笔记需要共享对象存储，向量需通过 pgvector/可访问的独立向量服务共享。现有生产 Chroma 本地双进程模式也不能假定支持多服务并发。

另一种受限预览可以将现有 Compose 布置在一台受控主机，保留共享业务目录；这仍需入口 HTTPS、访问保护、备份、资源限制和该主机实测，不是本轮已交付的 Render 部署方案。本轮没有擅自切换平台或创建服务，因此不提供会掩盖上述问题的可直接启动 Render 双服务蓝图。

## 前端 Vercel 配置

1. 项目 Root Directory 选择 `frontend`，框架选择 Next.js，Node 22。仓库已有 `frontend/vercel.json`，使用 `npm ci` 与 `npm run build:deploy`。当前 Next.js 支持和自定义构建字段见 [Vercel Next.js 文档](https://vercel.com/docs/frameworks/full-stack/nextjs) 和 [静态配置文档](https://vercel.com/docs/project-configuration/vercel-json)。
2. 按 `deploy/frontend.env.example` 在对应 Preview/Production 环境配置四个公开变量。`NEXT_PUBLIC_APP_URL` 填实际、稳定的前端 HTTPS origin；API 地址必须包含 `/api/v1`。`INTERNAL_API_BASE_URL` 建议不设置，让服务端请求使用同一地址；不要沿用本地 `http://backend:8000`。
3. 公开 Supabase 变量只能使用 publishable key 或旧 anon key；禁止 secret/service-role Key、数据库密码、模型 Key、Cookie、主密钥出现在 `NEXT_PUBLIC_*`。预检允许项目四个公开变量和官方列出的 Vercel 框架元数据，其他公开变量需先明确用途。参见 [Vercel 框架变量](https://vercel.com/docs/environment-variables/framework-environment-variables)。
4. 部署命令先检查配置，再执行已有构建。普通本地 `npm run dev` 和 `npm run build` 保持原行为；部署时不要在平台覆盖回普通 build 来绕过检查。
5. 公开环境变量写入构建产物，修改后重新构建，不能只重启旧产物。[Next.js 环境变量说明](https://nextjs.org/docs/pages/guides/environment-variables)。预发布访问保护需在平台核对，代码文件本身不启用平台密码。

前端检查：在已导出目标环境变量的前端目录执行 `npm run check:deployment`。输出只含固定检查名和布尔值；返回 0 表示配置形式通过，2 表示被阻止；不会连接 Supabase 或 API。`build:deploy` 随后实际构建，普通 CI 还检查部署保护用例。

## 后端环境、迁移和就绪

后端模板为 `deploy/backend.env.example`。这些都是无凭证占位模板，不能直接当作可用环境：

| 配置组 | 要求 |
| --- | --- |
| 环境与认证 | `APP_ENV=production`、`AUTH_MODE=supabase`、前后端 Supabase 项目一致、使用公开项目 Key |
| 数据库 | 当前驱动为 `postgresql+psycopg`；按提供方 URL 设置连接与 TLS，模板要求 `sslmode=require` 或更严格模式；目标平台连通性另验 |
| Schema | `AUTO_CREATE_DATABASE_TABLES=false`；先备份，再单独运行现有 `python -m scripts.migrate`，核对 `alembic current` |
| 主密钥 | 从已有安全备份继承 `USER_API_KEY_ENCRYPTION_KEY`；部署/重启不生成或覆盖；格式有效不等于能解开真实密文 |
| CORS | 只允许确切前端 HTTPS origins，包含实际预发布域名；不使用 `*` 或域名通配符 |
| 文件与向量 | 绝对路径不代表有持久盘；须通过 R6 的目标拓扑与持久性验收 |
| ASR/检索 | 默认 ASR disabled 只能处理已有字幕；hash 检索仅基础实现；真实转写和检索质量另验 |

在目标后端环境执行只读检查：

```bash
python -m scripts.check_deployment --frontend-env-file /secure/frontend.env
```

该文件只用于比对拟部署的前端变量，环境中已有值优先；本地 Compose 已导出的 localhost 配置会优先于文件，因此本机开发环境被阻止是预期结果。不要为使预检变绿而改写正在使用的本地 `.env`。CLI 不输出变量值、URL、密码、Key 或校验异常正文，不访问网络/数据库，不迁移/写文件。`configuration_passed` 只是配置形式通过；输出始终保留 `ready_for_public_users=false` 和待做真实验收清单。格式错误/无法读取返回 2，不能以退出 0 替代验收。

最终 API 启动沿用生产镜像：迁移后启动 Uvicorn，禁用原始访问日志和代理头信任。Worker 为 `python -m scripts.video_worker`，独立消费同库任务；Linux 音频监督和 init 回收条件见 [临时空间说明](TEMPORARY_STORAGE.md)。不要在迁移不兼容的情况下让多个实例同时无序迁移。`/health` 是进程存活；`/api/v1/health/ready` 核对数据库连接和向量库可用性。就绪成功仍不证明 Worker、文件共享或第三方服务可用。

Supabase 的 Site URL、允许重定向 URL 和实际预发布地址保持一致；需按当前密码登录/注册/邮箱验证流程测试。只添加受控预发布域名，不因调试把所有任意域名开放为可信回调。[Supabase 重定向说明](https://supabase.com/docs/guides/auth/redirect-urls)。

## 目标环境必须留下的验收证据

- 两个真实账号的注册/验证、登录/退出、刷新/过期；A 不能读、改、处理、删除或检索 B 的资料。
- 各自模型和转写 Key 的保存/替换/删除与调用；缺 Key 不回退到站长 Key，错误和额度不足反馈明确。
- 真实视频完成转写、笔记、入库和问答，回答引用与原资料一致；说明使用的模型和剩余质量问题。
- Worker 中断后任务恢复；API/Worker 重部署和实例替换后，数据库、媒体、笔记和向量可对账。
- 删除、限流反馈、日志脱敏、备份/隔离恢复和主密钥可解性；记录未通过项。

当前这些目标服务验收没有完成。本轮预检、合成配置和本地构建只支持进入下一步联调，不构成发布成功。
