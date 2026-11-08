# 私有对象传输与文件账本基础

2026-11-07：上传 API、笔记编辑和持久 Worker 共用可选文件后端；生成、读取和删除路径已接入。默认 `FILE_STORAGE_BACKEND=local`，现有运行库与文件未迁移。可以为已准备账本和私有桶的受控空白环境选择 supabase；旧文件迁移、未知上传对账和真实云端验收仍待完成。API/Worker 分拆还需要共享数据库与 pgvector，不能以两块独立磁盘代替共享存储。

## 当前实现

- `app/services/object_storage/supabase.py` 使用已有 httpx，通过 Supabase Storage REST 上传、读取、删除私有对象。每次操作先读取 bucket 元数据，拒绝 public bucket；不自动建桶，不生成公开或签名链接。
- 服务端配置为 `SUPABASE_URL`、`SUPABASE_STORAGE_SERVICE_KEY`、`SUPABASE_STORAGE_BUCKET`（默认 `videomind-private`）。现代 `sb_secret_` 只放 `apikey`；旧 service_role JWT 同时使用 Bearer。拒绝公开 Key、不跟随重定向、不使用环境代理。生产只允许 HTTPS；仅测试显式开放 loopback HTTP。密钥只进后端私有环境，禁止放入 `NEXT_PUBLIC_*`，禁止提交真实值。
- 此凭证用于平台文件存储，与用户本人 LLM/ASR Key 无关；不改变已认证用户的密钥隔离规则。由于存储凭证有高权限，应用层必须先核对当前用户和视频归属。
- 账本对象键形如 `users/<user>/videos/<video>/<kind>/<artifact-uuid>/<video>.<extension>`；只接受服务端规范 UUID 与安全文件名。每次发布分配新对象键，`x-upsert=false`，不覆盖旧对象。账本还保存 bucket、项目指纹、字节数和 SHA-256，拒绝切错项目后读取同名对象。
- 上传逐块校验实际大小/摘要；下载在私有暂存目录逐块校验后才替换目标，失败清理本次临时文件，保留已有目标。拒绝符号链接源文件与目标，使用已有阶段大小和磁盘余量限制。分块 64 KiB，socket 读超时 30 秒、连接 10 秒、传输检查点预算默认 300 秒；检查点预算不是精确的全程硬截止或并发磁盘预留。

## 账本状态和事务

`pending → ready → retired → deleted`，没有自动后台清理或旧版恢复入口。

1. 用专用、无待提交业务改动的 Session 核对视频归属、测量文件，测量后再次锁视频，将 pending 意图提交后释放锁，再上传。这保留进程故障或响应丢失时的对象键，便于未来对账。
2. 上传成功后锁用户行，再锁视频，重新核对归属并计算账本内当前 ready 文件及 pending 来源预留总量；替换按净增长计量。旧版改 retired、新版改 ready 在同一事务提交，partial unique index 保证同一逻辑文件只有一个 ready 版本。
3. 上传或发布失败，旧版继续 ready，新记录保留 pending；不因异常擅自删除结果不明的远端对象。SQL 失败对外仅固定错误，日志只记异常类型。
4. 读取必须同时匹配当前用户、视频及 ready 状态；在本次私有目录落地，用完删除缓存。retire 后才允许显式 purge；远端删除响应成功后还要读取确认 404，才把账本标为 deleted。当前 ready 对象不允许直接 purge。

**逻辑总量核算 ready 文件 + pending 来源上传预留，来源上传额度核算 ready/pending 且 `is_source_upload=true` 的对象。** 生成过程的 pending、retired 旧版及提供方账单不在逻辑配额内；预留不能代替远端物理账单、在途生成预留或本地并发磁盘容量保护。相同用户仍禁止本地正式文件与对象数据混用。

## 统一配置与上传

`FILE_STORAGE_BACKEND=local` 不创建云客户端或查询对象表；`supabase` 通过共享工厂先只读检查账本必要列与私有 bucket，配置、列或访问不可用返回固定 503，不自动回退。API 上传/笔记编辑、持久 Worker 及兼容工作流入口共用工厂，结束关闭客户端。认证在 HTTP 文件工厂之前执行。API 与 Worker 必须使用相同配置、数据库和项目；不要只修改其中一个进程。

