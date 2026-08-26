# RAGOps 前端 MVP

React + TypeScript + Vite 实现的 RAGOps 工程工作台。默认使用内置脱敏 fixture，可演示“评测任务 → 报告 → 样本诊断 → 检索与引用证据”完整链路。

## 本地运行

```bash
npm install
npm run dev
```

打开 `http://localhost:5173`。默认入口会重定向到演示项目概览。

## 数据源切换

复制 `.env.example` 为 `.env.local`。默认 `VITE_API_MODE=mock`；切换真实后端时设置：

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

真实模式使用 `src/api/client.ts` 中的类型化 HTTP client。响应可为直接 JSON，或 `{ "data": ... }` 包装。所有请求都带 `Accept: application/json`，并设 10 秒超时。

## 状态演练

页面右上角“数据场景”可切换正常、加载、空数据、请求失败和部分数据；选择结果写入 URL 的 `state` 查询参数，便于复现与测试。

## 质量检查

```bash
npm run typecheck
npm test
npm run build
```
