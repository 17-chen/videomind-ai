# 2026-11-27 队列监控完整性

## 实现

R8只读队列快照新增running租约不完整及未知任务状态聚合，check_operations发现任一异常直接attention；过期边界包含等于检查时刻。PostgreSQL使用干净专用Session、READ ONLY REPEATABLE READ、固定public表与有效RLS拒绝，结束rollback，避免受限视图/混合时点/自动flush误报健康。task_queue_status失败固定脱敏JSON/退出2；成功仍仅为原始快照，不代替运营健康退出码。

没有新依赖、迁移、模型调用、自动修复/重试/取消或生产调度。详见 [监控说明](OPERATIONS_MONITORING.md)。

## 验证

初版28项定向测试通过；修正测试函数的Lint写法后，干净检出中的 `python -m pytest -q` 全量598项通过（92.16秒），三组PostgreSQL opt-in全部启用，`ruff check app tests scripts` 与差异格式检查通过，仅既有LangGraph弃用警告。前端未改，本机未重复构建；功能提交 `e13451e` 的 [CI 45993381017](https://github.com/17-chen/videomind-ai/actions/runs/45993381017) 前后端全部通过，含pytest/Ruff/固定hash检索、前端单元/build/typecheck/lint及Chromium生产界面合成验收。新增17项覆盖五种缺失/空白租约、未知状态脱敏、截止边界、三种脏Session拒绝、CLI聚合/脱敏、真实PostgreSQL下快照/运营/CLI的RLS拒绝及并发插入下一致只读快照。

## 工作区与边界

原仓库50个已跟踪文件及374个Git元数据文件带iCloud dataless标记，普通Git检查/读取持续阻塞，部分读取SIGBUS；系统Foundation下载请求已接受但尚未完成。未覆盖占位文件、重置索引、清理数据卷或读取outputs/和backend/:memory:.ses。原目录完整可读内容之外的差异无法核查，不据此认定工作树干净。

已通过GitHub HTTPS API核对远端main为65dda5c；在独立/private/tmp/videomind-clean-20261127克隆同一仓库，复制本轮明确改动。其他可读的已跟踪文件与干净检出比较无差异。验证对象是GitHub基线加本轮改动，不能代表未恢复的本地占位文件；CI另行验证同步提交。原目录同步保存本轮源码/文档，Git提交在临时检出完成，原目录Git历史/索引未强行更新，后续恢复iCloud可读性后须再核对并合入，禁止直接覆盖或reset。

测试仅使用独立无外网PostgreSQL16/pgvector、合成用户/任务和临时源码，无业务数据卷/私有配置。现有预览未重启、Worker未启动，未改主密钥、调用服务商或重跑真实视频。真实双账号、模型、完整恢复及生产持续监控仍未验收。
