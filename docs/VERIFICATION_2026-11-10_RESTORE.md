# 2026-11-10 恢复比对工具与合成备份演练

起点 `a130734` 与远端一致，上一轮 [CI 42745277669](https://github.com/17-chen/videomind-ai/actions/runs/42745277669) 前后端通过。本轮推进 R6/R8 可独立开发的恢复验收工具；未访问真实备份、用户正文或现有主密钥，未重跑视频或调用模型。

## 实现

新增只读 `verify_database_restore` 命令：比较既有源库与不同名的 vm_restore_ 隔离目标；只读 repeatable-read 快照、固定 13 表范围、列/主键结构与流式精确行摘要。来源权限受到 RLS 过滤、目标不满足隔离要求、连接异常或读取不完整时不返回 matched；返回聚合状态和退出码，不输出正文、密文、内部摘要或异常原文。预算同时覆盖源/目标读取，单语句和锁等待均设超时。没有自动创建、备份、恢复、删除或切换数据库的功能。

范围、用法和实际恢复的后续关口见 [说明](RESTORE_VERIFICATION.md)。

## 检查

- 新增 13 项测试，覆盖真实 PostgreSQL 的内容匹配、同数量内容变化、高精度 JSON 数值变化、列/迁移版本/缺表差异、行/字节预算、拒绝自身比较、只读事务、无主键/异常脱敏、RLS 过滤拒绝及 CLI 缺目标/无效 URL/无效预算。
- 当前源码 `python -m pytest -q` 全量 393 项通过，`ruff check app tests scripts` 通过；三组 PostgreSQL opt-in 检查开启，使用无外网的一次性 PostgreSQL/pgvector 与临时源码副本。身份、ASR、对象服务和模型响应仍为替身，既有真实 SQL/本地媒体检查一并通过。仅原有 LangGraph 弃用警告。
- 首次针对性检查发现流式选项污染连接后续语句，改为单条 execute 的作用域后通过。又保留原始 row_to_json 表示作摘要，避免 JSON 浮点解析把真实数值差异舍入；对应回归通过。Colima 不共享宿主 /tmp，初始演练脚本改用标准输入，之后保存为可复现 fixture；只读挂载的 Ruff 使用 --no-cache 检查通过。
- 本轮未修改前端或业务 API/Worker，不重启预览；前端由 GitHub CI 覆盖。

## 真实客户端、纯合成数据演练

在一次性 PostgreSQL 16/pgvector 集群中执行三组实际迁移，建立两名合成用户、转写/笔记、任务、向量、对象账本和一条合成密文。用真实 pg_dump 自定义格式归档，再用 pg_restore 恢复到独立目标：

- 13 张白名单表的选定列/主键结构与内容全部 matched，两侧合计读取 26 行、7498 字节。
- 恢复后合成密文可解：settings_rows=1、encrypted_values_checked=1、verified。
- 故意仅修改目标转写正文，保持 source_rows=restored_rows=1，工具得到 mismatch。CLI 同场景退出 1，max-rows=1 时返回 inconclusive/退出 2。
- 演练 fixture 已保存在 tests/fixtures/restore_probe.py；它只操作新建合成数据库，exercise 会故意修改合成目标，与只读产品命令区分。

没有使用真实用户备份、真实模型、真实 Supabase 对象文件或现有主密钥；原有业务容器/数据卷未改动。原未跟踪 outputs/、backend/:memory:.ses 保留，不读取、不提交、不清理。

## 尚未验收

真实 PostgreSQL 17 备份与兼容客户端、真实用户主密钥备份、对象内容/文件恢复、RLS/角色权限、身份登录和索引/问答均需独立验收。该工具只证明两个选定数据库快照的指定范围一致，不验证完整权限、索引/外键/函数/序列、Supabase 管理 schema 或远端文件。合成恢复成功不能勾选 R6/R8 整项完成。
