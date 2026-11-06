# 私有对象传输与文件账本基础

2026-11-06：R6 处理/分析/笔记编辑服务可显式注入对象客户端，已接入成组发布、按归属私有落地读取和业务正文同事务提交。**HTTP 上传入口、持久 Worker 的后端选择和部署切换尚未接入**。默认仍为本地；设置下列凭证不会自动启用对象存储，当前 API/Worker 仍不能放在两块独立 Render 磁盘上运行。

## 当前实现

- `app/services/object_storage/supabase.py` 使用已有 httpx，通过 Supabase Storage REST 上传、读取、删除私有对象。每次操作先读取 bucket 元数据，拒绝 public bucket；不自动建桶，不生成公开或签名链接。
- 服务端配置为 `SUPABASE_URL`、`SUPABASE_STORAGE_SERVICE_KEY`、`SUPABASE_STORAGE_BUCKET`（默认 `videomind-private`）。现代 `sb_secret_` 只放 `apikey`；旧 service_role JWT 同时使用 Bearer。拒绝公开 Key、不跟随重定向、不使用环境代理。生产只允许 HTTPS；仅测试显式开放 loopback HTTP。密钥只进后端私有环境，禁止放入 `NEXT_PUBLIC_*`，禁止提交真实值。
- 此凭证用于平台文件存储，与用户本人 LLM/ASR Key 无关；不改变已认证用户的密钥隔离规则。由于存储凭证有高权限，应用层必须先核对当前用户和视频归属。
- 账本对象键形如 `users/<user>/videos/<video>/<kind>/<artifact-uuid>/<video>.<extension>`；只接受服务端规范 UUID 与安全文件名。每次发布分配新对象键，`x-upsert=false`，不覆盖旧对象。账本还保存 bucket、项目指纹、字节数和 SHA-256，拒绝切错项目后读取同名对象。
- 上传逐块校验实际大小/摘要；下载在私有暂存目录逐块校验后才替换目标，失败清理本次临时文件，保留已有目标。拒绝符号链接源文件与目标，使用已有阶段大小和磁盘余量限制。分块 64 KiB，socket 读超时 30 秒、连接 10 秒、传输检查点预算默认 300 秒；检查点预算不是精确的全程硬截止或并发磁盘预留。

## 账本状态和事务

`pending → ready → retired → deleted`，没有自动后台清理或旧版恢复入口。

1. 用专用、无待提交业务改动的 Session 核对视频归属、测量文件，测量后再次锁视频，将 pending 意图提交后释放锁，再上传。这保留进程故障或响应丢失时的对象键，便于未来对账。
2. 上传成功后锁用户行，再锁视频，重新核对归属并计算账本内当前 ready 文件的总量；替换按净增长计量。旧版改 retired、新版改 ready 在同一事务提交，partial unique index 保证同一逻辑文件只有一个 ready 版本。
3. 上传或发布失败，旧版继续 ready，新记录保留 pending；不因异常擅自删除结果不明的远端对象。SQL 失败对外仅固定错误，日志只记异常类型。
4. 读取必须同时匹配当前用户、视频及 ready 状态；在本次私有目录落地，用完删除缓存。retire 后才允许显式 purge；远端删除响应成功后还要读取确认 404，才把账本标为 deleted。当前 ready 对象不允许直接 purge。

**账本配额只计算 ready 逻辑文件，不统计现有本地文件、pending/retired 远端副本或提供方账单。** 它尚未与现有上传来源配额、业务文件配额和生产暂存容量整合，不能视作完整云端容量限制。超额上传可能留下 pending 物理副本，后续需要有上限的预留和可恢复回收。

## 处理服务的显式接入

- `generate_artifacts(..., object_store=store)` 在原有私有暂存目录生成，验证整组输出后调用 `publish_artifacts`。同一视频/种类最多 100 个不同文件，组大小受阶段上限控制；全部 pending 先持久化，全部上传确认后才原子切换 ready。失败保留旧组和待对账键。
- 生成输出使用完整种类快照：旧组中不再出现的文件名也退休，避免新视频搭配旧语言字幕。兼容的 `publish_artifact` 仍仅替换同名文件，不自动退休其他名称。
- 发布事务在用户/视频锁下核算净增长，并可调用只修改当前 Session 的 SQL 回调；视频/音频引用、转写正文、分析/手工笔记正文随对象组一起提交。回调不得自行提交或进行网络调用；SQL 失败后两者一起回滚，已上传的新键仍 pending。向量同步继续在提交之后，保留原有重试边界。
- `process_video(..., object_store=store)` 持久化 `object://<artifact-uuid>`，不是远端地址或另一实例的缓存路径。视频和 sidecar 按用户/视频/种类/current ready 查询，要求主对象属于该组；逐文件校验后在本次私有目录供字幕和 ffmpeg 使用，音频另行私有落地供 ASR。完成或失败都销毁本次缓存，并恢复 ContextVar 输入目录。
- 组读取再次检查视频归属后才向处理步骤交付路径；有大小/数量边界。它不是在途读取强制撤销机制，也不是并发磁盘容量预留。单次任务同时缓存不同种类的文件，合计空间仍需 R8 统一预留。
- `analyze_video(..., object_store=store)` 和 `update_note_for_user(..., object_store=store)` 使用同一发布接口，保留手工笔记规则；本人 LLM/ASR 配置路径不变。读取笔记正文仍来自 SQL，前端无需看到 bucket、项目指纹或服务端凭证。

