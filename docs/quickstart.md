# 克隆、配置与使用教程

本文面向第一次拿到仓库的使用者，说明如何从零克隆、配置环境、启动 MVP、验证功能和运行质量检查。

## 1. 当前 MVP 可以做什么

当前仓库可以直接用于：

- 用 Docker Compose 一键启动前端工作台和后端 API。
- 在前端查看脱敏 mock 演示数据，体验“评测任务 -> 报告 -> 样本诊断 -> 检索与引用证据”链路。
- 通过 Swagger UI 调用真实后端 API，验证数据集、样本导入、发布、评测任务、样本结果和报告接口。
- 让前端以 API 模式连接本地后端，执行人工样本导入、mock 任务、报告、刷新和 SQLite 重启持久化闭环。
- 以默认断网安全配置运行 mock，或离线测试 OpenAI-compatible 适配器的请求、错误、超时和重试契约。
- 运行后端、前端、评测、fixture 和文档质量门禁。

当前仓库暂不声明以下能力已经完成：

- 真实 LLM/RAG provider 接入。
- LLM judge 或线上业务评测。
- 生产部署、高可用、权限系统、真实向量检索与生产队列。

> 当前集成基线的浏览器 API 验收发现诊断 `rule_id` 被显示为 `unclassified`。核心闭环可运行，但修复并复测前不能宣称离线阶段全部通过；见 [离线基础集成验收记录](qa/offline-readiness-acceptance.md)。

## 2. 前置环境

推荐优先使用 Docker 方式启动。手动开发时再安装 Python 与 Node.js。

| 用途 | 依赖 | 说明 |
| --- | --- | --- |
| 克隆代码 | Git | 任意常用 Git 客户端均可 |
| 一键启动 | Docker Engine + Docker Compose v2 | 推荐方式，命令为 `docker compose ...` |
| 后端本地开发 | Python 3.11+、uv | Docker 镜像使用 Python 3.11 |
| 前端本地开发 | Node.js 24、npm | Docker 镜像使用 `node:24-alpine` |

检查命令：

```bash
git --version
docker --version
docker compose version
python --version
uv --version
node --version
npm --version
```

如果只想体验 MVP，前 3 个命令可用即可。

## 3. 克隆仓库

```bash
git clone https://github.com/JichaoChen1123/RAGOps.git
cd RAGOps
```

建议先确认当前在仓库根目录：

```bash
ls
```

应能看到 `backend/`、`frontend/`、`docs/`、`examples/`、`tests/` 和 `docker-compose.yml`。

## 4. 使用 Docker 一键启动

仓库根目录运行：

```bash
docker compose up --build
```

首次启动会构建两个镜像：

- `backend`：FastAPI API，默认暴露 `8000`。
- `frontend`：Nginx 托管的前端工作台，默认暴露 `5173`。

启动后访问：

- 前端工作台：<http://localhost:5173>
- 后端 Swagger UI：<http://localhost:8000/docs>
- 后端就绪检查：<http://localhost:8000/health/ready>

PowerShell 也可以验证后端健康：

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

curl：

```bash
curl http://localhost:8000/health/ready
```

期望返回：

```json
{"status":"ready"}
```

## 5. 配置环境变量

默认不需要 `.env` 也能启动。需要改端口、日志级别或前端数据模式时，复制示例文件：

```bash
cp .env.example .env
```

PowerShell：

```powershell
Copy-Item .env.example .env
```

常用配置：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `RAGOPS_BACKEND_PORT` | `8000` | 后端映射到本机的端口 |
| `RAGOPS_FRONTEND_PORT` | `5173` | 前端映射到本机的端口 |
| `RAGOPS_DATABASE_URL` | `sqlite:////data/ragops.db` | Docker 内后端数据库地址 |
| `RAGOPS_LOG_LEVEL` | `INFO` | 后端日志级别 |
| `RAGOPS_AUTO_CREATE_SCHEMA` | `true` | 是否自动创建 MVP 表结构 |
| `RAGOPS_MODEL_EXECUTION_ADAPTER` | `mock` | 默认执行器：`mock` 或 `openai_compatible` |
| `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED` | `false` | 真实模型网络总开关；默认先于 DNS/socket 拒绝 |
| `RAGOPS_MODEL_REQUEST_TIMEOUT_MS` | `10000` | 单次模型请求超时上限 |
| `RAGOPS_MODEL_TOTAL_TIMEOUT_MS` | `25000` | 包含重试的总时间上限 |
| `RAGOPS_MODEL_MAX_ATTEMPTS` | `3` | 总尝试次数，包含第一次 |
| `VITE_API_MODE` | `mock` | 前端数据源模式 |
| `VITE_API_BASE_URL` | `/api/v1` | 前端 API base URL |

示例：如果本机 `5173` 被占用，可以在 `.env` 中改成：

```dotenv
RAGOPS_FRONTEND_PORT=5174
```

然后重新启动：

```bash
docker compose up --build
```

## 6. 前端怎么使用

打开 <http://localhost:5173>。

当前默认进入脱敏 mock 演示模式，可以查看：

- 项目概览。
- 数据集状态。
- 评测任务列表。
- 单次评测报告。
- 样本级诊断、检索片段和引用证据。

页面右上角的“数据场景”可切换正常、加载、空数据、请求失败和部分数据，用于演示不同产品状态。

