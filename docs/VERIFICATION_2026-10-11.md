# 2026-10-11 运行与功能核查

本记录区分本机实测、模拟外部依赖的测试和仍需真实账号/服务的验收。运行环境为 Colima Docker Compose；未记录任何密钥值。

| 范围 | 结果 | 证据与边界 |
| --- | --- | --- |
| 后端测试 | 29 项通过 | `python -m pytest -q`；下载、Supabase Auth、模型与向量服务在相关测试中使用替身 |
| 后端静态检查 | 通过 | `ruff check app tests`；修复 ORM 类型注解缺少导入的 7 处错误 |
| 前端 | 通过 | 隔离副本执行 `npm run typecheck`、`npm run lint`、`npm run build` |
| 数据库迁移 | `20261008_0004 (head)` | 运行中 PostgreSQL 上执行 `alembic current` |
| 服务就绪 | 200 | VideoMind `GET http://localhost:8001/api/v1/health/ready`，响应标识 `service=VideoMind AI`，数据库与向量库均为 `ok` |
| 页面 | 200 | `/`、`/auth`、`/dashboard`、`/library`、`/chat`、`/settings`、现有视频详情 |
| 视频基本操作 | 通过 | 在本地 demo 新建独立测试记录，验证列表和详情，随后删除；原有记录数恢复 |
| 模型设置 | demo 限制正常 | 读取设置 200；demo 保存个人 Key 被拒绝 403 |
| 空知识库问答 | 200 | 当前 Chroma 记录数为 0，问答返回无来源结果；未发起付费模型调用 |
| 无字幕处理 | 模拟测试通过 | 无转写 Key 时在提取音频前失败；有 Key 时模拟提取和转写成功 |
| 登录用户与自己的模型 | 模拟测试通过 | API 级测试覆盖个人 Key 加密、视频一键入库、本人问答引用和跨用户隔离 |
| 视频删除 | 测试及本地冒烟通过 | 越权、处理中和向量故障均有测试；本地仅删除本轮新建的测试记录 |

## 本机端口冲突

2026-10-11，本机另一个 Python 项目监听 `127.0.0.1:8000`，因此访问 `localhost:8000` 得到的不是 VideoMind。VideoMind 容器内路由正常。已在**Git 忽略的本地 `.env`** 中设 `API_PORT=8001` 与 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1`，重建前后端容器；Docker 内部 `INTERNAL_API_BASE_URL=http://backend:8000/api/v1` 不变。端口配置不含密钥且不提交 Git。今后检查前应确认 OpenAPI 中存在 `/api/v1/videos`，不能仅凭 `/health/ready` 返回 200 判断服务身份。

## 尚未实测

- 真实 Supabase 项目的注册、登录、刷新和两个真实账户的数据/模型账单隔离；当前 `.env` 未配置 Supabase。
- 真实 Bilibili/抖音视频下载、字幕或无字幕转写，以及真实 DeepSeek/OpenAI 调用和计费。
- 真实视频的分析、向量检索质量和回答来源准确性；当前 `local_hash` 只验证流程。
- 后台任务跨进程重启恢复，以及多实例部署下的删除与文件清理。

这些能力不能仅凭页面 200 或模拟测试标记为已验收。
