# 本地对象归档只读核查

在恢复演练中，使用已导出的对象副本和对应时间点的隔离数据库账本；先按 [恢复手册](RECOVERY_RUNBOOK.md) 停止写入。本工具不创建导出、不执行恢复、不解压归档，也不修改配置、状态、配额或文件。

后端使用已有受保护环境的DATABASE_URL连接目标账本。不要把真实连接串放进命令行；推荐只读可信后端角色。PostgreSQL核查使用READ ONLY事务，若账本或videos受有效RLS过滤会报固定error，不能通过扩大浏览器角色权限来规避。

```sh
python -m scripts.audit_objects --archive-root /srv/vm-restore-export --limit 20 --offset 0 --max-mb 512
```

--archive-root与--verify-remote互斥；不创建Supabase对象客户端，不请求远端对象或模型，但仍读取所配置数据库。默认不带参数的账本汇总行为保留。未安装账本返回not_installed，不访问归档，也不表示备份为空或已验证。

## 目录约定

已展开的目录必须是以下布局，每个文件保持原始对象字节：

```text
<archive-root>/<project_fingerprint>/<bucket>/<object_key>
object_key = users/<user_id>/videos/<video_id>/<kind>/<artifact_id>/<filename>
```

指纹、桶与不可变键都取自账本；使用项目指纹分区，防止多项目同桶名/键互相覆盖。工具不输出这些标识，也不负责生成或重新整理目录。目录内容/权限及导出来源由恢复操作人员确认，不能将任意ZIP解压目录直接认定为此格式。

需要支持dir_fd/O_NOFOLLOW的POSIX系统；已验证Docker/Linux。根目录及其祖先、对象目录、最终文件均拒绝符号链接；根路径不含..。macOS的/tmp、/var常为链接，应使用实际物理路径。特殊文件不按对象正文读取，FIFO非阻塞打开后拒绝；读取时文件大小不符直接mismatch，摘要读取最多声明大小+1字节。记录打开前后及当前同名文件的设备/inode/大小/mtime/ctime/类型变化，发现变化不判匹配。普通读取可能更新atime，不显式更改文件。

## 输出与判定

输出保持writes_performed=false、observations_only=true，verification_target=local_archive，原remote聚合字段改为archive；不会回传目录、文件名、用户/对象ID、摘要、连接信息或异常正文。

matched/absent/mismatch/failed分别表示选定文件字节匹配、缺失、大小/摘要/文件变化不符或读取失败。deleted对象使用deleted_absent/deleted_present。pending即使matched也不发布、不释放额度，整批仍needs_attention。权限拒绝或符号链接等错误计failed，不当成absent。

复用 [对象核查预算](OBJECT_STORAGE.md)：默认UUID顺序20条，最多100条；每条预留声明字节+64KiB，失败和缺失也不归还本批预算。skipped_budget、truncated、并发账本变化或任何异常均needs_attention，退出2；成功选定批次observed退出0。offset非0只证明该位置起的批次；批次之间必须停写，不可把一个批次退出0当作全部验证。

不枚举未登记的额外文件，不验证全部桶清单、源导出的真实性/时点、ACL/RLS策略、账号、主密钥、文件可被真实ASR消费或云端恢复后可下载。未解析压缩包、未联网下载；通过也不是完整恢复验收。数据库结构/内容用 [数据库恢复比对](RESTORE_VERIFICATION.md) 独立验证，真实主密钥可解和恢复后双账号访问仍需单独验收。
