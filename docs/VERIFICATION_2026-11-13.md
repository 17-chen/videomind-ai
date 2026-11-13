# 2026-11-13 恢复结构比对

## 范围与结果

从 main `d720a77` 恢复并 fetch，起点与 origin/main 一致，上轮 CI 43165469017 成功。保留原未跟踪 outputs/ 和 backend/:memory:.ses，不读取或清理。本轮继续无需第二账号的 R6/R8 恢复验收基础工作。

原工具仅比较列、主键和精确行内容。现在增加所选表的约束名称/类型、PostgreSQL 定义及验证状态，以及索引名称、定义和 valid/ready/live 状态；缺失或不同返回 schema_difference，不读取正文来掩盖结构差异。定义包含外键动作、唯一/CHECK、延迟属性和索引谓词/表达式/INCLUDE。目录读取沿用只读 REPEATABLE READ、查询/锁等待时限及脱敏报告，不创建或修复对象、不执行定义。

## 实际演练发现与修复

首轮真实 pg_dump/pg_restore 显示：PostgreSQL 16 会把 varchar 字面量数组整体转 text[] 改写成逐元素转 text，影响已有 video_tasks 部分索引与 vm_storage_objects CHECK。单纯比较反解析 SQL 会把正常恢复误报为结构差异。

修复统一会话 search_path/字符串设置，按 SQL 词元比较定义；只定向归一化无长度限制 varchar 字面量数组转 text[] 的无损改写，字符串和带引号标识符作为完整词元保留。其他表达式、更名、不同谓词和有长度限制的转换不忽略。该实现不是任意 SQL 语义等价判定器；其他反解析变化仍可能保守报差异，需人工核查。

## 验证证据

功能 `ba07ed9` 已同步 GitHub，[CI 43350954201](https://github.com/17-chen/videomind-ai/actions/runs/43350954201) 前后端及固定检索检查全部通过。一次性测试集群及其中归档已移除；原未跟踪文件保留。

- 新增13项：10种数据不变而结构丢失/改变场景，2种数据库实际反解析再解析的 CHECK/部分索引场景，1项词元保护回归；恢复比对模块共27项测试。
- 最终源码全量 **410项后端测试**、`ruff check app tests scripts` 通过。无外网 PostgreSQL/pgvector 16 一次性容器，源码复制到 tmpfs，三组 PostgreSQL/pgvector/对象 opt-in 测试启用；仅已有 LangGraph 弃用警告。
- 同一隔离集群中按 restore_probe fixture 执行三组迁移、合成两账号与13表；同版本真实 pg_dump/pg_restore 后，13表匹配，两侧共26行/7498字节；合成密文1条校验 verified。随后仅改变目标转写正文、行数不变，准确返回 mismatch。归档只在一次性容器中，未使用真实配置或应用主密钥。
- API 8002 readiness 与前端3001 /auth 均 HTTP 200。离线工具改动无需重启服务，未入队/重跑视频、下载真实媒体或调用付费模型。前端未修改，本地不覆盖开发构建目录；前端检查由 GitHub CI 执行。

## 未验收边界

触发器、函数/操作符实现、序列状态、物理布局、RLS 策略/角色权限、非白名单表与远端对象文件不在该比对范围；相同的未验证约束/无效索引不证明可用。匹配不代表真实 Supabase PostgreSQL 17、真实用户备份、现有主密钥与对象文件恢复成功。真实双账号、完整自动更新浏览器过程、问答引用质量、下载合并/并发空间预留仍待完成，不勾选 R6/R8 整项。
