# 队列与本地磁盘阈值检查

2026-11-10：R8 基础监控子项。`python -m scripts.check_operations` 只读查询队列、目录元数据及文件系统余量，输出聚合 JSON 和退出码；没有恢复任务、删除文件、释放额度或修改数据库的功能。不读取文件正文、密钥密文或服务商配置，不调用模型。

## 运行

普通 Compose 环境：

```bash
docker compose exec -T backend python -m scripts.check_operations
```

当前独立云预览通过启动器加载私有 dotenv，裸 docker exec 不继承启动器写入的进程环境。API 和 Worker 应分别执行，不能假设它们拥有同一暂存磁盘：

```bash
docker --host unix:///Users/chenxin/.colima/default/docker.sock exec videomind-preview-api python -c 'from dotenv import load_dotenv; load_dotenv("/run/secrets/cloud.env", override=True); from scripts.check_operations import main; raise SystemExit(main([]))'
docker --host unix:///Users/chenxin/.colima/default/docker.sock exec videomind-preview-worker python -c 'from dotenv import load_dotenv; load_dotenv("/run/secrets/cloud.env", override=True); from scripts.check_operations import main; raise SystemExit(main([]))'
```

这些命令不输出 dotenv 内容。当前路径仅适用于本机预览；目标部署应通过受保护环境配置运行同一 Python 模块。

## 阈值与状态

| 参数 | 默认 | 触发条件 |
| --- | --- | --- |
| `--max-queued-seconds` | 300 | 有排队任务且最老等待时间严格超过该值 |
| `--max-expired-leases` | 0 | 运行中且租约已经过期的任务数严格超过该值 |
| `--max-failures-last-hour` | 0 | 最近一小时结束的失败任务数严格超过该值 |
| `--min-free-mb` | 当前 `MIN_MEDIA_FREE_SPACE_MB`，应用默认 1024 | 任一被检查本地文件系统的可用空间严格低于该值 |

MB=1024×1024 字节。允许非负整数；负数参数在读取前拒绝。最大值为 0 表示不容许正数，并非关闭检查。磁盘最小值为 0 不触发低余量告警，但仍要求能读取磁盘信息。按部署的正常等待时间、失败量和磁盘预算调整阈值，不把预览的 128 MiB 阈值当作生产建议。

| `status` | 退出码 | 含义 |
| --- | --- | --- |
| `ok` | 0 | 本次选定检查均可读取，且没有超阈值 |
| `attention` | 1 | 数据可读取，但至少一个阈值超限 |
| `unavailable` | 2 | 至少一项无法核对；即使其他项同时告警，也不能当作健康 |

`checks.queue` 包含已有队列聚合字段，`checks.local_disk` 包含检查的文件系统数量、读取错误数及最小可用字节。`alerts` 使用固定代码：`queue_wait_exceeded`、`expired_leases_exceeded`、`recent_failures_exceeded`、`local_disk_free_below_minimum`。`unavailable` 使用 `queue_read_failed` 或 `local_disk_read_failed`，不返回异常原文、地址、路径或身份。`mutations_performed=false` 恒定。

数据库不可读时仍检查磁盘；某目录不可读时保留其他成功检查及低空间告警。video/audio/transcript/note 配置目录按文件系统设备去重；尚未创建的目录检查最近存在的父目录，不创建目录。配置位置为普通文件、断开的符号链接、无法读取或没有任何可检查根时标记 unavailable。此命令只检查容量，不扫描目录下的业务文件。

## 处理与边界

- 排队过久或租约过期：先核对 Worker 状态和脱敏任务日志，结合 [队列记录](VERIFICATION_2026-10-26.md) 判断；命令不会重领、取消或重跑任务，尤其不能据此重试可能已计费的阶段。
- 近期失败：用请求/任务关联日志定位类型，修复配置或资源后再决定重试；已结束一小时以上的失败不触发此项，但总 failed 数仍保留在快照中。
- 低余量：结合 [磁盘只读对账](STORAGE_MONITORING.md) 和 [临时空间边界](TEMPORARY_STORAGE.md) 核对，不凭文件年龄、数量或本次告警直接清理。
- unavailable：按数据库/文件系统检查状态排查；不能把读取失败当成空队列或充足空间，也不能自动切换到其他用户密钥或更宽松的数据源。

当前只是按需运行的检查入口，未接生产调度、通知、日志汇聚或告警去重。没有向外部监控服务发送数据。后续可由部署监控读取退出码和固定 JSON 代码；这不代表本轮已配置持续监控。

队列与磁盘不是同一时刻的原子快照，不保证未来的磁盘余量；不包含全局空间预留、远端对象配额、数据库磁盘、模型缓存、API/Auth 可用性、模型质量或 Worker 活性证明。路径检查只查询配置目标的文件系统，不提供并发路径替换的原子安全保证，不能据此扩展为删除器。云预览 API/Worker 各有独立 tmpfs，必须分别运行，容器视图不能代替宿主机监控。
