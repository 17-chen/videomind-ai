# 私有对象传输与文件账本基础

2026-11-04：R6 的基础层已实现并通过隔离验证，**尚未接入上传、Worker、编辑/下载和视频删除业务入口**。当前文件仍写本地，设置下列参数不会自动切换业务存储；当前 API/Worker 仍不能放在两块独立 Render 磁盘上运行。

## 当前实现

- `app/services/object_storage/supabase.py` 使用已有 httpx，通过 Supabase Storage REST 上传、读取、删除私有对象。每次操作先读取 bucket 元数据，拒绝 public bucket；不自动建桶，不生成公开或签名链接。
- 服务端配置为 `SUPABASE_URL`、`SUPABASE_STORAGE_SERVICE_KEY`、`SUPABASE_STORAGE_BUCKET`（默认 `videomind-private`）。现代 `sb_secret_` 只放 `apikey`；旧 service_role JWT 同时使用 Bearer。拒绝公开 Key、不跟随重定向、不使用环境代理。生产只允许 HTTPS；仅测试显式开放 loopback HTTP。密钥只进后端私有环境，禁止放入 `NEXT_PUBLIC_*`，禁止提交真实值。
- 此凭证用于平台文件存储，与用户本人 LLM/ASR Key 无关；不改变已认证用户的密钥隔离规则。由于存储凭证有高权限，应用层必须先核对当前用户和视频归属。
- 账本对象键形如 `users/<user>/videos/<video>/<kind>/<artifact-uuid>/<video>.<extension>`；只接受服务端规范 UUID 与安全文件名。每次发布分配新对象键，`x-upsert=false`，不覆盖旧对象。账本还保存 bucket、项目指纹、字节数和 SHA-256，拒绝切错项目后读取同名对象。
- 上传逐块校验实际大小/摘要；下载在私有暂存目录逐块校验后才替换目标，失败清理本次临时文件，保留已有目标。拒绝符号链接源文件与目标，使用已有阶段大小和磁盘余量限制。分块 64 KiB，socket 读超时 30 秒、连接 10 秒、传输检查点预算默认 300 秒；检查点预算不是精确的全程硬截止或并发磁盘预留。

## 账本状态和事务

`pending → ready → retired → deleted`，没有自动后台清理或旧版恢复入口。

1. 用专用、无待提交业务改动的 Session 核对视频归属、测量文件，先提交 pending 记录，再上传。这保留进程故障或响应丢失时的对象键，便于未来对账。
2. 上传成功后锁用户行，再锁视频，重新核对归属并计算账本内当前 ready 文件的总量；替换按净增长计量。旧版改 retired、新版改 ready 在同一事务提交，partial unique index 保证同一逻辑文件只有一个 ready 版本。
3. 上传或发布失败，旧版继续 ready，新记录保留 pending；不因异常擅自删除结果不明的远端对象。SQL 失败对外仅固定错误，日志只记异常类型。
4. 读取必须同时匹配当前用户、视频及 ready 状态；在本次私有目录落地，用完删除缓存。retire 后才允许显式 purge；远端删除响应成功后还要读取确认 404，才把账本标为 deleted。当前 ready 对象不允许直接 purge。

**账本配额只计算 ready 逻辑文件，不统计现有本地文件、pending/retired 远端副本或提供方账单。** 它尚未与现有上传来源配额、业务文件配额和生产暂存容量整合，不能视作完整云端容量限制。超额上传可能留下 pending 物理副本，后续需要有上限的预留和可恢复回收。

## 显式迁移

模型用独立 `ArtifactBase`，不属于业务 `Base.metadata`，普通启动/create_all 和业务迁移不创建此表。先备份目标库、核对业务迁移，再在受控环境执行：

```bash
cd backend
python -m scripts.prepare_objects          # 返回 2：未连接数据库、未写入
python -m scripts.prepare_objects --apply  # 仅明确准备账本时执行
```

成功版本为独立 `alembic_version_objects=20261104_o001`，业务 head 保持 `20261024_0008`。脚本可重复执行，但不验证 bucket，也不启用业务存储。迁移开启 RLS，撤销 PUBLIC 及已存在 anon/authenticated/service_role 的表权限，表只供可信后端数据库角色访问；该角色需有实际 SQL 权限，不能依赖客户端 JWT 直接读账本。

账本故意不设级联删除外键，避免视频/用户删除后丢失远端清理键。当前视频不存在时，用户读取和删除都拒绝；管理员对账/墓碑清理尚未提供，**不能先删业务记录再期待这层自动回收对象**。回退应用时保留账本和对象，勿直接降级删表或批量删前缀。

## 后续接入顺序与真实验收

1. 为上传、URL/音频/文本生成、笔记编辑和文件读取接入同一文件寻址及发布接口；Worker 任务只持久化对象身份，不依赖另一实例的缓存路径。统一现有配额和远端预留。
2. 视频删除先持久化清理意图，再协调账本、向量、业务记录；补失败重试、pending/retired 对账和有证据的垃圾回收，处理删除与在途读取/写入的竞态。
3. 提供本地旧文件迁移、数量/摘要核对和回退方案，更新部署预检与 readiness；完成后才加入存储模式切换。
4. 使用真实私有 bucket、后端角色和两个账号，验证 API/Worker 跨实例读取、重部署后持久性、服务商失败/删除语义、桶策略与恢复。高权限凭证绕过 Storage RLS，应用归属检查不可省略；桶元数据检查也不能阻止管理员随后将桶改成 public。

当前证据包括真实本地文件、loopback HTTP 和一次性 PostgreSQL；Supabase 响应、用户及角色均为模拟。真实 Supabase 注册/JWT、Storage 网络/API/策略/费用、真实模型调用均未验收，见 [本轮核查](VERIFICATION_2026-11-04.md)。

协议依据：[Supabase 私有下载](https://supabase.com/docs/guides/storage/serving/downloads)、[API Key 与 secret Key 用法](https://supabase.com/docs/guides/getting-started/api-keys)。
