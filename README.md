# RAGOps

RAGOps 是一个面向 RAG 应用的质量评测、故障诊断与工程化交付平台。本仓库当前交付的是可运行、可测试的 MVP 骨架：

- 后端：FastAPI + SQLite，支持数据集、评测任务、样本结果和报告的最小闭环。
- 前端：React + TypeScript + Vite 的诊断工作台，默认使用脱敏 mock 数据演示核心链路。
- 评测：确定性指标、诊断规则、脱敏样例和 fixture oracle。
- 工程：Docker Compose、GitHub Actions、后端/前端/文档/fixture 质量门禁。

> 当前 MVP 可以用于本地演示、代码阅读、二次开发和质量门禁验证；还不是生产版。真实 provider、LLM judge、浏览器级 E2E、前端真实 API 端到端闭环仍在后续范围内。

## 运行模式与可见交互边界

### Mock 模式

Mock 模式只使用仓库内的脱敏 fixture 和确定性演示状态，用于复现 UI 流程。允许在浏览器内模拟创建、筛选、复核和导出，但这些动作不代表真实模型运行或生产持久化；刷新导致状态重置时，界面必须提前说明。

### API 模式

API 模式以配置的服务端为唯一事实来源。数据集创建/导入、评测任务创建/状态读取、样本复核和报告导出必须调用后端契约并展示真实成功或错误结果。当前实现与契约状态请以 [WOR-49 可见交互验收矩阵](docs/qa/wor-49-visible-interactions.md) 为准。

### No silent fallback（禁止静默回退）

API 超时、断开、返回校验错误或能力尚未实现时，页面必须给出可理解的错误、重试入口或明确禁用说明；禁止静默切换到 mock 后显示成功。所有视觉上可操作的主要按钮都必须执行动作、打开界面，或以禁用态说明边界，不能点击后没有反馈。

## 克隆

完整教程见：[克隆、配置与使用教程](docs/quickstart.md)。

最快方式是准备 Docker Engine 与 Docker Compose v2，然后运行：

```bash
git clone https://github.com/JichaoChen1123/RAGOps.git
cd RAGOps
docker compose up --build
```

启动后访问：

- 前端工作台：<http://localhost:5173>
- 后端 Swagger UI：<http://localhost:8000/docs>
- 后端就绪检查：<http://localhost:8000/health/ready>

无需先创建 `.env`；需要覆盖端口或运行参数时，将 `.env.example` 复制为 `.env` 后再启动：

```bash
cp .env.example .env
docker compose up --build
```

PowerShell：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

停止服务并保留本地数据：

```bash
docker compose down
```

连同名为 `ragops-data` 的 Compose 数据卷一起清理：

```bash
docker compose down --volumes
```

## 不使用 Docker 的本地运行

后端：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

前端：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

前端默认 `VITE_API_MODE=mock`，用于稳定演示“任务 -> 报告 -> 样本诊断”链路；后端真实 API 可通过 Swagger UI 独立验证。前后端真实 API 端到端路由尚未完全对齐，切换到 `api` 模式前请先阅读 [本地开发与工程交付](docs/development.md)。

## 本地质量检查

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run --project backend python scripts/validate_repository.py

npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build

docker compose config --quiet
docker compose build
```

CI 在 pull request 与 `main` push 上执行同一组后端 lint/test、前端 typecheck/test/build、Markdown/fixture/YAML 校验，并构建 Docker 镜像。

## 文档入口

- [克隆、配置与使用教程](docs/quickstart.md)
- [本地开发、Docker 与 Windows Git hook 排障](docs/development.md)
- [后端平台架构、API、数据模型与异步评测流程](docs/architecture/backend.md)
- [评测指标、数据模型与执行流程](docs/evaluation/metrics.md)
- [故障诊断规则](docs/evaluation/diagnosis-rules.md)
- [评测数据集格式与样例](examples/datasets/README.md)
- [MVP 测试计划、验收标准与质量门禁](docs/qa/test-plan.md)
- [MVP 骨架验收与质量门禁](docs/qa/mvp-acceptance.md)
- [可复现评测样例](examples/eval-samples/README.md)
- [测试目录与 fixture 自检](tests/README.md)
