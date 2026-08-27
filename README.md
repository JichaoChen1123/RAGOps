# RAGOps

**RAGOps 是 RAG 应用质量评测与故障诊断平台。**

当前仓库交付了一个可运行、可测试的工程化 MVP：用脱敏 fixture 和确定性执行器完成“数据集 → 评测任务 → 指标计算 → 样本诊断 → 人工复核 → 报告导出”闭环，让评测结果可复现、故障依据可审计、质量门禁可自动执行。

> 这是 RAGOps 工程骨架，不是生产 RAG 服务。默认 mock 模式不会调用真实模型；真实 LLM provider、向量库、Embedding/Rerank 服务仍属于下一阶段。

## 技术栈与工程含量

| 层次 | 技术与已实现内容 |
| --- | --- |
| 前端 | React、TypeScript、Vite、React Router；组件化工作台；类型化 mock/API client；概览、数据集、评测任务、报告和样本诊断路由；加载、空数据、错误和部分数据状态。 |
| 后端 | FastAPI、SQLite、SQLAlchemy、Pydantic / Pydantic Settings；数据集、评测任务、样本结果、复核状态和报告 API；幂等任务创建、统一错误结构与健康检查。 |
| 评测 | Recall@K、MRR@K、NDCG@K、Context Precision/Recall、引用命中率等确定性指标；版本化诊断规则；脱敏样本 fixture；JSON 报告导出。 |
| 工程化 | Docker Compose、GitHub Actions；Ruff、Pytest、Vitest、TypeScript 类型检查和前端构建；分支覆盖率门禁；Markdown、JSON/JSONL、YAML 与 fixture 一致性校验。 |

核心链路：

```text
脱敏样本 / fixture
        ↓
SQLite 数据集（草稿、导入、发布冻结）
        ↓
确定性评测任务（queued → running → completed）
        ↓
聚合指标 + 样本级诊断证据
        ↓
人工复核（pending / confirmed / dismissed）
        ↓
JSON 导出；前端可继续生成 Markdown 文件
```

## 功能完成度

| 范围 | 状态 | 当前能力与边界 |
| --- | --- | --- |
| Mock UI 演示 | 已完成 | 可浏览概览、数据集、任务、报告和样本诊断；可模拟创建、筛选、复核、版本对比及 JSON/Markdown 导出；包含加载、空、失败和部分数据场景。写入只保存在浏览器内存中，刷新后重置。 |
| 数据集 API MVP | 已完成 | 创建数据集、批量导入样本、发布冻结、列表与详情读取；使用 SQLite 持久化。 |
| 评测任务 API MVP | 已完成 | 创建任务、幂等重放、状态流转、样本结果和聚合报告；执行器计算本地确定性指标，不调用外部模型。 |
| 复核与导出 API MVP | 已完成 | 样本诊断状态可在 `pending`、`confirmed`、`dismissed` 间更新；报告导出接口返回带样本摘要的结构化 JSON。 |
| 测试与质量门禁 | 已完成 | 后端、评测、前端交互和 API client 均有自动化测试；CI 执行 lint、类型检查、单测、覆盖率、构建、文档/fixture 校验和 Docker 镜像构建。 |
| 真实 RAG 基础设施 | 下一阶段 | 接入真实 LLM provider、向量数据库、Embedding、Rerank、LLM judge 与线上数据采集。 |
| 生产级交付 | 下一阶段 | 真实浏览器 E2E、生产部署、鉴权、多租户、可观测性、任务队列、高可用、数据库迁移与对象存储。 |

## Mock / API 边界

| 模式 | 数据来源 | 写入行为 | 适用场景 |
| --- | --- | --- | --- |
| `VITE_API_MODE=mock`（默认） | 仓库内脱敏 fixture | 仅修改当前浏览器内存；刷新即重置 | 稳定演示 UI、交互状态和诊断链路 |
| `VITE_API_MODE=api` | `VITE_API_BASE_URL` 指向的后端 | 调用真实 MVP API，并把成功或错误结果呈现在页面 | API 契约联调与二次开发 |

Mock 模式不是生产 RAG，也不代表模型推理、检索或持久化已经发生。API MVP 虽然会把数据集、任务结果和复核状态持久化到 SQLite，但执行的仍是仓库内确定性评测逻辑；它没有接入真实 provider、向量库或生产任务队列。

API 模式不会在请求失败时静默回退到 mock。类型化 client 已覆盖数据集创建、评测任务创建、样本复核和报告导出等资源契约；本地浏览器直连后端时，还需要在开发环境补充同源代理或允许跨域访问。

## 无 Docker 验收教程（Windows PowerShell）

### 1. 准备环境

- Git
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 与 npm

在 PowerShell 中确认版本：

```powershell
git --version
python --version
uv --version
node --version
npm --version
```

克隆并进入仓库：

```powershell
git clone https://github.com/JichaoChen1123/RAGOps.git
Set-Location RAGOps
```

### 2. 启动前端 mock 模式

在第一个 PowerShell 窗口、仓库根目录运行：

```powershell
npm --prefix frontend ci
$env:VITE_API_MODE = "mock"
npm --prefix frontend run dev
```

访问以下页面验收：