API 模式已经对齐后端资源路由。页面 URL 中的 `projectId` 只是工作台上下文；API 请求使用 `/api/v1/datasets`、`/evaluation-jobs`、报告、样本/复核和 `/model-execution/status`。`VITE_API_MODE=api` 只表示浏览器读取 RAGOps 后端，不代表真实模型已配置或验证。

## 7. 后端怎么使用

打开 Swagger UI：<http://localhost:8000/docs>。

最小 API 流程：

1. `POST /api/v1/datasets` 创建草稿数据集。
2. `POST /api/v1/datasets/{dataset_id}/samples:import` 导入样本。
3. `POST /api/v1/datasets/{dataset_id}:publish` 发布并冻结数据集。
4. `POST /api/v1/evaluation-jobs` 创建评测任务。
5. `GET /api/v1/evaluation-jobs/{job_id}` 查询任务状态。
6. `GET /api/v1/evaluation-jobs/{job_id}/samples` 查看样本结果。
7. `GET /api/v1/evaluation-jobs/{job_id}/report` 查看评测报告。
8. `GET /api/v1/evaluation-jobs/{job_id}/report/export` 导出结构化报告。
9. `GET /api/v1/model-execution/status` 查看不含秘密且不探测提供方的执行状态。

脱敏样例位于：

- `examples/eval-samples/valid-samples.jsonl`
- `examples/eval-samples/invalid-samples.jsonl`
- `examples/eval-samples/metric-cases.json`

后端验收测试 `tests/backend/test_mvp_acceptance.py` 演示了如何把这些样例接入真实 API 闭环。

### 数据库迁移

`ragops init-db` 与后端自动初始化都执行 `0001_mvp_baseline -> 0002_model_execution_contract`。对无迁移元数据的完整 1.0 库，程序会先校验必需表和字段，再盖章并升级；重复执行是 no-op。部分或未知 schema 会明确失败，不能删除旧库或用 `create_all` 重建来冒充迁移。

## 8. 不使用 Docker 的本地开发

后端：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

默认数据库是仓库根目录下的 `ragops.db`。需要改数据库时：

```bash
RAGOPS_DATABASE_URL=sqlite:///./local-ragops.db uv run --project backend ragops init-db
```

PowerShell：

```powershell
$env:RAGOPS_DATABASE_URL = "sqlite:///./local-ragops.db"
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

前端 mock 模式：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

打开 <http://localhost:5173>。

如果要在前端本地覆盖配置，可创建 `frontend/.env.local`：

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=/api/v1
VITE_API_PROXY_TARGET=http://127.0.0.1:8000
```

随后先启动后端，再启动 Vite。代理保持浏览器同源；`VITE_API_PROXY_TARGET` 是 RAGOps 后端地址，不是模型提供方地址，不能填写 Key。

## 9. 运行测试和质量门禁

本阶段最终结果、实际命令、截图和阻断缺陷见 [离线基础集成验收记录](qa/offline-readiness-acceptance.md)。

后端、评测、fixture 和覆盖率：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run --project backend python scripts/validate_repository.py
pwsh -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
pwsh -File tests/acceptance/offline-readiness/run-local-restart.ps1 -RepoRoot .
```

前端：

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
node --check frontend/scripts/offline-readiness-browser.mjs
```

产品浏览器 API 模式脚本不会下载浏览器，使用本机 Edge/Chrome。它需要已按 [浏览器检查表](../tests/acceptance/offline-readiness/browser-checklist.md) 启动的本地后端与前端，并分 `create`、`restart_recheck`、`disconnected` 三阶段运行。脚本发现语义或控制台错误时会以非零退出，截图不能替代 API 断言。

Docker：

```bash
docker compose config --quiet
docker compose build
```

## 10. 停止、重启和清理

停止服务，保留 SQLite 数据卷：

```bash
docker compose down
```

停止服务并清空 Docker 数据卷：

```bash
docker compose down --volumes
```

本地非 Docker 模式如果要重置数据库，停止后端后删除 `ragops.db`，再重新执行：

```bash
uv run --project backend ragops init-db
```

## 11. 常见问题

### 端口被占用

复制 `.env.example` 为 `.env`，修改：

```dotenv
RAGOPS_BACKEND_PORT=8001
RAGOPS_FRONTEND_PORT=5174
```

然后重新启动 `docker compose up --build`。

### 前端页面能打开，但看起来不是后端真实数据

前端默认 `VITE_API_MODE=mock`，用于稳定演示产品链路。要读取本地后端，按第 8 节配置 `api` 模式并确认页面顶部显示“API 数据”。不要把 mock fixture、API 模式或 mock 执行器误写成真实模型连接。

### Docker 不可用

使用“不使用 Docker 的本地开发”流程，分别启动后端和前端。Docker Compose build 只能在安装 Docker 的机器或 GitHub CI 上验证。

### Windows 上 uv 缓存或 pytest 临时目录权限异常

可以把缓存和 pytest 临时目录放到仓库内：

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --basetemp .pytest-basetemp
```

这些目录是运行产物，不要提交。

### npm 或 Vite 在受限环境中出现 `spawn EPERM`

这通常是受限 Windows 运行环境阻止子进程启动。请在普通终端或 CI runner 中重试：

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

### 想接入真实模型

不要只把 `VITE_API_MODE` 改为 `api`：它与模型提供方无关。需要由用户明确提供 provider、模型、后端 Base URL/鉴权、secret 注入、超时/重试/并发/预算要求和经授权数据，并在隔离环境单独做受控连接验证。默认 `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` 必须保留，未经授权不能用现有凭据探测。
