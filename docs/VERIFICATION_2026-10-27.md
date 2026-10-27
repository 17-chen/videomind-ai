# 2026-10-27 核查记录：用户密钥恢复校验

- 新增只读命令 `python -m scripts.verify_key_recovery`。默认使用当前配置的 Fernet 主密钥，也可从权限 `0600` 的普通文件读取备份密钥。遍历 `ai_settings` 的模型与 ASR 两类密文并尝试解密，只输出总数与状态；错误不包含用户 ID、密钥、密文或明文。
- 两项隔离 SQLite 测试使用临时生成的 Fernet 密钥与合成用户配置，覆盖两类密文、错误密钥、私有文件权限和空库的 `inconclusive` 结果。它们不代表真实用户密钥或正式数据库恢复通过。
- 本机运行中的 PostgreSQL 只读检查返回 `{"status":"inconclusive","settings_rows":0,"encrypted_values_checked":0}`，退出码 2：当前没有真实用户加密配置，无法从本机数据证明主密钥可恢复。未改动现有主密钥、用户设置或数据库。
- 本地 Colima 后端完整回归为 **96 passed、1 个既有 LangGraph 待弃用提示**；`ruff check app tests scripts` 通过。前端代码未改，本机未重跑前端构建；GitHub Actions 仍以本轮提交实际运行结果为准。备份、隔离恢复、轮换与真实用户密钥验收仍待实际演练；操作边界见 [恢复手册](RECOVERY_RUNBOOK.md)。
