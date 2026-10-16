# VideoMind AI 开发指引

## 恢复上下文

新会话先读取 `PROJECT_HANDOFF.md`、`PROJECT_CONTEXT.md`、`docs/COMPLETION_PLAN.md` 和 `TODO.md`，再核对 Git 状态与最近提交。需要架构细节时读 `docs/architecture.md`、`DECISION_LOG.md`。历史聊天不作为唯一项目记忆。

事实优先级：当前源码与实际验证 > Git 历史 > 有日期的核查记录 > 历史规划。区分“代码已实现”“模拟测试通过”和“真实服务已验收”；不要把旧工作树快照当作当前状态。

## 实现与权限

- 保留 Next.js + FastAPI + SQLAlchemy 架构和用户已有改动，按当前用户请求推进；历史发布偏好不替代新聊天的发布授权。
- 使用中文交流，说明实际结果和未验证边界；可以独立完成的常规开发与检查直接推进。
- 已认证用户的分析、问答和云端转写只读取本人的配置，禁止缺 Key 时回退到项目所有者的密钥。
- 不输出或提交 `.env`、API Key、用户令牌、Cookie、私钥和真实用户资料；不擅自轮换或重新生成现有加密主密钥。
- 不用 reset、清理数据卷或覆盖文件来处理未知状态。GitHub 同步遵循当前授权，先核对远端，保留并行更新，不强制推送。
- 从 ChatGPT 项目镜像接入时，`sources/` 是只读参考，业务修改应落在真实 Git 仓库中。

## 验证与记录

- 按改动风险运行相关测试；后端命令为 `python -m pytest -q` 和 `ruff check app tests scripts`，前端为 `npm run typecheck`、`npm run lint`、`npm run build`。
- 本机 Docker 使用 Colima，地址和预览端口见交接文档。前端生产构建使用临时副本，避免覆盖正在运行的开发构建目录。
- 检索评测使用 `python -m scripts.evaluate_retrieval`；虚构语料结果不能替代真实 BGE、ASR、Supabase 和服务商验收。
- 重要任务完成后更新 CHANGELOG、TODO 和项目上下文；只有有证据的任务才勾选完成。长期技术选择记录在 DECISION_LOG。
