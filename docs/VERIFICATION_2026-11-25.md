# 2026-11-25 离线用户密钥轮换工具

## 本轮实现

R8新增rotate_user_keys CLI与独立服务：默认只读全量预检；显式执行要求PostgreSQL与操作者确认已停止全部API/Worker。旧/新Fernet密钥必须不同，从私有普通文件有界读取，不接收命令行密钥值、不生成/安装主密钥或改环境配置。锁定public.ai_settings、拒绝有效RLS过滤，先验证全部源密文，再统一重加密并重新读取核对，单次提交，提交前失败整体回滚。超预算不轮换部分数据，空库inconclusive。详见 [操作与回退](KEY_ROTATION.md)。

不增加依赖、迁移或业务API变化。应用仍只有一个主密钥，本人配置/不回退所有者的规则不变。仅显式维护工具写数据库；本轮没有对真实数据执行该工具。

## 检查证据

- 初版38项定向检查与Ruff通过；随后首轮全量539项/Ruff通过（90.01秒）。最终补充提交确认丢失和public搜索路径保护后，完整 `python -m pytest -q` 541项通过（90.45秒），`ruff check app tests scripts` 与 `git diff --check` 通过；仅已有LangGraph弃用警告。
- 新增40项检查覆盖两用户模型/ASR与NULL保留、应用读取新密钥、默认无UPDATE、坏钥/坏密文/空库/预算/脏会话、私有文件权限与符号链接/FIFO/超大/缺失/非ASCII拒绝、固定脱敏输出；真实PostgreSQL验证SQL故障与触发器替换正确新钥token时整体回滚、RLS部分视图拒绝、并发插入/修改/删除/第二轮换被表锁阻挡，以及同名影子表不被改动。
- 真实数据库commit后模拟确认丢失，CLI退出1、writes_may_have_occurred=true，数据库全量仍可由新密钥解密，文件/配置未改；没有将失败误报为未写入。
- 三组PostgreSQL/pgvector/对象opt-in全部启用。前端未改，本机未重复构建；推送后通过CI复核前后端、Chromium与固定hash检索，结果另补。

## 运行与验证边界

本轮开始Colima未运行，复用现有2 CPU/4GB环境恢复；其既有frontend/API随Docker策略恢复，未重建服务或改配置。只读确认云Worker、旧Worker及归档Worker均exited；未启动Worker、重跑视频或调用模型。仅在无外网、无业务卷的一次性PostgreSQL16/pgvector容器中使用合成用户与密钥测试，退出清除本次测试资源，现有数据卷不变。

SQL故障/触发器/锁/RLS使用真实隔离PostgreSQL；提交确认丢失为在实际commit之后抛异常的故障模拟，不冒充真实网络断线验收。真实用户密钥未读取、变更或轮换，未回显/提交私有配置，未做真实模型计费或恢复验收。原未跟踪outputs/和backend/:memory:.ses保留。

本工具不保证操作者已停止服务、备份可恢复、目标库正确或部署新主密钥切换成功；读者不被表锁阻挡，不能在线使用。提交确认丢失时仍可能已提交，失败输出保守标注writes_may_have_occurred=true，必须停写后只读核验再决定配置。R8真实轮换/完整恢复、全局临时空间和生产限流/监控仍未完成，R2/R7真实本人模型/双账号仍待验收。