这些参数只供可信服务端调用，没有新增浏览器参数、环境模式开关或自动客户端。现有队列 `execute_claimed_task` 和 HTTP 入口仍不注入对象客户端。控制服务端调用方须保证客户端关闭、当前用户/任务归属与既有处理状态/租约；上传来源只能接受已登记对象引用，不能把本地路径当成跨实例来源。测试中的已登记上传对象不代表上传 API 已完成。

缺少客户端时，已知对象引用的处理/笔记服务会拒绝降级为本地。为避免现有配额按本地 Path 漏算，**同一用户禁止混用**：对象发布在预检及用户锁下再次检查已有本地正式文件；本地配额准入检查该用户非 deleted 的对象记录（含未决意图），存在时返回固定 503。未安装账本的本地行为保留。这不是旧文件迁移方案；真实切换须先完成上传来源额度、统一后端选择和迁移/回退，不要通过删账本或改状态绕过保护。

## 显式迁移

模型用独立 `ArtifactBase`，不属于业务 `Base.metadata`，普通启动/create_all 和业务迁移不创建此表。先备份目标库、核对业务迁移，再在受控环境执行：

```bash
cd backend
python -m scripts.prepare_objects          # 返回 2：未连接数据库、未写入
python -m scripts.prepare_objects --apply  # 仅明确准备账本时执行
```

成功版本为独立 `alembic_version_objects=20261105_o002`，业务 head 保持 `20261024_0008`。从 20261104_o001 升级会新增默认 false 的 delete_requested 列与清理索引，保留原有对象。脚本可重复执行，但不验证 bucket，也不启用上传/处理业务存储。迁移开启 RLS，撤销 PUBLIC 及已存在 anon/authenticated/service_role 的表权限，表只供可信后端数据库角色访问；该角色需有实际 SQL 权限，不能依赖客户端 JWT 直接读账本。

账本故意不设级联删除外键，避免视频/用户删除后丢失远端清理键。视频不存在时，用户读取和直接 purge 仍拒绝；可信维护命令只接受受支持删除入口留下的明确意图。回退应用时保留账本和对象；有未完成意图时，002 迁移拒绝降级丢弃该列。不要绕过保护删列/删表或批量删前缀。

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

## 后续接入顺序与真实验收

1. 处理/分析/笔记编辑服务已有显式对象路径；继续上传 API、上传来源额度、持久 Worker/HTTP 的后端工厂与预检，统一模式后再启用。实现旧文件迁移与远端物理容量/预留，解除混用保护必须有对账证据。
2. 视频删除意图与已确认对象的显式重试已接入；继续 pending 结果对账、用户整体删除、无标记旧对象迁移和读取在途边界，不把本命令当成通用垃圾回收。
3. 提供本地旧文件迁移、数量/摘要核对和回退方案，更新部署预检与 readiness；完成后才加入存储模式切换。
4. 使用真实私有 bucket、后端角色和两个账号，验证 API/Worker 跨实例读取、重部署后持久性、服务商失败/删除语义、桶策略与恢复。高权限凭证绕过 Storage RLS，应用归属检查不可省略；桶元数据检查也不能阻止管理员随后将桶改成 public。

当前证据包括真实本地文件、loopback HTTP 和一次性 PostgreSQL；Supabase 响应、用户及角色均为模拟。真实 Supabase 注册/JWT、Storage 网络/API/策略/费用、真实模型调用均未验收，见 [基础核查](VERIFICATION_2026-11-04.md) 、[删除核查](VERIFICATION_2026-11-05.md) 和 [处理服务核查](VERIFICATION_2026-11-06.md)。

协议依据：[Supabase 私有下载](https://supabase.com/docs/guides/storage/serving/downloads)、[API Key 与 secret Key 用法](https://supabase.com/docs/guides/getting-started/api-keys)。
