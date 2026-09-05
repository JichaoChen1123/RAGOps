# 阶段 3 浏览器 API 模式检查表

前置条件：阶段 2 后端与前端已经集成到同一 SHA；后端使用独立 SQLite，`RAGOPS_MODEL_EXECUTION_ADAPTER=mock`，`RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false`；前端使用 `VITE_API_MODE=api` 和本地后端地址。

## 操作和期望

| ID | 输入与操作 | 期望结果 |
| --- | --- | --- |
| B01 | 桌面视口 1440×900 打开项目前端 | 同时显示“前端 API / 后端 mock / 提供方未配置或已配置未验证”；不得显示真实已验证 |
| B02 | 在数据集页导入产品内置的 2.0 人工示例并发布；另用 `examples/offline-readiness/valid-v2.jsonl` 跑 API 脚本 | 页面 12 条、脚本 3 条均成功；版本、样本数和 SHA-256 可见；无静默 mock fixture 替换 |
| B03 | 创建 mock 评测任务并进入报告 | 显示“执行成功 / 质量未评估 / 分数未知”；不得显示 100 或 passed |
| B04 | 打开首条样本 | 参考答案、历史回答、本次回答、`provided` 上下文和引用分别展示；未知 Token/成本显示未知 |
| B05 | 刷新报告和样本页 | ID、回答、运行快照和报告仍存在，数据来自 API |
| B06 | 停止并重启后端，再刷新 | 同一任务与报告仍可读取；不得回退前端 mock 数据 |
| B07 | 停止后端后刷新页面 | 显示明确 API 错误与重试入口；不得显示成功或旧 mock 数据 |
| B08 | 移动视口 390×844 重复报告与样本下钻 | 无空白页、关键状态不被遮挡、横向内容可读或可滚动 |

## 浏览器内存 HTTP 辅助页

后端运行时，可用静态服务器打开 `browser-api-loop.html`，从真实浏览器执行创建、导入、发布、运行、报告和导出请求：

```powershell
python -m http.server 4173 --directory tests/acceptance/offline-readiness
```

打开 <http://127.0.0.1:4173/browser-api-loop.html>。页面结果必须为“通过”，浏览器 Network 面板中所有业务请求都指向本地 RAGOps 后端。该辅助页同时验证浏览器 CORS，但不替代产品前端 B01–B08，也不替代 PowerShell API 闭环。

## 产品前端自动检查

后端使用 `8000`、Vite 使用 `5173` 时：

```powershell
$env:RAGOPS_FRONTEND_URL = 'http://127.0.0.1:5173'
$env:RAGOPS_BROWSER_OUTPUT_DIR = (Resolve-Path docs/qa/screenshots/offline-readiness).Path
$env:RAGOPS_BROWSER_STATE = Join-Path $env:RAGOPS_BROWSER_OUTPUT_DIR 'browser-api-evidence.json'
npm --prefix frontend run acceptance:offline-browser -- create
```

停止并使用同一 SQLite 重启后端后：

```powershell
npm --prefix frontend run acceptance:offline-browser -- restart_recheck
```

最后停止后端、保持前端运行，验证断连态：

```powershell
npm --prefix frontend run acceptance:offline-browser -- disconnected
```

脚本只允许浏览器访问 `localhost`/`127.0.0.1`，出现外部 HTTP(S) 请求会立即阻断并失败。每个阶段都覆盖前一阶段的 JSON 状态文件；必须按顺序执行。语义错误、非断连阶段 console error 或外部请求都会产生非零退出码并保留证据。执行结束后只停止本次启动的后端/前端 PID。

## 证据记录

记录集成 SHA、浏览器和版本、桌面/移动视口、数据集 ID、任务 ID、`invoke-api-loop.ps1` 输出、重启前后结果及失败项。截图只用于布局和状态补充，不能单独作为 API 端到端证据。