| 页面 | 地址 | 验收重点 |
| --- | --- | --- |
| 项目概览 | <http://localhost:5173/projects/demo/overview> | 指标卡、趋势、失败类型分布和新建评测入口 |
| 数据集 | <http://localhost:5173/projects/demo/datasets> | 搜索、筛选、创建/导入演示和状态反馈 |
| 评测任务 | <http://localhost:5173/projects/demo/evaluations> | 任务创建、筛选、刷新和报告入口 |
| 评测报告 | <http://localhost:5173/projects/demo/evaluations/eval-20260826/report> | 聚合指标、失败样本、版本对比、JSON/Markdown 导出 |
| 样本诊断 | <http://localhost:5173/projects/demo/evaluations/eval-20260826/samples/sample-042> | 诊断证据、检索片段、引用信息和复核状态 |

页面右上角“数据场景”可切换正常、加载、空数据、请求失败和部分数据。mock 模式中的创建与复核是演示状态，不应当作后端写入成功的证据。

### 3. 启动后端 API

在第二个 PowerShell 窗口、仓库根目录运行：

```powershell
uv sync --project backend --extra dev --frozen
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

默认数据库文件是仓库根目录的 `ragops.db`。启动后访问：

- Swagger UI：<http://localhost:8000/docs>
- OpenAPI JSON：<http://localhost:8000/openapi.json>
- 就绪检查：<http://localhost:8000/health/ready>

可以在 Swagger UI 按下列顺序验收真实 API MVP：

1. `POST /api/v1/datasets` 创建数据集。
2. `POST /api/v1/datasets/{dataset_id}/samples:import` 导入样本。
3. `POST /api/v1/datasets/{dataset_id}:publish` 发布并冻结数据集。
4. `POST /api/v1/evaluation-jobs` 创建评测任务。
5. `GET /api/v1/evaluation-jobs/{job_id}` 查询任务状态。
6. `GET /api/v1/evaluation-jobs/{job_id}/samples` 查看样本结果。
7. `PATCH /api/v1/evaluation-jobs/{job_id}/samples/{sample_id}/review` 更新复核状态。
8. `GET /api/v1/evaluation-jobs/{job_id}/report` 查看报告。
9. `GET /api/v1/evaluation-jobs/{job_id}/report/export` 导出结构化 JSON。

验收样本位于 `examples/eval-samples/`；`tests/backend/test_mvp_acceptance.py` 展示了完整 API 调用闭环。

## Docker Compose 快速启动

已安装 Docker Engine 与 Docker Compose v2 时，在仓库根目录运行：

```powershell
docker compose up --build
```

启动后访问前端 <http://localhost:5173> 和 Swagger UI <http://localhost:8000/docs>。默认不需要 `.env`；如需覆盖端口或模式：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

停止并保留 SQLite 数据卷：

```powershell
docker compose down
```

连同本地 Compose 数据卷一起清理：

```powershell
docker compose down --volumes
```

## 本地质量检查

后端、评测、覆盖率与仓库契约：

```powershell
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run --project backend python scripts/validate_repository.py
```

前端：

```powershell
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```

GitHub Actions 在 pull request 和 `main` push 上运行相同的核心门禁，并验证 Docker Compose 构建。

## 简历可写技术点

请按自己的真实参与范围取舍和改写：

- 设计并实现 RAG 应用质量评测与故障诊断 MVP，打通数据集、评测任务、样本诊断、人工复核和报告导出闭环。
- 使用 FastAPI、SQLAlchemy、Pydantic 与 SQLite 构建类型化资源 API，落地统一错误结构、健康检查和持久化模型。
- 实现带幂等键的评测任务创建与 `queued → running → completed` 状态流转，降低重复提交导致的任务污染。
- 实现 Recall@K、MRR@K、NDCG@K、Context Precision/Recall 和 Citation Hit Rate 等可审计的确定性 RAG 指标。
- 构建版本化故障诊断规则，输出原因、证据、置信度、改进建议与缺失输入，区分“未触发”和“无法判定”。
- 使用 React、TypeScript、Vite 与 React Router 构建组件化诊断工作台，覆盖概览、数据集、任务、报告和样本证据页面。
- 设计 mock/API 双 client 与显式错误边界，保证演示数据和真实 API 结果不被静默混用。
- 建立 Pytest、Vitest、Ruff、TypeScript、覆盖率、fixture/文档校验和 Docker build 组成的 GitHub Actions 质量门禁。
- 建立脱敏 JSONL fixture 与指标 oracle，用自动化测试保障评测结果、异常输入和样本复核状态可复现。

## 仓库结构

```text
backend/             FastAPI 服务、数据模型、评测与诊断逻辑
frontend/            React 工作台、路由、组件与 mock/API client
docs/                产品、架构、设计、评测、开发与 QA 文档
examples/            数据集 schema、脱敏样本和指标 oracle
tests/               后端、评测、前端与验收测试
docker/              前后端镜像和 Nginx 配置
docker-compose.yml   本地一键启动编排
```

## 延伸文档

- [克隆、配置与使用教程](docs/quickstart.md)
- [本地开发、Docker 与 Windows Git hook 排障](docs/development.md)
- [后端平台架构、API、数据模型与异步评测流程](docs/architecture/backend.md)
- [评测指标、数据模型与执行流程](docs/evaluation/metrics.md)
- [故障诊断规则](docs/evaluation/diagnosis-rules.md)
- [评测数据集格式与样例](examples/datasets/README.md)
- [MVP 测试计划、验收标准与质量门禁](docs/qa/test-plan.md)
- [功能回归验收记录](docs/qa/wor-52-functional-acceptance.md)
- [测试目录与 fixture 自检](tests/README.md)