上传仍验证扩展名、MIME、大小、ffprobe，并在私有暂存目录计算摘要。随后在用户锁内核算来源额度与总量，把 `is_source_upload=true` 的 pending 记录提交，再释放锁执行不可变键上传；远端确认后重新锁用户，复查额度并将 Video 与 ready 原子提交。201 才代表两者完成，失败不会显示半成品 Video。普通同用户重复返回 409；相同摘要已有未决来源也返回 409，不同用户分别计量。数据库 partial unique index 兜底并发重复。

上传响应不明或最终 SQL 失败时，pending、精确键和额度保留。即使列表没有该视频，预留仍占额度；可能长期阻止重复/新上传。当前没有安全的自动释放/重试恢复入口，不按年龄、404 或视频缺失删除账本或远端副本。真实部署前需要完成可恢复对账。已有上传 Video 如果没有准确绑定本人 ready 源对象，则拒绝新增云上传，避免漏算旧来源。

`/api/v1/health/ready` 除数据库/向量外检查所选文件后端，成功增加 `file_storage` 字段；云模式会访问桶元数据，但不上传文件，不验收真实权限、持久性、Worker、备份或双用户闭环。部署配置预检仅检查 backend 枚举和云凭证形状，不访问网络。

## 处理服务的显式接入

- `generate_artifacts(..., object_store=store)` 在原有私有暂存目录生成，验证整组输出后调用 `publish_artifacts`。同一视频/种类最多 100 个不同文件，组大小受阶段上限控制；全部 pending 先持久化，全部上传确认后才原子切换 ready。失败保留旧组和待对账键。
- 生成输出使用完整种类快照：旧组中不再出现的文件名也退休，避免新视频搭配旧语言字幕。兼容的 `publish_artifact` 仍仅替换同名文件，不自动退休其他名称。
- 发布事务在用户/视频锁下核算净增长，并可调用只修改当前 Session 的 SQL 回调；视频/音频引用、转写正文、分析/手工笔记正文随对象组一起提交。回调不得自行提交或进行网络调用；SQL 失败后两者一起回滚，已上传的新键仍 pending。向量同步继续在提交之后，保留原有重试边界。
- `process_video(..., object_store=store)` 持久化 `object://<artifact-uuid>`，不是远端地址或另一实例的缓存路径。视频和 sidecar 按用户/视频/种类/current ready 查询，要求主对象属于该组；逐文件校验后在本次私有目录供字幕和 ffmpeg 使用，音频另行私有落地供 ASR。完成或失败都销毁本次缓存，并恢复 ContextVar 输入目录。
- 组读取再次检查视频归属后才向处理步骤交付路径；有大小/数量边界。它不是在途读取强制撤销机制，也不是并发磁盘容量预留。单次任务同时缓存不同种类的文件，合计空间仍需 R8 统一预留。
- `analyze_video(..., object_store=store)` 和 `update_note_for_user(..., object_store=store)` 使用同一发布接口，保留手工笔记规则；本人 LLM/ASR 配置路径不变。读取笔记正文仍来自 SQL，前端无需看到 bucket、项目指纹或服务端凭证。

这些显式参数保留给可信服务端调用；浏览器不能选择客户端或传入凭证。默认入口由统一工厂注入，沿用当前用户、任务归属和既有状态/租约校验。对象来源必须是已登记引用，本地路径不能当作跨实例来源。

缺少客户端时，已知对象引用的处理/笔记服务会拒绝降级为本地。为避免现有配额按本地 Path 漏算，**同一用户禁止混用**：对象发布在预检及用户锁下再次检查已有本地正式文件；本地配额准入检查该用户非 deleted 的对象记录（含未决意图），存在时返回固定 503。未安装账本的本地行为保留。这不是旧文件迁移方案；真实切换须先完成旧文件数量/摘要核对和迁移/回退，不要通过删账本或改状态绕过保护。

## 显式迁移

模型用独立 `ArtifactBase`，不属于业务 `Base.metadata`，普通启动/create_all 和业务迁移不创建此表。先备份目标库、核对业务迁移，再在受控环境执行：

```bash
cd backend
python -m scripts.prepare_objects          # 返回 2：未连接数据库、未写入
python -m scripts.prepare_objects --apply  # 仅明确准备账本时执行
```

成功版本为独立 `alembic_version_objects=20261107_o003`，业务 head 保持 `20261024_0008`。从 001 升级经 002 新增 delete_requested，003 新增 is_source_upload 与 pending 来源唯一索引。003 只回填 source=upload 视频准确绑定的本人 ready video 对象，sidecar 和不明 pending 不推断；旧受控试验数据仍需人工核对。脚本可重复执行，但不验证 bucket，也不启用上传/处理业务存储。迁移开启 RLS，撤销 PUBLIC 及已存在 anon/authenticated/service_role 的表权限，表只供可信后端数据库角色访问；该角色需有实际 SQL 权限，不能依赖客户端 JWT 直接读账本。

