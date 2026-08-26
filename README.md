# RAGOps

RAG 质量评测、故障诊断与工程化交付平台。本仓库当前提供可运行的后端 MVP、前端诊断工作台、脱敏评测样例和基础质量门禁。

## 一键启动

准备 Docker Engine 与 Docker Compose v2 后，在仓库根目录运行：

```bash
docker compose up --build
```

无需先创建 `.env`；需要覆盖端口或运行参数时，将 `.env.example` 复制为 `.env` 后再执行同一条命令。

- 前端工作台：<http://localhost:5173>
- 后端 Swagger UI：<http://localhost:8000/docs>
- 后端就绪检查：<http://localhost:8000/health/ready>

前端容器默认使用脱敏 mock 数据，确保“任务 → 报告 → 样本诊断”演示链路稳定可用；后端同时以真实 SQLite API 启动。前后端当前资源路由尚未完全对齐，因此真实 API 模式不作为默认值，详见 `docs/development.md`。

停止服务并保留本地数据：

```bash
docker compose down
```

连同名为 `ragops-data` 的 Compose 数据卷一起清理：

```bash
docker compose down --volumes
```

## 本地质量检查

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests/backend scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend -q
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
uv run --project backend python scripts/validate_repository.py
```

CI 在 pull request 与 `main` push 上执行同一组后端 lint/test、前端 typecheck/test/build、Markdown/fixture/YAML 校验，并构建两个 Docker 镜像。

## 文档入口

- [本地开发、Docker 与 Windows Git hook 排障](docs/development.md)
- [后端平台架构、API、数据模型与异步评测流程](docs/architecture/backend.md)
- [评测指标、数据模型与执行流程](docs/evaluation/metrics.md)
- [故障诊断规则](docs/evaluation/diagnosis-rules.md)
- [评测数据集格式与样例](examples/datasets/README.md)
- [MVP 测试计划、验收标准与质量门禁](docs/qa/test-plan.md)
- [可复现评测样例](examples/eval-samples/README.md)
- [测试目录与 fixture 自检](tests/README.md)
