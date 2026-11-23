# 2026-11-23 对象清理完整视图保护

## 本轮实现

R6/R8 对象维护共用 PostgreSQL 完整视图检查。此前只读 audit_objects 已拒绝有效 RLS 过滤视图，cleanup_objects 的预览和执行尚未检查；若维护角色看不到仍存在的视频，旧删除意图可能被误选为可清理对象；若看不到账本，则可能误报无积压。

现在预览及每次选取清理对象的事务均检查 vm_storage_objects 与 videos 的有效 RLS，受限即停止。不会关闭 RLS、改变角色或授予权限；普通 API/Worker 和用户隔离规则保持现有行为。CLI 复用固定 object_cleanup_failed 输出，初始检查失败不创建云对象客户端；之前事务已执行过删除时，继续保留 writes_may_have_occurred=true 的既有语义。

共用检查同时用于只读归档/远端核查，不引入依赖、配置、迁移或自动清理。

## 检查证据

- 无外网、无业务卷的一次性 PostgreSQL 16/pgvector 与临时后端源码副本中运行 `python -m pytest -q`：501项通过（84.87秒），三组PostgreSQL opt-in全部启用。仅既有LangGraph弃用警告。结束只移除本次测试容器和临时副本。
- `ruff check app tests scripts` 通过；`git diff --check` 通过。
- 新增10项回归：账本/视频分别受限 × 预览/执行/CLI预览/CLI执行，共8项；初始预览后及首个删除提交后切入受限角色，共2项。真实存在的视频、对象和删除意图保留；初始受限不创建provider，后续受限不继续删，之前已确认删除保留。
- 前端未改，本机未重复构建；功能提交 `fa7c1e3` 的 [CI 45207598215](https://github.com/17-chen/videomind-ai/actions/runs/45207598215) 前后端全部通过，含后端pytest/Ruff/固定hash检索、前端单元/build/typecheck/lint及Chromium生产界面合成验收。

## 边界与下一步

全部数据库角色、视频、对象内容和传输均为合成数据。真实 PostgreSQL 权限/事务参与测试，Supabase 对象删除为内存替身；不是实际云端删除或完整恢复验收。不访问真实用户备份/对象正文、变更主密钥、调用模型、重跑视频或启动 Worker。现有预览服务未重启，前端未改，不需同步私有源码副本。

本次只补维护角色视图保护，不解决 pending、旧文件迁移、并发空间预留或真实恢复。管理员在检查后同事务内并发修改权限/策略不受此预检查完全保护，维护时仍应冻结角色/策略和恢复写入。未自动扩大角色权限。真实双账号详细隔离、本人模型问答及隔离恢复继续待验收。原未跟踪 outputs/ 和 backend/:memory:.ses 保留。
