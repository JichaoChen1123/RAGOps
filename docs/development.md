# 本地开发与工程交付

## 从零克隆

如果你是第一次使用本仓库，先阅读 [克隆、配置与使用教程](quickstart.md)。该教程覆盖 Git clone、Docker 一键启动、环境变量、本地后端/前端启动、测试命令和常见问题。

最短路径：

```bash
git clone https://github.com/JichaoChen1123/RAGOps.git
cd RAGOps
docker compose up --build
```

启动后访问：

- 前端工作台：<http://localhost:5173>
- 后端 Swagger UI：<http://localhost:8000/docs>
- 后端就绪检查：<http://localhost:8000/health/ready>

## Docker Compose 一键启动

仓库根目录下的唯一启动命令是：

```bash
docker compose up --build
```

Compose 会构建并启动两个服务：

- `backend`：Python 3.11、FastAPI、SQLite 持久化卷，暴露 `8000`。
- `frontend`：Node 24 构建、Nginx 静态托管，暴露 `5173`。

服务启动顺序由后端 readiness healthcheck 控制；前端只会在后端健康后启动。默认值已写入 `docker-compose.yml`，因此 `.env` 不是启动前置条件。需要覆盖端口、日志级别或数据源模式时：

```bash
cp .env.example .env
docker compose up --build
```

PowerShell 对应命令：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

`.env` 已加入 `.gitignore`。示例文件不含密钥；后续如果引入真实凭证，只能通过本地环境或受控 secret store 注入。

### 当前接口边界

前端 client 已对齐后端的 `/api/v1/datasets`、`/evaluation-jobs`、报告、样本/复核与 `/model-execution/status` 资源路由。前端页面 URL 中的 `projectId` 只表示工作台上下文，不会被拼进资源 API。Vite 开发服务器通过 `VITE_API_PROXY_TARGET` 代理 `/api`，Compose/Nginx 通过同源 `/api/` 代理到 backend。

Compose 仍默认 `VITE_API_MODE=mock`，避免克隆后把演示数据误当成本地持久化结果。设置 `VITE_API_MODE=api` 后，页面会读取并写入真实 RAGOps 后端；这不表示外部模型已配置、已连接或已验证。

## 不使用 Docker 的本地开发

后端：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

前端（默认 mock）：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

本地 API 模式：

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

$env:VITE_API_MODE = 'api'
$env:VITE_API_BASE_URL = '/api/v1'
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8000'
npm --prefix frontend run dev
```

后端命令与前端命令应在两个终端运行。只有顶部状态同时显示“API 数据 / mock / 提供方未配置”时，才是本阶段预期的离线 API 组合。

## 模型执行与秘密边界

后端默认使用 `mock`，`RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` 是唯一外部模型网络总开关。OpenAI-compatible 适配器已通过内存 HTTP transport 离线测试，但没有完成真实连接验证；不能因为 Base URL 或 Key 存在就自动启用。

秘密只能通过后端环境或 secret store 注入。不得进入 `VITE_*`、API 状态响应、运行快照、日志、异常消息、报告、截图或前端 build。完整变量、范围和错误语义见 [模型执行契约](architecture/model-execution-contract.md)。

## 数据库初始化与迁移

```powershell
uv run --project backend ragops init-db
uv run --project backend ragops init-db
```

两次命令都应成功，第二次不重复迁移。迁移链为 `0001_mvp_baseline -> 0002_model_execution_contract`；完整旧 1.0 库会先校验再升级并保留原记录，新库直接创建到 head。部分或未知 schema 必须报错，禁止删库、删卷或 `create_all` 重建来代替迁移。

## 与 CI 一致的检查

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend ruff check --config backend/pyproject.toml backend/app tests scripts
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=85

npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build

uv run --project backend python scripts/validate_repository.py
pwsh -File tests/acceptance/offline-readiness/validate-assets.ps1 -RepoRoot .
pwsh -File tests/acceptance/offline-readiness/run-local-restart.ps1 -RepoRoot .
docker compose config --quiet
docker compose build
```

`scripts/validate_repository.py` 会检查 Markdown 基础格式与本地链接、JSON/JSONL 可解析性、脱敏 fixture 的关键 oracle，以及 YAML（包括 Compose 和 GitHub Actions）语法。

阶段测试矩阵、实际结果、截图和未验证项见 [离线基础集成验收记录](qa/offline-readiness-acceptance.md)。产品浏览器脚本使用本机 Edge/Chrome，不下载浏览器；启动方式和三阶段顺序见 `tests/acceptance/offline-readiness/browser-checklist.md`。D01 诊断 `rule_id`/React key 修复已在 `1698150bf8a63dfd534b4c10a2fc64287cbcf993` 完成独立复测，三个浏览器阶段分别保留当前 DOM/API 与退出码；Docker 容器和真实模型连接仍未验证。

如果 Docker Engine 未运行，只记录 `docker info` 的实际错误，并继续本地回归；不要安装 Docker、登录账号或删除用户卷。Engine 可用时执行：

```powershell
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
pwsh -File tests/acceptance/offline-readiness/run-docker-loop.ps1 -RepoRoot .
```

## Windows Git hook 的 `sh.exe` 风险

受限 Windows 运行环境中，Git for Windows 启动 POSIX hook 时可能失败：

```text
sh.exe: fatal error - couldn't create signal pipe, Win32 error 5
error: 'prepare-commit-msg' hook failed
```

这表示 hook shell 没有启动成功，不代表代码或暂存内容失败。按以下顺序处理：

1. 用 `git status` 确认 Git 操作停留在哪一步，并阅读 `.git/hooks/prepare-commit-msg`，确认该 hook 的真实作用。
2. 先手动运行本页全部质量检查；不要把跳过 hook 当作跳过 lint/test 的方式。
3. 仅为当前 Git 命令指定一个空 hooks 目录，不写全局或仓库级 `core.hooksPath`。
4. 如果 hook 本应添加提交 trailer，手动在提交消息中保留同样的 trailer，再用 `git show -s --format=fuller HEAD` 核对结果。

PowerShell 示例：

```powershell
$emptyHooks = Join-Path (Resolve-Path ..) '.git-hooks-disabled'
New-Item -ItemType Directory -Force $emptyHooks | Out-Null
git -c core.hooksPath=$emptyHooks commit -m 'WOR-46: add Docker and CI baseline' -m 'Co-authored-by: multica-agent <github@multica.ai>'
```

对暂停的 cherry-pick，可在确认原提交消息已包含所需 trailer 后执行：

```powershell
git -c core.hooksPath=$emptyHooks cherry-pick --continue
```

不要使用 `git config --global core.hooksPath ...`，也不要删除平台安装的 hook；全局绕过会影响其他仓库并掩盖真正的安全检查。