账本故意不设级联删除外键，避免视频/用户删除后丢失远端清理键。视频不存在时，用户读取和直接 purge 仍拒绝；可信维护命令只接受受支持删除入口留下的明确意图。回退应用时保留账本和对象；有未完成意图时，002 迁移拒绝降级丢弃删除意图；存在未 deleted 的来源记录时，003 拒绝降级丢弃来源计量列。不要绕过保护删列/删表或批量删前缀。

## 视频删除与显式清理

`DELETE /videos/{id}` 锁定本人且非处理中的视频后，若账本已安装：先锁属于该用户/视频的对象，把未完成的对象标为 `delete_requested=true`，ready 改为 retired；随后删除向量，并将意图与业务视频删除在同一 SQL 事务提交。pending 保持 pending，已 deleted 的记录不动。向量/SQL 失败会回滚意图和视频；跨向量库事务仍不能回滚，必要时须重新索引。

未安装可选账本时保留原有本地流程；账本已存在但缺 002 列或无权限时，在触碰向量前返回 503，不静默绕过云端清理意图。请先备份并升级可选迁移。普通启动不会自动升级此表，本机既有库仍未安装。

删除 API 成功表示业务内容已移除、清理意图已提交，**不代表云端副本已经全部物理删除**。API 请求不调用 Storage、后台也不自动执行维护命令。运维可在核对私有 bucket、项目和目标库后执行：

```bash
cd backend
python -m scripts.cleanup_objects                    # 默认只读预览，不创建 Storage 客户端
python -m scripts.cleanup_objects --apply --limit 20 # 明确执行，最多 20 次，允许 1–100
```

只处理 `delete_requested=true AND state=retired` 且同 ID 视频不存在的对象；按精确、不可变键删除并通过认证读取确认 404，再提交 deleted。失败保留意图，下次显式重试；删除不占用媒体缓存，因此不受后来调低的本地阶段文件上限阻挡，上传/下载仍受限；不按前缀批量删，也不因文件年龄或视频缺失推断删除权限。即使是标记过的对象，若手工恢复了同 ID 视频也会阻止清理。

PostgreSQL 每次只锁一个对象，`SKIP LOCKED` 防止维护进程同时删除同一对象；网络期间不持有用户或视频锁，但仍占用对象行锁与数据库连接。每批次数有上限，不等于整个命令的严格时间上限；SQLite 仅用于隔离用例，不作为多维护进程方案。

输出只有聚合数量：eligible、pending_uncertain、blocked、attempted、confirmed_deleted、failed、writes_performed 和 status。退出 0 为正常只读预览、未安装或本批全部完成；退出 2 为错误、执行后仍有积压/失败/阻止项或结果不明项。预览可列出 eligible>0 而仍退出 0；需另看计数，不把 0 当作没有副本。

**pending 即使视频已删除、对象暂时 404 或上传线程已退出，也不自动清理。** 远端请求可能结果不明或仍在处理，不能通过本机租约撤销。删除在途上传会保留其 pending 意图；后续发布拒绝已删除的视频及已标记的对象。需要另做有凭据的上传结果对账/解决流程，当前不能承诺所有副本最终自动回收。

直接 SQL 删除、用户整体删除、旧记录缺失意图、无标记的 retired 对象都不在此命令自动范围内。恢复数据库前停止维护命令，核对数据库与对象快照；未完成云端恢复验收前不自行修改状态去强迫清理。

## 只读账本与远端核查

2026-11-08 新增可信运维命令，不提供浏览器用户接口：

```bash
cd backend
python -m scripts.audit_objects
python -m scripts.audit_objects --verify-remote --limit 20 --max-mb 512
# 仅在暂停所有账本写入后跨批巡检；第二批示例
python -m scripts.audit_objects --verify-remote --offset 20 --limit 20 --max-mb 512
```

默认只读取 SQL，汇总各状态条数/账本声明字节、pending 来源预留字节及缺少本人视频的 ready 数量；不创建云客户端、不打开本地业务文件。对象表未安装时返回 `not_installed`，条数/字节为未知空映射，不把它说成云端空桶。旧 schema 或 SQL 权限不足返回固定 error，不自动迁移。当前要求对象迁移 003。

