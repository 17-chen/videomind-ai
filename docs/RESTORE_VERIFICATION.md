# 隔离数据库恢复比对

2026-11-13：结构范围扩展至约束和索引，包含外键动作、延迟属性、CHECK 验证状态及索引运行状态。正常 pg_dump/pg_restore 的 varchar 数组转 text 数组反解析差异有定向兼容，见 [核查](VERIFICATION_2026-11-13.md)。

2026-11-10：R6/R8 子项。`python -m scripts.verify_database_restore` 只读取已经存在的源库和隔离恢复库，不执行备份、恢复、迁移、创建/删除数据库或修复数据。它用于在实际 pg_restore 后核对选定范围，不把“归档目录可读”或“行数相同”当作内容恢复证据。

## 输入与隔离

- 源库使用现有受保护环境中的 `DATABASE_URL`；目标使用独立私有环境变量 `RESTORE_VERIFICATION_DATABASE_URL`。不要把真实连接串写在命令行、Git 或共享日志中。
- 仅支持 PostgreSQL。目标数据库名必须以 `vm_restore_` 开头，且与源库名称不同；即使部署在不同主机，同名也保守拒绝。还会核对连接后的 current_database，避免把源库与自身比较。工具不会创建目标库。
- 两侧连接使用 REPEATABLE READ、READ ONLY 事务，UTC 会话；单条语句超时 15 秒、锁等待 3 秒。数据库连接阶段仍沿用连接串/驱动的超时配置。
- 需要覆盖整张所选表的后端读取权限；若 PostgreSQL 判定当前角色受行级策略过滤，返回 unavailable，防止两个不完整视图被误判一致。不要为运行工具而扩大浏览器角色权限。
- 比对前按 [恢复手册](RECOVERY_RUNBOOK.md) 停止写入并选择同一恢复点。两边是独立快照，工具不能证明没有其他写入，更不能撤回已开始的模型调用。

在配置完私有环境之后运行：

```bash
python -m scripts.verify_database_restore --max-rows 100000 --max-bytes 67108864
```

预算统计两侧合计处理的行/UTF-8 字节，不是每表或每库各一份。超过预算返回 inconclusive，已经完成的局部表结果不能替代整体匹配。流式读取每批 100 行，一批或超大行可能先到达客户端才检查预算；它不是内存硬上限。

## 比对范围与输出

必需业务表：users、videos、transcripts、summaries、embeddings、ai_settings、video_tasks、request_windows。可选范围：三组 alembic_version 表、vm_vector_chunks 和 vm_storage_objects；可选表在两侧都不存在时记为 not_present，仅一侧存在则 mismatch。必需表缺失不能通过。

按列顺序比对名称、PostgreSQL 类型/schema、字符长度/数值及时间精度/collation、可空性、默认值与主键。还比对所选表的约束名称/类型、PostgreSQL 定义及 convalidated 状态，以及索引名称、定义和 valid/ready/live 状态；定义涵盖外键动作、唯一/排斥约束、延迟属性、CHECK、索引表达式/谓词/INCLUDE 和定义中呈现的选项。只读取目录，不执行约束表达式、不重建索引，也不保证原有未验证约束或无效索引可用。

两侧统一 search_path 和字符串设置，SQL 定义按词元比较，字符串和带引号标识符保持原样。PostgreSQL 在实际恢复时会把无长度限制 varchar 字面量数组整体转 text[] 改写为逐元素转 text；仅定向归一化该无损差异。不是通用 SQL 等价证明器：其他等价表达式、更名或跨版本反解析变化仍可能保守报 schema_difference，需人工核对，不能据此自动修复或放宽校验。

随后按主键顺序流式读取 PostgreSQL row_to_json 的原始 UTC 表示，使用带长度边界的 SHA-256 摘要。不会经 Python 浮点解析，避免把高精度 JSON 数值差异舍入成相同。匹配要求行数与摘要均相同；JSON 格式/键顺序变化也可能被视为差异，工具不是语义等价判定器。

只返回固定表名、状态、行数、读取总量及固定原因代码。行正文、用户标识、连接地址、密文、内部摘要、约束/索引名称及定义和异常原文都不返回、不写文件；加密字段参与内容比对但不在此命令中解密。`writes_performed=false` 恒定。

| 状态 | 退出码 | 含义 |
| --- | --- | --- |
| matched | 0 | 选定范围的所有必需/已安装可选表匹配 |
| mismatch | 1 | 存在缺表、列/约束/索引结构或内容差异 |
| inconclusive | 2 | 读取预算不足，未完成全部比对 |
| unavailable | 2 | 未设置目标、目标不满足隔离约束、权限/连接/结构读取失败或不支持的后端 |

没有主键无法稳定排序，返回 unavailable。结构比对不覆盖触发器、函数实现、序列状态、物理存储布局、RLS 策略定义或授权；表达式引用的函数/类型/操作符实现也未比对。拒绝受 RLS 过滤的读取不等于验证恢复后的角色权限正确。非白名单表、Supabase auth/storage 管理表、扩展版本和远端文件内容均不在范围中。

匹配也不证明备份主密钥可解、对象文件可下载、实际身份可登录或问答正确。之后仍须单独运行密钥校验、对象摘要/文件恢复与真实双账号验收，不要直接切换到恢复库或启动可能调用模型的 Worker。

## 可复现的纯合成演练

手动 fixture：`backend/tests/fixtures/restore_probe.py`，只用于全新、无外网、无业务卷的 PostgreSQL/pgvector 测试集群。其 `seed` 会创建固定的 vm_source_probe/vm_restore_probe，已有库会失败而不会覆盖；`exercise` 在核验后故意修改合成目标转写以验证差异检测。这是会写入合成数据的测试 fixture，与上方只读命令分开，不要用真实凭证运行。

本轮用已有 pgvector/pgvector:0.8.7-pg16 镜像、network none 和 tmpfs 建立独立集群；测试后移除整个一次性容器。容器内部步骤：

1. 在挂载的仓库后端目录设置 PYTHONPATH，使用该测试集群的合成 DATABASE_URL 运行 `python tests/fixtures/restore_probe.py seed`。执行三组迁移，建立两个合成账号、转写/笔记、任务、向量、对象账本和一条合成密文。fixture 使用明确的合成测试密钥，不读取或替换应用主密钥。
2. 用测试集群内的同版本客户端 `pg_dump -U vmtest -Fc vm_source_probe -f /tmp/synthetic-recovery.dump`，再对空的合成目标执行 `pg_restore -U vmtest --exit-on-error -d vm_restore_probe /tmp/synthetic-recovery.dump`。归档设为私有权限，留在一次性容器内。
3. `python tests/fixtures/restore_probe.py exercise`：13 表匹配，合成密文校验 verified；随后目标转写被故意改变且行数不变，必须得到 mismatch。

本轮 PostgreSQL 16 合成演练不代表真实 Supabase PostgreSQL 17、用户备份主密钥、远端对象或恢复后权限已经验收。实际环境仍须使用兼容版本客户端和隔离资源，保留原数据库与用户数据。
