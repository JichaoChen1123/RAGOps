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
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

真实模式使用 `src/api/client.ts` 中的类型化 HTTP client。响应可为直接 JSON，或 `{ "data": ... }` 包装。所有请求都带 `Accept: application/json`，并设 10 秒超时。

前端页面路由中的 `projectId` 仅用于工作台上下文；后端 MVP 当前按资源提供接口，不带项目路径前缀。客户端已对齐以下契约并负责 snake_case 到页面模型的转换：

| 操作 | HTTP 契约 |
| --- | --- |
| 数据集列表 / 创建 | `GET /datasets`、`POST /datasets` |
| 评测任务列表 / 创建 / 状态 | `GET /evaluation-jobs`、`POST /evaluation-jobs`、`GET /evaluation-jobs/{jobId}` |
| 报告读取 / 导出 | `GET /evaluation-jobs/{jobId}/report`、`GET /evaluation-jobs/{jobId}/report/export` |
| 样本诊断 / 复核 | `GET /evaluation-jobs/{jobId}/samples`、`PATCH /evaluation-jobs/{jobId}/samples/{sampleId}/review` |

mock 模式的新增数据集、创建评测和样本复核仅保存在当前浏览器内存中，并明确使用 `mock-*` ID；刷新后重置。API 模式会调用上表的真实 MVP 写入接口。项目聚合指标与趋势暂时没有后端接口，API 模式下概览仅聚合数据集和评测任务并显示边界提示。两种模式都不代表已接入真实 LLM、向量库或生产队列。

数据集列表和评测任务列表均提供显式刷新入口。刷新期间保留当前列表、搜索和筛选条件，并禁用重复提交；刷新失败时继续显示上次成功数据，给出错误原因和“重试刷新”入口。API 模式不会因刷新失败而切换到 mock 数据。

## 状态演练

页面右上角“数据场景”可切换正常、加载、空数据、请求失败和部分数据；选择结果写入 URL 的 `state` 查询参数，便于复现与测试。

## 质量检查

```bash
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```
