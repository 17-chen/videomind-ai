# 2026-11-21 本地对象归档核查

## 本轮实现

R6/R8增加audit_objects --archive-root模式，复用现有只读账本批次/预算/变化检查，独立验证本地已导出对象的大小与SHA-256，绝不上传/删除/发布或释放pending。报告显式标注local_archive，不把本地文件结果叫远端验证。

文件按项目指纹/桶/不可变对象键定位。逐级描述符相对打开且拒绝符号链接（包括归档根祖先），文件非阻塞打开并拒绝特殊文件；声明大小+1字节的有界读取，比较读取前后及同名入口的元数据，替换/变化不判匹配。只读核查新增PostgreSQL有效RLS过滤拒绝，不把有限角色的空结果当完整视图。

详见 [归档说明](OBJECT_ARCHIVE_VERIFICATION.md)。不引入依赖、迁移或业务API变化。

## 检查证据

- 首轮全量488项后端测试/Ruff通过（88.30秒，三组PostgreSQL/pgvector/对象opt-in全部启用，仅已有LangGraph弃用警告）。新增22项覆盖大小/摘要/缺失、空文件、项目分区、根/祖先/中间/最终符号链接、FIFO/目录、读取时同字节替换、状态保留、CLI脱敏及互斥参数、预算不足不打开文件，以及真实PostgreSQL账本+真实合成文件匹配/同长度篡改检出。
- 随后补PostgreSQL受限角色RLS拒绝1项，489项全量及Ruff通过（82.71秒）；最后空路径拒绝新增2项，最终归档/真实PostgreSQL定向75项及Ruff通过（3.81秒）。所有文件/账号/凭证均合成；独立无外网PostgreSQL16/pgvector和临时源码，无.env/业务卷，结束删除本次测试资源。
- 前端未改，本机不重复构建；功能提交 `3d57311` 的 [CI 44866458202](https://github.com/17-chen/videomind-ai/actions/runs/44866458202) 前后端全部通过，包含最终源码的后端pytest/Ruff及固定hash检索，前端21项单元、build/typecheck/lint与4项Chromium用例。

## 边界

真实Supabase后端默认只读核查通过完整视图检查，返回preview：ready=4、pending/retired/deleted=0，ready_without_owned_video=0；remote.enabled=false、attempted=0，writes_performed=false。仅账本聚合，不代表4个对象文件已核验或恢复。

仅复用运行环境的受保护配置执行默认只读账本聚合，未回显或提交配置、未修改主密钥，未打开真实用户备份或对象正文、下载远端对象、调用模型、重跑视频、启动Worker或执行实际恢复；原未跟踪outputs/、backend/:memory:.ses保持原样。只读确认3001/auth与8002 readiness均200，云与旧演示Worker均exited；本轮工具属于显式维护命令，未重启业务服务或同步私有前端源码。

仅验证选定账本条目，不检查未登记文件，不证明备份完整、全局快照一致、角色权限正确或真实完整恢复；pending结果即使匹配也保持待解决。真实数据库/主密钥/对象文件隔离恢复和双账号逐项验收仍待做。