`--verify-remote` 才读取所配置私有桶中的账本精确键，通过真实响应流计算大小/SHA-256，不扫描 bucket 前缀、不写媒体缓存。仍先检查项目指纹和桶私有性，不跟随重定向、不过代理。高权限 Key 仅用于服务端维护，此命令不改变本人 LLM/ASR Key 规则。远端读取可能产生提供方请求/出网费用，默认不启用。

按 UUID 排序取一批（limit 默认 20，范围 1–100）；max-mb 默认 512 MiB，范围 1–10240。每次读取前按账本字节 + 64 KiB 溢出块预留预算，即使失败也不归还本批预算；流超出声明大小最多再迭代一块即停止。预算限制对象响应正文，不含桶元数据、HTTP/TLS/内核缓冲；不是严格网络账单上限。继承连接/读取超时与传输检查点预算，不承诺整个命令有严格总时限。无需沿用媒体暂存文件上限，因为没有磁盘缓存。

PostgreSQL 初始汇总/选取使用只读可重复读；释放事务后才访问网络。每次读取后在新只读事务复查整条元数据、状态、意图和更新时间，变化单独记 `changed_during_check`。不会锁对象/用户/视频行或在 GET 期间占 SQL 事务。它仍不是跨数据库和 Storage 的原子快照；对象可在后续变化，SQL 未变也不能证明远端上传已停止。跨批 offset（范围 0–1000000）只适合已暂停写入的人工巡检，并发增删会造成跨批遗漏/重复。

只输出聚合，不包含用户/视频/对象 ID、邮箱、文件名、摘要、bucket/项目/Key 或异常正文。remote 的 matched/absent/mismatch/failed 为非 deleted 对象的读取结果；deleted_absent 是已删除对象当时不存在，deleted_present 表示又读到内容。changed_during_check 不当作稳定匹配；skipped_budget 或 truncated 表示本批不能覆盖所选后续范围。源账本条数/字节始终为初始快照，remote 计数不能当作最新账本总量。

状态 `preview` 为仅账本预览，`observed` 为选定批次没有发现上述异常；均不表示完成全桶清单、业务引用迁移或真实服务验收。初始存在 pending/缺少本人视频的 ready，或远端发现缺失/不符/失败/变化/已删除对象再出现/预算跳过/后续截断，返回 `needs_attention`、退出 2；固定 error 也退出 2。其余退出 0，包括未安装；必须结合字段理解，不能只凭退出码判定可上线。offset>0 只覆盖该位置起的一批，不宣称已核查前面的对象。

**所有结果均保持 `observations_only=true`、`writes_performed=false`。pending 即使匹配或 404 也保持原状态和额度；不会创建 Video、恢复旧版、释放预留、退休或删除对象。** 有凭据地解决未决上传和旧文件迁移仍需后续实现，不能用手改账本绕过这一边界。

## 后续接入顺序与真实验收

1. 上传/来源额度、处理/分析/笔记、持久 Worker/HTTP 工厂与预检已接入；继续旧文件迁移与远端物理容量/预留，解除混用保护必须有数量/摘要对账证据。
2. 视频删除意图与已确认对象的显式重试已接入；只读汇总与远端观察已补；继续有凭据地解决 pending、用户整体删除、无标记旧对象迁移和读取在途边界，不把本命令当成通用垃圾回收。
3. 提供本地旧文件迁移、数量/摘要核对和回退方案；显式模式选择不执行这些操作，不要直接切换已有用户。
4. 使用真实私有 bucket、后端角色和两个账号，验证 API/Worker 跨实例读取、重部署后持久性、服务商失败/删除语义、桶策略与恢复。高权限凭证绕过 Storage RLS，应用归属检查不可省略；桶元数据检查也不能阻止管理员随后将桶改成 public。

当前证据包括真实本地文件、loopback HTTP 和一次性 PostgreSQL；Supabase 响应、用户及角色均为模拟。真实 Supabase 注册/JWT、Storage 网络/API/策略/费用、真实模型调用均未验收，见 [基础核查](VERIFICATION_2026-11-04.md) 、[删除核查](VERIFICATION_2026-11-05.md) 、[处理服务核查](VERIFICATION_2026-11-06.md) 、[上传/统一后端核查](VERIFICATION_2026-11-07.md) 和 [只读对账核查](VERIFICATION_2026-11-08.md)。

协议依据：[Supabase 私有下载](https://supabase.com/docs/guides/storage/serving/downloads)、[API Key 与 secret Key 用法](https://supabase.com/docs/guides/getting-started/api-keys)。
