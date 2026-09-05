# RAGOps 前端 MVP

React + TypeScript + Vite 实现的 RAGOps 工程工作台。默认使用内置脱敏 fixture，可演示“评测任务 → 报告 → 样本诊断 → 检索与引用证据”完整链路。

完整的克隆、Docker 启动、环境变量和后端联调用法见 [`../docs/quickstart.md`](../docs/quickstart.md)。

## 本地运行

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

打开 `http://localhost:5173`。默认入口会重定向到演示项目概览。

## 数据源切换

复制 `.env.example` 为 `.env.local`。默认 `VITE_API_MODE=mock`；切换真实后端时设置：

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

API 模式使用 `src/api/client.ts` 中的类型化 HTTP client。Vite 开发服务器把 `/api` 代理到本地 RAGOps 后端；`VITE_API_PROXY_TARGET` 不是模型提供方地址，前端也没有任何 Key 或凭据参数。响应可为直接 JSON，或 `{ "data": ... }` 包装。所有请求都带 `Accept: application/json`，并设 10 秒超时。

顶部状态区同时展示三个互不推导的轴：前端数据源 `mock/api`、后端执行器 `mock/openai_compatible`、提供方 `未配置/已配置未验证/真实已验证`。`VITE_API_MODE=api` 只表示浏览器正在读取项目后端；状态接口缺失或失败时显示未知，绝不标成模型已连接。本阶段没有真实连接验证按钮。

前端页面路由中的 `projectId` 仅用于工作台上下文；后端 MVP 当前按资源提供接口，不带项目路径前缀。客户端已对齐以下契约并负责 snake_case 到页面模型的转换：

| 操作 | HTTP 契约 |
| --- | --- |
| 执行与提供方状态 | `GET /model-execution/status`（只读，不探测提供方） |
| 数据集列表 / 创建 | `GET /datasets`、`POST /datasets` |
| 2.0 样本导入 / 发布 | `POST /datasets/{datasetId}/samples:import`、`POST /datasets/{datasetId}:publish` |
| 评测任务列表 / 创建 / 状态 | `GET /evaluation-jobs`、`POST /evaluation-jobs`、`GET /evaluation-jobs/{jobId}` |
| 报告读取 / 导出 | `GET /evaluation-jobs/{jobId}/report`、`GET /evaluation-jobs/{jobId}/report/export` |
| 样本诊断 / 复核 | `GET /evaluation-jobs/{jobId}/samples`、`PATCH /evaluation-jobs/{jobId}/samples/{sampleId}/review` |

示例导入使用 2.0 契约，按“创建空草稿 → 导入人工样本 → 发布并冻结”执行。问题、参考标签、给定上下文、上下文来源、文档/片段 ID、历史输出和 metadata 分开传输；空数据集不会发送发布请求。任务创建显式提交执行器、Prompt 文本/版本、完整生成参数和上下文策略。选择未配置的执行器或本阶段不可用的 `retrieval` 时，页面展示后端错误码和安全消息，不回退到 mock。

mock 模式的新增数据集、创建评测和样本复核仅保存在当前浏览器内存中，并明确使用 `mock-*` ID；刷新后重置。API 模式会调用上表的真实项目后端写入接口。项目聚合指标与趋势暂时没有后端接口，API 模式下概览仅聚合数据集和评测任务并显示边界提示。两种前端模式都不代表已接入真实 LLM、向量库或生产队列。

任务生命周期、样本执行结果、质量状态、质量结论和具体指标分别映射。执行成功不会产生 100 分或 `passed`；未执行指标显示“未评估”，未知 Token/成本/时间/旧模型身份显示“未知”。`provided` 和 `legacy_unknown` 上下文不会在前端改名成真实检索结果；引用 `resolved` 与 `supports_claim` 分开显示。报告与 Markdown/JSON 导出保留原始问题、参考答案、本次回答、历史回答、上下文来源、引用、错误和运行快照。

数据集列表和评测任务列表均提供显式刷新入口。刷新期间保留当前列表、搜索和筛选条件，并禁用重复提交；刷新失败时继续显示上次成功数据，给出错误原因和“重试刷新”入口。API 模式不会因刷新失败而切换到 mock 数据。

## 状态演练

页面右上角“数据场景”可切换正常、加载、空数据、请求失败和部分数据；选择结果写入 URL 的 `state` 查询参数，便于复现与测试。

## 质量检查

```bash
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```

API 模式的真实浏览器验收使用本机 Edge/Chrome，不下载浏览器：

```powershell
npm --prefix frontend run acceptance:offline-browser -- create
npm --prefix frontend run acceptance:offline-browser -- restart_recheck
npm --prefix frontend run acceptance:offline-browser -- disconnected
```

运行前需按 [`../tests/acceptance/offline-readiness/browser-checklist.md`](../tests/acceptance/offline-readiness/browser-checklist.md) 启动本地前后端并配置证据目录。脚本会阻止非 localhost HTTP(S) 请求；语义错误、非断连阶段 console error 或外部请求都会以非零退出并保留证据。
