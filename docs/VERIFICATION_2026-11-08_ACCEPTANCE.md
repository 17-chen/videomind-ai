# 2026-11-08 自动更新复核与验收推进

## 本轮结果

- Git 起点 `7b3a6b4`，fetch 后与 origin/main 一致。原未跟踪 `outputs/`、`backend/:memory:.ses` 保留，未读取、提交或清理。
- 真实 Safari 的 3001 已登录详情页可见摘要、核心观点、时间线和 Markdown 笔记；任务 completed、尝试次数 1。本轮未重新处理现有视频，未触发任何模型调用，不保存视频正文或身份信息。
- 这次浏览器读取存在长时间延迟；没有从新任务入队开始观察，不能把现有终态页面作为全程无手动刷新证据。真实全程自动更新仍待完成。

## 自动更新补强

原实现入队后依赖下一次读取或服务端刷新才锁定按钮；当视频快照仍是旧终态、任务接口已经 running 时，也可能提前解锁。现在收到 queued 立即更新本地快照并清除旧任务；queued/running 任务与视频状态共同决定是否处理中。保留原有 3 秒串行轮询、终态 router.refresh 和卸载保护。

新增 5 项模拟回归：入队立即锁定；queued→transcribing→analyzing→embedding→completed 自动观察并触发详情刷新；运行中任务遇到旧 completed 视频仍锁定；瞬时错误重试及卸载忽略在途结果；问答响应的标题、片段与详情引用链接及单次语言参数。测试只证明组件行为，不证明 Next.js 服务端详情正文在真实任务完成后自动呈现，也不证明真实模型引用准确。

## 检查与运行证据

- 前端全部 12 项测试通过；临时源码副本 build/typecheck/lint 通过。依赖复用运行卷，未覆盖运行 .next；隔离 build 因 node_modules 符号链接提示 standalone tracing 路径警告，本产物不用于部署。
- 后端当前源码 359 项全量及 `ruff check app tests scripts` 通过；一次性 PostgreSQL/pgvector、内存盘、无真实配置/业务卷，三组 PostgreSQL opt-in 测试均开启。身份、ASR、云对象服务和模型响应仍使用测试替身；含真实本地媒体工具与 SQL 检查。
- 初次测试环境使用 SQLite，随后 PostgreSQL 副本又遗漏 evals，产生环境相关失败；纠正隔离环境和语料路径后全量通过。前端首次临时命令的配置文件名/模块路径及测试状态槽位已纠正，最终结果如上，不作为产品故障记录。
- 单个 `video-actions.tsx` 已同步到 3001 私有源码副本，SHA-256 与仓库一致。未重启 API/Worker。3001 /auth=200，8002 匿名 /videos=401；ready 返回数据库、向量及 Supabase 文件后端 ok。
- 按预览启动器先加载 `/run/secrets/cloud.env` 后只读检查：queued=0、running=0、succeeded=1、failed=0、cancelled=0、expired_leases=0。裸 docker exec 不继承启动器 dotenv 注入，第一次裸检查出现 DNS/空密钥格式错误，不能据此认定运行服务配置损坏。
- 同样按启动器加载配置后，现有密钥校验返回 `verified`、settings_rows=1、encrypted_values_checked=1。仅校验当前配置可解现存密文，没有导出明文或修改主密钥；不等于备份密钥、数据库/文件隔离恢复验收。

## 未完成关口

用户确认第二真实账号尚未准备，先完成可独立验证部分。现有模拟回归覆盖本人模型选择、禁止所有者密钥回退、他人资料拒绝访问和问答来源隔离；不能替代两个真实 Supabase 会话。真实问答答案与原资料对照、错误 Key/额度不足、双账号、完整备份恢复和新任务真实浏览器全过程均保持待验收。云检索仍为 local_hash，不作为真实 BGE 质量证据。
