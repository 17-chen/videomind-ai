# 浏览器合成验收

在仓库的 `frontend` 目录运行：

```sh
npm run test:e2e
```

需要 Node.js 22及以上、npm、依赖和浏览器下载网络。Linux还需Chromium系统依赖；CI已运行 `npx playwright install --with-deps chromium --only-shell`。本机macOS ARM64和CI Linux分别记录结果，不把一种环境的通过当作另一种环境的证据。

脚本自动建立系统临时副本、npm ci、下载独立Chromium Headless Shell、运行单元测试、生产build/typecheck/lint，最后启动Next standalone和纯合成HTTP API。无需启动Docker、配置账号或提供Key；不要直接在真实源码目录执行 `playwright test`，配置会拒绝这种调用。3001/8002预览和现有.next不受影响。

副本只包含白名单前端源码/配置，跳过.env、缓存与符号链接；运行环境不继承数据库/服务商凭证，强制空Supabase配置与本机假API。仅使用127.0.0.1:43181/43182，占用时失败，不复用已有服务。浏览器使用临时上下文并阻断其他来源。npm和浏览器安装阶段仍需访问下载站点，可继承下载代理。

覆盖以下真实浏览器行为，业务数据与服务响应均合成：

- 点击处理一次，保持处理锁，从排队到SSR笔记出现无需手动刷新或完整文档重载；完成后按钮恢复且停止任务轮询。
- 后台失败后仅显式点击重试才再次提交，重试完成后笔记出现。
- 排队取消后进入终态，恢复按钮且没有笔记。
- 同一时刻重复提交问答只发送一次请求；编辑草稿不改变回答对应问题；有效编号打开对应视频，未知编号不生成链接。

成功时打印独立报告目录，内含report.json；失败还保留本次副本及截图/trace供诊断。可设 `VIDEOMIND_BROWSER_ARTIFACT_DIR` 指定报告父目录，每次创建独立子目录；CI上传synthetic-browser-report，保留7天。成功只删除本脚本创建的工作副本。浏览器缓存默认在该副本内；CI通过PLAYWRIGHT_BROWSERS_PATH复用专用临时缓存，并禁止清理其他缓存版本。

这些检查证明生产界面与合成协议协作正常，不能替代真实Supabase登录、Whisper转写、本人DeepSeek、真实引用质量、双账号权限或完整恢复验收。运行结果见 [2026-11-19核查](VERIFICATION_2026-11-19.md)。
